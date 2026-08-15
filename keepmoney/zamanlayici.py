"""Tarama zamanlayıcısı — worker sürecinin ana döngüsü.

KARAR: Redis + arq/Celery YOK (bkz. docs/MIMARI.md K24).

Kuyruk altyapısı, "kullanıcı bir iş tetikler, N worker paylaşır" problemini
çözer. Bizim iş bu değil: periyodik olarak *sırası gelmiş* ürünleri taramak.
Sıranın kendisi zaten veritabanında duruyor (`Product.son_kontrol` +
`kontrol_araligi_dk`) — yani DB kuyruğun ta kendisi. Üstüne Redis koymak,
aynı bilgiyi ikinci bir yerde tutmak ve yeni bir arıza noktası eklemek olurdu.

Bu döngü tek süreçte çalışır ve şunu yapar:
  1. sırası gelen ürünleri tara
  2. bekleyen uyarıları Telegram'a ilet
  3. ölçümleri güncelle
  4. uyu

İkinci worker gerektiğinde geçiş yolu açık: `taranacak_urunler`e
`SELECT ... FOR UPDATE SKIP LOCKED` eklemek (Postgres) tek satırlık iştir ve
kuyruk kütüphanesi olmadan yatay ölçekleme sağlar.
"""
from __future__ import annotations

import asyncio
import contextlib
import signal
import time

from .cekici import HttpCekici
from .db import SessionLocal
from .gunluk import log
from .models import Alert, Product
from .olcumler import bayat_urun, bekleyen_uyari, izlenen_urun, tarama_turu_suresi
from .throttle import HostThrottle
from .worker import Tarayici
from .zaman import utc_simdi

logger = log("keepmoney.zamanlayici")

TUR_ARALIGI_SN = 60          # her dakika "sırası gelen var mı" diye bak
TUR_BASINA_URUN = 50
BAYATLIK_SAAT = 24


class Zamanlayici:
    def __init__(self) -> None:
        # Throttle SÜREÇ ÖMRÜ BOYUNCA tekil olmalı: host cezaları turlar
        # arasında hatırlanmazsa, engellenen siteye her turda yeniden gidilir.
        self.throttle = HostThrottle()
        self.cekici = HttpCekici()
        self._dur = asyncio.Event()

    def durdur(self) -> None:
        logger.info("kapanma_istendi")
        self._dur.set()

    async def tur(self) -> None:
        baslangic = time.monotonic()
        with SessionLocal() as db:
            tarayici = Tarayici(db, self.cekici, self.throttle)

            # Tarama senkron ve I/O ağırlıklı — olay döngüsünü bloklamasın.
            sonuc = await asyncio.to_thread(tarayici.tur_calistir, TUR_BASINA_URUN)

            if sonuc.taranan_urun:
                logger.info(
                    "tarama_turu",
                    urun=sonuc.taranan_urun,
                    okunan=sonuc.okunan_kaynak,
                    basarisiz=sonuc.basarisiz_kaynak,
                    ertelenen=sonuc.ertelenen_kaynak,
                    fiyat_degisen=sonuc.fiyat_degisen,
                    uyari=sonuc.uretilen_uyari,
                    hata=len(sonuc.hatalar),
                )

            await self._uyarilari_ilet(db)
            self._olcumleri_guncelle(db)

        tarama_turu_suresi.observe(time.monotonic() - baslangic)

    async def _uyarilari_ilet(self, db) -> None:
        """Bot yapılandırılmamışsa sessizce atlanır — uyarılar web'de durur."""
        try:
            from .bot.gonderici import bekleyenleri_gonder
            from .bot.uygulama import AiogramPostaci, bot_olustur
        except ImportError:
            return                      # aiogram kurulu değil, bot isteğe bağlı

        bot = bot_olustur()
        if bot is None:
            return
        try:
            await bekleyenleri_gonder(db, AiogramPostaci(bot))
        finally:
            with contextlib.suppress(Exception):
                await bot.session.close()

    def _olcumleri_guncelle(self, db) -> None:
        izlenen_urun.set(db.query(Product).count())
        bekleyen_uyari.set(
            db.query(Alert).filter(Alert.telegram_gonderildi.is_(False)).count())

        from datetime import timedelta
        sinir = utc_simdi() - timedelta(hours=BAYATLIK_SAAT)
        bayat_urun.set(
            db.query(Product)
            .filter((Product.son_kontrol.is_(None)) | (Product.son_kontrol < sinir))
            .count()
        )

    async def calistir(self) -> None:
        logger.info("zamanlayici_basladi", aralik_sn=TUR_ARALIGI_SN)
        try:
            while not self._dur.is_set():
                try:
                    await self.tur()
                except Exception as e:
                    # Tek turun hatası döngüyü ÖLDÜRMEZ. Bu süreç 7/24
                    # ayakta kalmalı; geçici bir DB/ağ hatası yüzünden
                    # durursa tüm tarama durur.
                    logger.exception("tur_hatasi", hata=str(e))

                with contextlib.suppress(TimeoutError, asyncio.TimeoutError):
                    await asyncio.wait_for(self._dur.wait(), TUR_ARALIGI_SN)
        finally:
            self.cekici.kapat()
            logger.info("zamanlayici_durdu")


async def main() -> None:
    from .gunluk import kur

    kur()
    z = Zamanlayici()

    # Nazik kapanma: konteyner SIGTERM gönderir; yarım kalan tur bitsin,
    # tarayıcı düzgün kapansın.
    dongu = asyncio.get_running_loop()
    for sinyal in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            dongu.add_signal_handler(sinyal, z.durdur)

    await z.calistir()


if __name__ == "__main__":
    asyncio.run(main())

"""robots.txt saygısı.

NEDEN VAR: bu ürün başkalarının sitelerinden veri okuyor. `robots.txt`
teknik bir zorunluluk değil — kimse zorlamaz — ama site sahibinin açıkça
ifade ettiği iradedir. Yok saymak iki şeye mal olur: IP'nin kalıcı olarak
engellenmesi (ürünün tamamen çalışmaz hâle gelmesi) ve savunulabilir bir
konumun kaybı. Uymak, üretilen değerden hiçbir şey eksiltmiyor: fiyat
sayfalarını `Disallow` eden site zaten yok denecek kadar az; engellenen
tipik yollar sepet, arama ve hesap sayfaları.

TASARIM:
  • `urllib.robotparser` standart kütüphanede — yeni bağımlılık yok.
  • Sonuç host başına ÖNBELLEKLENİR: her fiyat okumasında robots.txt
    indirmek, korumaya çalıştığımız yükü ikiye katlardı.
  • `robots.txt` OKUNAMAZSA İZİN VERİLİR. Sunucu hatası yüzünden taramayı
    durdurmak, geçici bir arızayı kalıcı veri kaybına çevirir; ayrıca
    "yasak" beyanı yoksa yasak yoktur.
  • İndirme SSRF kapısından geçer (`aglar.dogrula`) — robots.txt de sonuçta
    kullanıcının verdiği bir adrese yapılan istektir.
"""
from __future__ import annotations

import threading
import time
import urllib.robotparser
from urllib.parse import urlparse

from .aglar import guvenli_mi
from .gunluk import log

logger = log("keepmoney.robots")

# Bot kimliğimiz. `robots.txt`te bize özel kural yazılabilsin diye ayrı bir
# ad taşıyoruz; site sahibi istediğinde yalnızca bizi engelleyebilmeli.
BOT_ADI = "KeepMoneyBot"

# Önbellek ömrü: robots.txt nadiren değişir, günde bir kez bakmak fazlasıyla
# yeterli ve site başına ek yükü ihmal edilebilir kılıyor.
ONBELLEK_OMRU_SN = 24 * 3600

ZAMAN_ASIMI_SN = 10


class RobotsKapisi:
    """Host başına robots.txt kuralları. Süreç ömrü boyunca tekil olmalı."""

    def __init__(self, onbellek_omru: int = ONBELLEK_OMRU_SN):
        self.onbellek_omru = onbellek_omru
        self._kilit = threading.Lock()
        # host → (okuyucu | None, ne zaman alındı). None = okunamadı.
        self._onbellek: dict[str, tuple[object | None, float]] = {}

    def _oku(self, taban: str):
        """robots.txt indirir. Okunamazsa None (izin ver anlamına gelir)."""
        okuyucu = urllib.robotparser.RobotFileParser()
        okuyucu.set_url(f"{taban}/robots.txt")
        try:
            okuyucu.read()
            return okuyucu
        except Exception as e:
            logger.debug("robots_okunamadi", taban=taban, hata=str(e))
            return None

    def _okuyucu_getir(self, taban: str):
        simdi = time.monotonic()
        with self._kilit:
            girdi = self._onbellek.get(taban)
            if girdi and simdi - girdi[1] < self.onbellek_omru:
                return girdi[0]

        okuyucu = self._oku(taban)          # ağ çağrısı kilit DIŞINDA
        with self._kilit:
            self._onbellek[taban] = (okuyucu, simdi)
        return okuyucu

    def izin_var_mi(self, url: str) -> bool:
        """Bu URL taranabilir mi?

        Kararsız kalınan her durumda True döner — robots.txt bir yasak
        beyanıdır; beyan yoksa yasak da yoktur.
        """
        p = urlparse(url)
        if not p.scheme or not p.hostname:
            return True
        taban = f"{p.scheme}://{p.netloc}"

        # robots.txt'nin kendisi de bir dış istektir: SSRF kapısından geçmeli.
        if not guvenli_mi(f"{taban}/robots.txt"):
            return True                     # asıl engelleme çekim anında

        okuyucu = self._okuyucu_getir(taban)
        if okuyucu is None:
            return True

        try:
            return bool(okuyucu.can_fetch(BOT_ADI, url))
        except Exception:
            return True

    def temizle(self) -> None:
        with self._kilit:
            self._onbellek.clear()

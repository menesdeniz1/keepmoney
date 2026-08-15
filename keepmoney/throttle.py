"""Site bazlı istek aralığı ve üstel geri çekilme.

Ölçekli scraping'de tek başarısızlık noktası budur: aynı siteye arka arkaya
istek göndermek IP'yi hızla yaktırır. Bu sınıf iki şey yapar:
  1) Aynı hosta istekler arasına asgari aralık + jitter koyar,
  2) Bot koruması görülürse o hosta üstel geri çekilme uygular (5→10→…→60 dk).

Kritik davranış — ERTELEME: bekleme MAX_KUYRUK_BEKLEME'yi aşacaksa kontrol o
tur ATLANIR. Aksi halde cezalı bir hostun sırasını bekleyen görev worker
slotunu dakikalarca işgal eder; birkaç slot birden cezalı hosta denk gelince
TÜM tarama saatlerce kilitlenir. (Bu davranış gerçek bir üretim arızasından
geliyor: loglarda 15-57 dakikalık açıklanamayan sessizlikler.)

API SENKRONDUR — bilerek. Önceki sürümde sıraya girme `async with
throttle.slot(host)` biçiminde bir ASENKRON bağlam yöneticisiydi; oysa tarama
yolu (`Tarayici.kaynak_oku`) senkrondur ve `asyncio.to_thread` içinden
çağrılır. Yani o arayüzü kullanmak yapısal olarak MÜMKÜN DEĞİLDİ ve hiçbir
yerden çağrılmadı: yukarıda "tek başarısızlık noktası" diye yazan korumanın
birinci maddesi üretimde hiç devreye girmiyor, worker aynı hosta ardışık
istekleri tam hızla atıyordu. Ceza (ikinci madde) çalışıyordu; aralık
çalışmıyordu. Koruma ancak tarama yoluyla aynı renkte olursa iş görür.
"""
from __future__ import annotations

import random
import threading
import time
from collections import defaultdict

VARSAYILAN_ARALIK = 25.0        # aynı hosta iki istek arasındaki min saniye
MAX_KUYRUK_BEKLEME = 180.0      # bunu aşan bekleme → tur atlanır
CEZA_TABAN = 300.0              # ilk geri çekilme: 5 dk
CEZA_TAVAN = 3600.0             # tavan: 1 saat


class HostThrottle:
    """Host başına aralık + ceza yöneticisi. Süreç ömrü boyunca tekil olmalı.

    İş parçacığı güvenli: tarama `asyncio.to_thread` ile ayrı bir thread'de
    koşuyor ve ileride birden çok tarama thread'i olabilir. Tek kilit yeter —
    korunan işlemler mikrosaniyelik sözlük güncellemeleri.
    """

    def __init__(self, min_gap: float = VARSAYILAN_ARALIK):
        self.min_gap = min_gap
        self._kilit = threading.Lock()
        self._musait: dict[str, float] = defaultdict(float)   # monotonic
        self._ceza: dict[str, float] = defaultdict(float)     # saniye

    # ── aralık ───────────────────────────────────────────────────

    def tahmini_bekleme(self, host: str) -> float:
        """Bu hosta ŞİMDİ girilse kaç saniye beklenir (rezervasyon YAPMADAN).
        Erteleme kararı buna bakılarak verilir."""
        with self._kilit:
            return max(0.0, self._musait[host] - time.monotonic())

    def ertelenmeli_mi(self, host: str) -> bool:
        return self.tahmini_bekleme(host) > MAX_KUYRUK_BEKLEME

    def sirala(self, host: str) -> float:
        """Sıraya girer: beklenecek süreyi döner ve BİR SONRAKİ slotu rezerve
        eder.

        Rezervasyon çağrı anında yapılır, uyku bittikten sonra değil: iki
        thread aynı anda girerse ikincisi birincinin slotunu görüp arkasına
        dizilir. Jitter şart — sabit aralık makine imzası gibi görünür.
        """
        with self._kilit:
            simdi = time.monotonic()
            bekle = max(0.0, self._musait[host] - simdi)
            gap = self.min_gap * random.uniform(0.8, 1.6)
            self._musait[host] = simdi + bekle + gap
            return bekle

    def bekle(self, host: str) -> float:
        """`sirala` + uyku. Tarama yolunun kullandığı tek çağrı."""
        sure = self.sirala(host)
        if sure > 0:
            time.sleep(sure)
        return sure

    # ── ceza ─────────────────────────────────────────────────────

    def cezalandir(self, host: str) -> float:
        """Bot koruması algılandı → geri çekilmeyi büyüt. Dönen: ceza saniyesi."""
        with self._kilit:
            self._ceza[host] = min(
                max(self._ceza[host] * 2, CEZA_TABAN), CEZA_TAVAN)
            self._musait[host] = time.monotonic() + self._ceza[host]
            return self._ceza[host]

    def odullendir(self, host: str) -> None:
        """Başarılı okuma → geri çekilmeyi sıfırla.

        Yalnızca cezayı sıfırlar; `_musait` DOKUNULMAZ — yoksa her başarılı
        okuma aralık rezervasyonunu da siler ve asgari aralık anlamsızlaşır.
        """
        with self._kilit:
            self._ceza[host] = 0.0

    def ceza_durumu(self, host: str) -> float:
        with self._kilit:
            return self._ceza[host]

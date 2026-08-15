"""Site bazlı istek kuyruğu ve üstel geri çekilme.

Ölçekli scraping'de tek başarısızlık noktası budur: aynı siteye eşzamanlı
istek göndermek IP'yi hızla yaktırır. Bu sınıf iki şey yapar:
  1) Aynı hosta istekleri SIRAYA sokar (aralarında min_gap + jitter),
  2) Bot koruması görülürse o hosta üstel geri çekilme uygular (5→10→…→60 dk).

Kritik davranış — ERTELEME: kuyruk beklemesi MAX_KUYRUK_BEKLEME'yi aşacaksa
kontrol o tur ATLANIR. Aksi halde cezalı bir hostun sırasını bekleyen görev
worker slotunu dakikalarca işgal eder; birkaç slot birden cezalı hosta denk
gelince TÜM tarama saatlerce kilitlenir. (Bu davranış gerçek bir üretim
arızasından geliyor: loglarda 15-57 dakikalık açıklanamayan sessizlikler.)
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict

VARSAYILAN_ARALIK = 25.0        # aynı hosta iki istek arasındaki min saniye
MAX_KUYRUK_BEKLEME = 180.0      # bunu aşan bekleme → tur atlanır
CEZA_TABAN = 300.0              # ilk geri çekilme: 5 dk
CEZA_TAVAN = 3600.0             # tavan: 1 saat


class HostThrottle:
    """Host başına kuyruk + ceza yöneticisi. Süreç ömrü boyunca tekil olmalı."""

    def __init__(self, min_gap: float = VARSAYILAN_ARALIK):
        self.min_gap = min_gap
        self._kilitler: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._musait: dict[str, float] = defaultdict(float)   # monotonic
        self._ceza: dict[str, float] = defaultdict(float)     # saniye

    def slot(self, host: str) -> _Slot:
        """`async with throttle.slot(host):` biçiminde kullanılır."""
        return _Slot(self, host)

    def tahmini_bekleme(self, host: str) -> float:
        """Bu hosta ŞİMDİ girilse kaç saniye beklenir (kilit almadan tahmin).
        Erteleme kararı buna bakılarak verilir."""
        return max(0.0, self._musait[host] - time.monotonic())

    def ertelenmeli_mi(self, host: str) -> bool:
        return self.tahmini_bekleme(host) > MAX_KUYRUK_BEKLEME

    def cezalandir(self, host: str) -> float:
        """Bot koruması algılandı → geri çekilmeyi büyüt. Dönen: ceza saniyesi."""
        self._ceza[host] = min(max(self._ceza[host] * 2, CEZA_TABAN), CEZA_TAVAN)
        self._musait[host] = time.monotonic() + self._ceza[host]
        return self._ceza[host]

    def odullendir(self, host: str) -> None:
        """Başarılı okuma → geri çekilmeyi sıfırla."""
        self._ceza[host] = 0.0

    def ceza_durumu(self, host: str) -> float:
        return self._ceza[host]


class _Slot:
    def __init__(self, throttle: HostThrottle, host: str):
        self.t = throttle
        self.host = host

    async def __aenter__(self):
        await self.t._kilitler[self.host].acquire()
        bekle = self.t._musait[self.host] - time.monotonic()
        if bekle > 0:
            await asyncio.sleep(bekle)
        return self

    async def __aexit__(self, *exc):
        # Bir sonraki aynı-site isteği için minimum aralık + jitter.
        # Jitter önemli: sabit aralık makine imzası gibi görünür.
        gap = self.t.min_gap * random.uniform(0.8, 1.6)
        self.t._musait[self.host] = max(
            self.t._musait[self.host], time.monotonic() + gap)
        self.t._kilitler[self.host].release()
        return False

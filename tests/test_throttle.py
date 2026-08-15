"""Host aralığı ve geri çekilme testleri.

Bu dosyanın varlık sebebi: aralık koruması bir dönem HİÇ ÇALIŞMIYORDU.
`slot()` asenkron bir bağlam yöneticisiydi, tarama yolu ise senkron —
yani çağrılması yapısal olarak mümkün değildi ve hiç çağrılmadı.
"""
from __future__ import annotations

import time

from keepmoney.throttle import (
    CEZA_TABAN,
    CEZA_TAVAN,
    MAX_KUYRUK_BEKLEME,
    HostThrottle,
)


def test_ilk_istek_beklemez():
    t = HostThrottle(min_gap=10)
    assert t.sirala("magaza.com") == 0.0


def test_ikinci_istek_aralik_kadar_bekler():
    """Asıl korunan davranış: aynı hosta ardışık istek."""
    t = HostThrottle(min_gap=10)
    t.sirala("magaza.com")
    bekle = t.sirala("magaza.com")
    assert 8 <= bekle <= 16, bekle          # 10 * jitter(0.8-1.6)


def test_farkli_hostlar_birbirini_beklemez():
    t = HostThrottle(min_gap=10)
    t.sirala("a.com")
    assert t.sirala("b.com") == 0.0


def test_aralik_kumulatiftir():
    """Üçüncü istek ikincinin arkasına dizilmeli — hepsi aynı anda değil."""
    t = HostThrottle(min_gap=10)
    t.sirala("m.com")
    ikinci = t.sirala("m.com")
    ucuncu = t.sirala("m.com")
    assert ucuncu > ikinci


def test_jitter_var():
    """Sabit aralık makine imzası gibi görünür ve bot korumasına yakalanır."""
    olculen = set()
    for _ in range(20):
        t = HostThrottle(min_gap=10)
        t.sirala("m.com")
        olculen.add(round(t.sirala("m.com"), 3))
    assert len(olculen) > 1, "jitter yok — tüm beklemeler aynı"


def test_bekle_gercekten_uyur():
    t = HostThrottle(min_gap=0.2)
    t.bekle("m.com")
    basla = time.monotonic()
    t.bekle("m.com")
    assert time.monotonic() - basla >= 0.15


# ── ceza ─────────────────────────────────────────────────────────

def test_ceza_ustel_buyur():
    t = HostThrottle()
    assert t.cezalandir("m.com") == CEZA_TABAN
    assert t.cezalandir("m.com") == CEZA_TABAN * 2
    assert t.cezalandir("m.com") == CEZA_TABAN * 4


def test_ceza_tavani_asmaz():
    t = HostThrottle()
    for _ in range(20):
        t.cezalandir("m.com")
    assert t.ceza_durumu("m.com") == CEZA_TAVAN


def test_cezali_host_ertelenir():
    t = HostThrottle()
    t.cezalandir("m.com")                   # 300 sn > 180 sn eşiği
    assert t.ertelenmeli_mi("m.com") is True


def test_odul_cezayi_sifirlar():
    t = HostThrottle()
    t.cezalandir("m.com")
    t.odullendir("m.com")
    assert t.ceza_durumu("m.com") == 0.0


def test_odul_aralik_rezervasyonunu_silmez():
    """Ödül yalnızca cezayı sıfırlamalı. `_musait`i de sıfırlasaydı her
    başarılı okuma aralığı silerdi ve asgari aralık anlamsızlaşırdı."""
    t = HostThrottle(min_gap=10)
    t.sirala("m.com")
    t.odullendir("m.com")
    assert t.sirala("m.com") > 0


def test_normal_host_ertelenmez():
    t = HostThrottle(min_gap=10)
    t.sirala("m.com")
    assert t.ertelenmeli_mi("m.com") is False
    assert t.tahmini_bekleme("m.com") <= MAX_KUYRUK_BEKLEME


def test_tahmini_bekleme_rezervasyon_yapmaz():
    """Erteleme kararı sırayı ilerletmemeli — yoksa sadece bakmak bile
    hostu geriye atardı."""
    t = HostThrottle(min_gap=10)
    t.sirala("m.com")
    once = t.tahmini_bekleme("m.com")
    t.tahmini_bekleme("m.com")
    assert t.tahmini_bekleme("m.com") <= once

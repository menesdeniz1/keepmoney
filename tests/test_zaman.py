"""Zaman dilimi politikası testleri.

Buradaki testler ürünün en sinsi hata kaynağını kapatıyor: gece yarısı
civarındaki okumaların YANLIŞ GÜNE yazılması. Türkiye UTC+3 olduğu için
UTC gününe göre gruplama, akşam 21:00'den sonraki her okumayı ertesi güne
kaydırırdı.
"""
from datetime import UTC, date, datetime

from keepmoney.analiz import Okuma, gunluk_minimumlar
from keepmoney.zaman import TR, sessiz_saat_mi, tr_gun, tr_saat, utc_simdi


def test_utc_simdi_naive_ve_utc():
    t = utc_simdi()
    assert t.tzinfo is None
    fark = abs((t - datetime.now(UTC).replace(tzinfo=None)).total_seconds())
    assert fark < 5


def test_tr_saat_naive_girdiyi_utc_kabul_eder():
    """DB'den gelen her şey naive UTC'dir."""
    tr = tr_saat(datetime(2026, 8, 15, 12, 0))
    assert tr.hour == 15          # UTC+3 (yaz/kış fark etmez, TR sabit +3)
    assert tr.tzinfo == TR


def test_tr_saat_aware_girdiyi_cevirir():
    tr = tr_saat(datetime(2026, 8, 15, 12, 0, tzinfo=UTC))
    assert tr.hour == 15


def test_tr_gun_gece_yarisi_kaymasi():
    """KRİTİK: UTC 22:00 = Türkiye'de ERTESİ GÜN 01:00.
    Bu okuma Türkiye takviminde 16 Ağustos'a aittir, 15'ine değil."""
    assert tr_gun(datetime(2026, 8, 15, 22, 0)) == date(2026, 8, 16)


def test_tr_gun_gunduz_kaymaz():
    assert tr_gun(datetime(2026, 8, 15, 9, 0)) == date(2026, 8, 15)


def test_gunluk_minimum_turkiye_gunune_gore_gruplar():
    """Aynı Türkiye gününe düşen iki okuma tek güne toplanmalı — biri UTC'de
    bir önceki güne düşse bile."""
    okumalar = [
        Okuma(datetime(2026, 8, 15, 21, 30), 1000),   # TR: 16 Ağu 00:30
        Okuma(datetime(2026, 8, 16, 6, 0), 900),      # TR: 16 Ağu 09:00
    ]
    g = gunluk_minimumlar(okumalar)
    assert g == {date(2026, 8, 16): 900}


def test_sessiz_saat_normal_aralik():
    # UTC 22:00 → TR 01:00, 0-8 aralığında
    assert sessiz_saat_mi(0, 8, datetime(2026, 8, 15, 22, 0)) is True
    # UTC 09:00 → TR 12:00, aralık dışı
    assert sessiz_saat_mi(0, 8, datetime(2026, 8, 15, 9, 0)) is False


def test_sessiz_saat_gece_yarisini_asan_aralik():
    # 23-7 aralığı: UTC 21:00 → TR 00:00 → içeride
    assert sessiz_saat_mi(23, 7, datetime(2026, 8, 15, 21, 0)) is True
    # UTC 12:00 → TR 15:00 → dışarıda
    assert sessiz_saat_mi(23, 7, datetime(2026, 8, 15, 12, 0)) is False

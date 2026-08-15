"""Fiyat zekâsı testleri — ürünün kalbi burası, en sıkı test edilen katman."""
from datetime import date, datetime, timedelta

from keepmoney.analiz import (
    MIN_GUN,
    Okuma,
    dip_kirildi_mi,
    fiyat_baglami,
    gunluk_minimumlar,
    sahte_indirim_mi,
    trend,
)

BUGUN = date(2026, 8, 15)


def seri(fiyatlar, bitis=BUGUN, gun_basina=1):
    """En eskiden yeniye günlük okuma listesi üretir."""
    n = len(fiyatlar)
    out = []
    for i, f in enumerate(fiyatlar):
        g = bitis - timedelta(days=(n - 1 - i))
        for k in range(gun_basina):
            out.append(Okuma(datetime(g.year, g.month, g.day, k % 24, (k * 7) % 60), f))
    return out


# ---------- günlük minimum ----------

def test_gunluk_minimum_gun_basina_tek_deger():
    o = [
        Okuma(datetime(2026, 8, 14, 9), 1000),
        Okuma(datetime(2026, 8, 14, 18), 900),    # aynı gün, daha ucuz
        Okuma(datetime(2026, 8, 15, 9), 950),
    ]
    assert gunluk_minimumlar(o) == {date(2026, 8, 14): 900, date(2026, 8, 15): 950}


def test_gunluk_minimum_sik_tarama_medyani_bozmaz():
    """Sık taranan ürün ham listede medyanı domine ederdi; günlük minimum
    bunu engeller — 3 gün, günde 20 okuma → yine 3 değer."""
    o = seri([1000, 1100, 1200], gun_basina=20)
    assert len(gunluk_minimumlar(o)) == 3


# ---------- fiyat bağlamı ----------

def test_baglam_yetersiz_veride_none():
    assert fiyat_baglami(seri([100] * (MIN_GUN - 1)), 100, BUGUN) is None


def test_baglam_dip_bolgesi():
    b = fiyat_baglami(seri([1000, 1000, 950, 980, 1000, 900]), 900, BUGUN)
    assert b is not None
    assert b.sinyal == "dip"
    assert b.emoji == "🟢"
    assert b.dip90 == 900


def test_baglam_dip_toleransi_kurus_farkini_affeder():
    """901 TL, 900'lük dibin %2'si içinde → yine dip sayılmalı."""
    b = fiyat_baglami(seri([1000, 1000, 950, 980, 1000, 900]), 901, BUGUN)
    assert b.sinyal == "dip"


def test_baglam_ortalamanin_alti():
    b = fiyat_baglami(seri([1000, 1200, 1100, 900, 1300, 1000]), 990, BUGUN)
    assert b.sinyal == "ucuz"
    assert b.emoji == "🟡"


def test_baglam_pahali_donem():
    b = fiyat_baglami(seri([1000, 900, 950, 1000, 980, 1100]), 1400, BUGUN)
    assert b.sinyal == "pahali"
    assert b.emoji == "🔴"


def test_baglam_yuzdelik_dilim():
    """5 günün 4'ünde bugünkünden pahalıydı → %80'inden ucuz."""
    b = fiyat_baglami(seri([1500, 1400, 1300, 1200, 900]), 1000, BUGUN)
    assert b.yuzdelik == 80


def test_baglam_tum_zamanlar_dibi_tarihiyle():
    o = seri([1000, 700, 1100, 1200, 1300, 1250])
    b = fiyat_baglami(o, 1250, BUGUN)
    assert b.tum_zamanlar_dibi == 700
    assert b.tum_zamanlar_dibi_tarih == BUGUN - timedelta(days=4)


def test_baglam_90_gun_disi_veriyi_saymaz():
    eski = [Okuma(datetime(2026, 1, 1), 10)]      # 7 ay önce, 90g dışı
    o = eski + seri([1000, 1000, 1000, 1000, 1000, 1000])
    b = fiyat_baglami(o, 1000, BUGUN)
    assert b.dip90 == 1000        # 10 TL pencereye girmemeli
    assert b.tum_zamanlar_dibi == 10   # ama tüm zamanlar dibi onu görmeli


def test_iyi_firsat_dip_ve_sahte_degil():
    b = fiyat_baglami(seri([1000, 1000, 950, 980, 1000, 900]), 900, BUGUN)
    assert b.iyi_firsat is True


# ---------- sahte indirim (bull-trap) ----------

def test_sahte_indirim_siserilip_indirilen_fiyat():
    """900 seyrinde giden ürün 1500'e çıkarılıp 1300'e 'indiriliyor' —
    hâlâ medyanın çok üstünde → tuzak."""
    g = gunluk_minimumlar(seri([900, 900, 900, 900, 1500, 1300]))
    assert sahte_indirim_mi(1300, g, BUGUN) is True


def test_sahte_indirim_gercek_indirimde_tetiklenmez():
    g = gunluk_minimumlar(seri([1000, 1000, 1000, 1000, 1000, 800]))
    assert sahte_indirim_mi(800, g, BUGUN) is False


def test_sahte_indirim_pahali_ama_dusus_yoksa_tetiklenmez():
    """Sadece pahalı olmak yetmez — bir 'indirim' anlatısı da olmalı."""
    g = gunluk_minimumlar(seri([900, 900, 900, 900, 900, 1300]))
    assert sahte_indirim_mi(1300, g, BUGUN) is False


def test_sahte_indirim_yetersiz_veride_false():
    g = gunluk_minimumlar(seri([1000, 500]))
    assert sahte_indirim_mi(500, g, BUGUN) is False


# ---------- trend ----------

def test_trend_dusuyor():
    yon, guc = trend(gunluk_minimumlar(seri([1200, 1150, 1100, 1000, 950, 900])), BUGUN)
    assert yon == "dusuyor"
    assert guc > 0


def test_trend_yukseliyor():
    yon, _ = trend(gunluk_minimumlar(seri([900, 950, 1000, 1100, 1150, 1200])), BUGUN)
    assert yon == "yukseliyor"


def test_trend_sabit():
    yon, guc = trend(gunluk_minimumlar(seri([1000, 1000, 1000, 1000, 1000])), BUGUN)
    assert yon == "sabit"
    assert guc == 0.0


def test_trend_tek_veride_cokmez():
    assert trend({BUGUN: 100}, BUGUN) == ("sabit", 0.0)


# ---------- 30 günün dibi ----------

def test_dip_kirildi_bugunu_haric_tutar():
    """Bugünkü okuma dibin kendisi; dahil edilirse asla kırılmış sayılmaz."""
    o = seri([1000, 950, 980, 1000, 900])   # sonuncu = bugün = 900
    kirildi, onceki_dip, gun = dip_kirildi_mi(o, 900, 30, BUGUN)
    assert kirildi is True
    assert onceki_dip == 950
    assert gun == 4


def test_dip_kirilmadi():
    o = seri([1000, 800, 980, 1000, 900])
    kirildi, onceki_dip, _ = dip_kirildi_mi(o, 900, 30, BUGUN)
    assert kirildi is False
    assert onceki_dip == 800


def test_dip_veri_yoksa():
    assert dip_kirildi_mi([], 900, 30, BUGUN) == (False, None, 0)

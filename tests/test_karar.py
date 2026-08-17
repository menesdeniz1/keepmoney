"""Koruma katmanı testleri. Her test bir GERÇEK arıza vakasını temsil eder —
buradaki bir testi silmeden önce docstring'i oku."""
from keepmoney.karar import (
    IzlemeDurumu,
    KaynakOkumasi,
    alarm_gerekli,
    asiri_supheli,
    dogrula,
    en_iyi_kaynak,
    fiyat_supheli,
    pazar_aykiri,
)


def okuma(**kw) -> KaynakOkumasi:
    varsayilan = {"url": "https://magaza.com/u", "host": "magaza.com",
                  "fiyat": None, "guven": "secici"}
    varsayilan.update(kw)
    return KaynakOkumasi(**varsayilan)


# ---------- alarm ----------

def test_alarm_hedefin_altinda():
    assert alarm_gerekli(10000, okuma(fiyat=9500)) is True


def test_alarm_hedefin_ustunde():
    assert alarm_gerekli(10000, okuma(fiyat=10500)) is False


def test_alarm_hedef_yoksa_yok():
    assert alarm_gerekli(None, okuma(fiyat=1)) is False


# ---------- şüpheli fiyat ----------

def test_supheli_regex_gecmis_yoksa():
    """Doğrulanmamış regex okuması ilk seferde her zaman şüphelidir."""
    assert fiyat_supheli(okuma(fiyat=1000, guven="regex"), IzlemeDurumu()) is True


def test_supheli_regex_son_iyiye_yakinsa_temiz():
    """±%5 içinde kalan regex okumasını geçmiş doğruluyor — her turda
    yeniden doğrulama yapma."""
    d = IzlemeDurumu(son_iyi_fiyat=1000)
    assert fiyat_supheli(okuma(fiyat=1020, guven="regex"), d) is False


def test_supheli_regex_sapiyorsa():
    d = IzlemeDurumu(son_iyi_fiyat=1000)
    assert fiyat_supheli(okuma(fiyat=1300, guven="regex"), d) is True


def test_supheli_hedefin_yarisindan_ucuz():
    assert fiyat_supheli(okuma(fiyat=4000), IzlemeDurumu(), hedef=10000) is True


def test_supheli_ani_dusus():
    d = IzlemeDurumu(son_iyi_fiyat=10000)
    assert fiyat_supheli(okuma(fiyat=5000), d) is True


def test_supheli_ani_yukselis():
    """Gerçek vaka: güvenilir json-ld kaynağından, tek pazaryeri satıcısının
    hatalı girdiği fiyat yüzünden ürün 2-9 katına çıkmış görünüyordu."""
    d = IzlemeDurumu(son_iyi_fiyat=10000)
    assert fiyat_supheli(okuma(fiyat=19000, guven="json-ld"), d) is True


def test_supheli_normal_dalgalanma_temiz():
    d = IzlemeDurumu(son_iyi_fiyat=10000)
    assert fiyat_supheli(okuma(fiyat=9200), d) is False


# ---------- aşırı şüpheli ----------

def test_asiri_supheli_kategori_sayfasi_vakasi():
    """Gerçek vaka: mağaza linki genel kategori sayfasına düşmüş, regex
    oradan hedefin (12.500) çok altında sabit 1.260 TL okuyordu."""
    assert asiri_supheli(okuma(fiyat=1260, guven="regex"),
                         IzlemeDurumu(), hedef=12500) is True


def test_asiri_supheli_sadece_regex_kaynaginda_dusuk_esik():
    """Aynı düşük fiyat GÜVENİLİR kaynaktan gelirse aşırı sayılmaz —
    gerçek bir çöküş olabilir, normal 2-okuma yolu işler."""
    assert asiri_supheli(okuma(fiyat=1260, guven="json-ld"),
                         IzlemeDurumu(), hedef=12500) is False


def test_asiri_supheli_yuksek_uc():
    d = IzlemeDurumu(son_iyi_fiyat=10000)
    assert asiri_supheli(okuma(fiyat=35000, guven="json-ld"), d) is True


def test_asiri_supheli_gecmis_yoksa_yuksek_uc_tetiklenmez():
    assert asiri_supheli(okuma(fiyat=35000), IzlemeDurumu()) is False


# ---------- doğrula (durum makinesi) ----------

def test_dogrula_temiz_fiyat():
    d = IzlemeDurumu(son_iyi_fiyat=10000)
    ok, sebep = dogrula(okuma(fiyat=9800), d)
    assert ok is True and sebep == "temiz"


def test_dogrula_iki_okuma_ile_onaylanir():
    """Şüpheli fiyat, ikinci okuma ±%2 tutarlıysa gerçek kabul edilir."""
    d = IzlemeDurumu(son_iyi_fiyat=10000)
    ok, sebep = dogrula(okuma(fiyat=5000), d)
    assert ok is False and sebep == "beklemede"
    assert d.bekleyen_fiyat == 5000

    ok, sebep = dogrula(okuma(fiyat=5050), d)
    assert ok is True and sebep == "ikinci-okuma-dogruladi"
    assert d.bekleyen_fiyat is None


def test_dogrula_tutarsiz_ikinci_okuma_onaylamaz():
    d = IzlemeDurumu(son_iyi_fiyat=10000)
    dogrula(okuma(fiyat=5000), d)
    ok, sebep = dogrula(okuma(fiyat=3000), d)
    assert ok is False and sebep == "beklemede"
    assert d.bekleyen_fiyat == 3000      # yeni aday beklemeye alınır


def test_dogrula_bozuk_kaynak_iki_okumayla_onaylanmaz():
    """KRİTİK: bozuk kaynak kendisiyle saatlerce tutarlı kalabilir. Aynı
    aşırı değerin iki kez okunması onu doğru YAPMAZ."""
    d = IzlemeDurumu(son_iyi_fiyat=12500)
    for _ in range(3):
        ok, sebep = dogrula(okuma(fiyat=1260, guven="regex"), d, hedef=12500)
        assert ok is False and sebep == "bozuk"
    assert d.asiri_supheli_seri == 3


def test_dogrula_bozukluktan_cikis_makul_okumayla():
    d = IzlemeDurumu(son_iyi_fiyat=12500)
    dogrula(okuma(fiyat=1260, guven="regex"), d, hedef=12500)
    ok, sebep = dogrula(okuma(fiyat=12000, guven="json-ld"), d, hedef=12500)
    assert ok is True and sebep == "temiz"
    assert d.asiri_supheli_seri == 0


def test_dogrula_fiyat_yoksa():
    ok, sebep = dogrula(okuma(fiyat=None), IzlemeDurumu())
    assert ok is False and sebep == "fiyat-yok"


# ---------- en iyi kaynak ----------

def test_en_ucuz_kaynak_secilir():
    o = [okuma(fiyat=1200, host="a.com"), okuma(fiyat=1100, host="b.com"),
         okuma(fiyat=1300, host="c.com")]
    assert en_iyi_kaynak(o).host == "b.com"


def test_engelli_ve_olu_kaynak_elenir():
    o = [okuma(fiyat=900, host="a.com", engelli=True),
         okuma(fiyat=950, host="b.com", olu=True),
         okuma(fiyat=1100, host="c.com")]
    assert en_iyi_kaynak(o).host == "c.com"


def test_hepsi_engelliyse_none():
    o = [okuma(fiyat=900, engelli=True), okuma(fiyat=950, engelli=True)]
    assert en_iyi_kaynak(o) is None


def test_fiyatsiz_kaynak_yine_de_doner():
    o = [okuma(fiyat=None, host="a.com")]
    assert en_iyi_kaynak(o).host == "a.com"


# ── Pazar aykırılığı: geçmişi OLMAYAN ürünün tek savunması ───────
# Bu modüldeki diğer bütün ölçütler `son_iyi_fiyat`a bakıyor. Yeni eklenen
# üründe öyle bir fiyat yok — ilk okumada gelen absürt bir değeri hiçbiri
# yakalayamaz ve o değer geçmişin başlangıcı olur, sonraki tüm "dip"
# hesaplarını kirletir.

def _toplayici(fiyat, ikinci=None, satici_sayisi=None, guven="json-ld"):
    return KaynakOkumasi(url="https://akakce.com/x", host="akakce.com",
                         fiyat=fiyat, guven=guven, ikinci_fiyat=ikinci,
                         satici_sayisi=satici_sayisi)


def test_gecmissiz_urunde_aykiri_fiyat_yakalanir():
    """Asıl kazanım: `son_iyi_fiyat` YOK ve yine de şüphe uyanıyor."""
    okuma = _toplayici(4000.0, ikinci=52000.0, satici_sayisi=14)
    assert fiyat_supheli(okuma, IzlemeDurumu()) is True


def test_makul_kampanya_supheli_sayilmaz():
    """Gerçek kampanyada bir satıcı %20-30 ucuz olabilir; bunu şüpheli
    saymak her fırsatı geciktirirdi."""
    okuma = _toplayici(40000.0, ikinci=46000.0, satici_sayisi=9)
    assert fiyat_supheli(okuma, IzlemeDurumu()) is False


def test_asiri_aykiri_fiyat_bozuk_sayilir():
    """3 kat fark artık kampanya değil, hatalı liste kaydı. İkinci okuma da
    aynı hatalı kaydı okuyacağı için 2-okuma yolu burada işe yaramaz."""
    okuma = _toplayici(4000.0, ikinci=52000.0)
    assert asiri_supheli(okuma, IzlemeDurumu()) is True


def test_tek_satici_tek_basina_suphe_sebebi_degil():
    """Birçok ürünü gerçekten tek mağaza satıyor. Sinyal, kıyaslanacak
    ikinci bir fiyatın VARLIĞINDA."""
    okuma = _toplayici(4000.0, ikinci=None, satici_sayisi=1)
    assert fiyat_supheli(okuma, IzlemeDurumu()) is False
    assert asiri_supheli(okuma, IzlemeDurumu()) is False


def test_pazar_verisi_olmayan_kaynak_etkilenmez():
    """Toplayıcı olmayan sitelerde bu ölçüt hiç devreye girmemeli."""
    okuma = KaynakOkumasi(url="https://magaza.com/x", host="magaza.com",
                          fiyat=4000.0, guven="secici")
    assert pazar_aykiri(okuma) is False
    assert fiyat_supheli(okuma, IzlemeDurumu()) is False


def test_aykiri_fiyat_ikinci_okumayla_temizlenmez():
    """Bozuk eşiğindeki okuma, tutarlı gelse bile kabul edilmemeli —
    bozuk kaynak kendisiyle günlerce tutarlı kalabilir."""
    durum = IzlemeDurumu()
    okuma = _toplayici(4000.0, ikinci=52000.0)
    for _ in range(2):
        gecerli, sebep = dogrula(okuma, durum)
        assert gecerli is False
        assert sebep == "bozuk"


def test_ucuz_ama_pazarla_uyumlu_fiyat_gecer():
    """Yanlış pozitif koruması: gerçekten ucuz ama pazar da orada."""
    okuma = _toplayici(38000.0, ikinci=39500.0, satici_sayisi=22)
    gecerli, sebep = dogrula(okuma, IzlemeDurumu())
    assert gecerli is True, sebep

"""Site kuralları testleri."""
from keepmoney.siteler import host_cikar, kural, tanimli_siteler, toplayici_mi


def test_host_normalize_eder():
    assert host_cikar("https://www.Amazon.com.tr/dp/B0X") == "amazon.com.tr"
    assert host_cikar("https://n11.com/urun/x") == "n11.com"


def test_host_bozuk_url():
    assert host_cikar("bu bir url degil") == "bilinmiyor"


def test_tanimli_site_kurali_yuklenir():
    k = kural("https://www.trendyol.com/x/y-p-123")
    assert k["satici"] == "Trendyol"
    assert k["render"] is True
    assert "prc-dsc" in k["fiyat_secici"]


def test_tanimsiz_site_varsayilana_duser():
    """Config zorunlu değil — varsayılan zincir çoğu siteyi zaten okur."""
    k = kural("https://bilinmeyen-magaza.com/urun")
    assert k["render"] is False
    assert "fiyat_secici" not in k


def test_alt_alan_adi_ust_kurala_duser():
    assert kural("https://magaza.trendyol.com/x")["satici"] == "Trendyol"


def test_toplayici_isaretlenir():
    assert toplayici_mi("https://www.akakce.com/x-fiyati,123.html") is True
    assert toplayici_mi("https://www.amazon.com.tr/dp/X") is False


def test_sablon_dosyasi_kural_olarak_yuklenmez():
    assert "ornek.com" not in tanimli_siteler()


def test_turk_pazarinin_ana_siteleri_tanimli():
    tanimli = tanimli_siteler()
    for domain in ("amazon.com.tr", "hepsiburada.com", "trendyol.com",
                   "n11.com", "akakce.com"):
        assert domain in tanimli


def test_amazon_regex_kapsami_daraltilmis():
    """Sponsorlu ürün karuselinin fiyatını ana fiyat sanmasın diye."""
    assert kural("https://www.amazon.com.tr/dp/X")["metin_alani"] == "#centerCol"


# ── Gerçek sayfa yapısına karşı seçici testleri ──────────────────
# Bu blok ilk gerçek link denemesinden geldi. Amazon düzeni A/B test ediyor:
# `corePriceDisplay_desktop_feature_div` sayfada DURUYOR ama boş kalabiliyor
# ve fiyat `corePrice_desktop` kabuğuna taşınıyor. Seçici listesinde
# `corePrice_feature_div` yazıyordu — sayfadaki id o değildi ve hiçbir seçici
# tutmadı. Kural dosyaları burada, SEVK EDİLEN hâlleriyle sınanıyor.

from keepmoney.ayikla import fiyat_ayikla

# Kullanıcının kaydettiği sayfadan çıkarılan yapı. Fiyat metnindeki \xa0
# (kırılmaz boşluk) gerçek sayfadaki hâliyle korundu.
AMAZON_COREPRICE_DESKTOP = """<html><head><title>HyperX Cloud III S</title></head>
<body>
  <div id="apex_desktop">
    <div id="corePriceDisplay_desktop_feature_div"></div>
  </div>
  <div id="corePrice_desktop">
    <span class="a-price"><span class="a-offscreen">15.049,00\xa0TL</span></span>
  </div>
  <div id="oneri_karuseli">
    <span class="a-price"><span class="a-offscreen">1.099,00\xa0TL</span></span>
  </div>
</body></html>"""


def test_amazon_fiyati_corePrice_desktop_kabugundan_okunur():
    kural_ = kural("https://www.amazon.com.tr/dp/X")
    assert fiyat_ayikla(AMAZON_COREPRICE_DESKTOP, kural_) == (15049.0, "secici")


def test_amazon_oneri_karuseli_fiyati_secilmez():
    """En sinsi hata türü: fiyat OKUNUR ama YANLIŞ üründen.

    Sessizdir — kullanıcı 15.049 TL'lik kulaklığın 1.099 TL'ye düştüğünü
    sanır. Bu yüzden seçiciler dar kapsayıcılara bağlı, geniş
    `span.a-price` bilerek kullanılmıyor.
    """
    kural_ = kural("https://www.amazon.com.tr/dp/X")
    fiyat, _ = fiyat_ayikla(AMAZON_COREPRICE_DESKTOP, kural_)
    assert fiyat != 1099.0


def test_amazon_secicileri_gecerli_css():
    """Geçersiz CSS sessizce atlanıyor — kural dosyasındaki yazım hatası
    'seçici tutmadı' diye görünür ve saatlerce yanlış yerde aranır."""
    from bs4 import BeautifulSoup
    corba = BeautifulSoup("<html></html>", "lxml")
    for parca in kural("https://www.amazon.com.tr/dp/X")["fiyat_secici"].split(","):
        corba.select(parca.strip())          # geçersizse burada patlar

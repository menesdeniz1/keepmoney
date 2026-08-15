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

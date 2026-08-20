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


# ── Öncül projeden (tracker) geri getirilen bilgi ────────────────
# tracker Amazon'u üretimde aylarca sorunsuz okudu. İki bilgi port sırasında
# kaybolmuştu ve ikisi de gerçek vakalardan öğrenilmişti.

AMAZON_TWISTER = """<html><head><title>SteelSeries Nova 7</title></head>
<body><div id="apex_price">
  <span class="a-price">7.499,00\xa0TL</span>
</div></body></html>"""


def test_amazon_twister_sablonundan_fiyat_okunur():
    """Renk/varyant seçicili sayfalarda ana fiyat `#apex_price` içinde;
    diğer seçicilerin hiçbiri tutmuyor."""
    kural_ = kural("https://www.amazon.com.tr/dp/X")
    assert fiyat_ayikla(AMAZON_TWISTER, kural_) == (7499.0, "secici")


def test_amazon_gercek_tarayici_ister():
    """`requests` ile ilk birkaç istek geçiyor, sonra captcha geliyor; ayrıca
    buybox fiyatı JS ile yükleniyor. tracker her isteği tarayıcıyla yapıyordu."""
    assert kural("https://www.amazon.com.tr/dp/X")["render"] is True


def test_toplayicilar_gercek_tarayici_ister():
    """Maliyet modeli bunların üstünde duruyor: 10 mağaza yerine 1 sayfa."""
    for d in ("akakce.com", "cimri.com"):
        assert kural(f"https://www.{d}/x")["render"] is True


def test_oncul_projedeki_tum_siteler_tanimli():
    """`tracker` üretimde bu sitelerden fiyat okuyordu; port sırasında
    düşmemeliler. Kural dosyası olmayan site çalışmaz demek değil (varsayılan
    zincir devrede) ama öğrenilmiş seçici kaybolur."""
    tanimli = tanimli_siteler()
    for domain in ("amazon.com.tr", "hepsiburada.com", "trendyol.com",
                   "n11.com", "akakce.com", "mediamarkt.com.tr",
                   "incehesap.com", "itopya.com", "tebilon.com",
                   "sinerji.gen.tr"):
        assert domain in tanimli, domain


# ── Kural dosyalarının bütünlüğü ────────────────────────────────
# Bu dosyalar "kod değişikliği gerekmesin" diye YAML — yani üründe hata
# yapması EN KOLAY yer burası ve hataların hepsi SESSİZ:
#   * geçersiz CSS  → `fiyat_ayikla` içindeki `except: continue` yutar,
#   * anahtar yazım hatası (`fiyat_secic`) → kimse okumaz, varsayılana düşer,
#   * bozuk YAML    → `_tum_kurallar` dosyayı atlar, site tanımsız sanılır,
#   * bozuk regex   → kanonik URL kalıbı hiç uygulanmaz, fiyat geçmişi bölünür.
# Hiçbiri patlamaz; hepsi "site okumuyor" diye görünür ve saatlerce yanlış
# yerde aranır. Amazon için ayrı bir CSS testi vardı — tek site yetmez.

SECICI_ANAHTARLARI = (
    "fiyat_secici", "metin_alani", "baslik_secici",
    "satici_secici", "saticilar_secici", "saticilar_fiyat_secici",
)

# Kodun GERÇEKTEN okuduğu anahtarlar. Listede olmayan bir anahtar ya yazım
# hatasıdır ya da kaldırılmış bir özelliğin kalıntısı; ikisi de sessizce
# hiçbir şey yapmaz. Yeni bir anahtar eklerken buraya da eklenmeli — bu
# testin amacı tam olarak o adımı zorunlu kılmak.
BILINEN_ANAHTARLAR = set(SECICI_ANAHTARLARI) | {
    "domain", "satici", "render", "bekleme_sn", "toplayici",
    "kanonik_yol_kalibi", "kanonik_yol_bicimi", "ortaklik", "notlar",
}


def _kural_dosyalari():
    from keepmoney.siteler import SITELER_DIZINI
    return [y for y in sorted(SITELER_DIZINI.glob("*.yaml"))
            if not y.name.startswith("_")]


def _yukle(yol):
    import yaml
    return yaml.safe_load(yol.read_text(encoding="utf-8")) or {}


def test_her_kural_dosyasi_gecerli_yaml_ve_domainli():
    """`_tum_kurallar` bozuk YAML'ı sessizce atlıyor: site tanımsız sanılır."""
    for yol in _kural_dosyalari():
        kural_ = _yukle(yol)                 # bozuksa burada patlar
        assert isinstance(kural_, dict), yol.name
        assert kural_.get("domain"), f"{yol.name}: `domain` yok, dosya yüklenmez"


def test_dosya_adi_domainle_uyusur():
    """`amazon_com_tr.yaml` → `amazon.com.tr`. Uyuşmazlık, düzenlenen dosyanın
    aslında başka bir siteyi etkilemesi demektir."""
    for yol in _kural_dosyalari():
        beklenen = _yukle(yol)["domain"].replace(".", "_").replace("-", "_")
        assert yol.stem == beklenen, f"{yol.name} ≠ {beklenen}.yaml"


def test_tum_seciciler_gecerli_css():
    from bs4 import BeautifulSoup
    corba = BeautifulSoup("<html></html>", "lxml")
    for yol in _kural_dosyalari():
        kural_ = _yukle(yol)
        for anahtar in SECICI_ANAHTARLARI:
            deger = kural_.get(anahtar)
            if not deger:
                continue
            for parca in str(deger).split(","):
                # Geçersizse SoupSieve burada patlar — sessiz atlama yerine
                # test kırmızısı, aranan davranış budur.
                corba.select(parca.strip())


def test_bilinmeyen_anahtar_yok():
    for yol in _kural_dosyalari():
        fazla = set(_yukle(yol)) - BILINEN_ANAHTARLAR
        assert not fazla, f"{yol.name}: kod bu anahtarları okumuyor: {fazla}"


def test_kanonik_yol_kaliplari_derlenir_ve_bicimle_tutarli():
    """Kanonik URL kalıbı bozuksa aynı ürün iki kayda düşer ve fiyat geçmişi
    ikiye bölünür — K16'nın ihlali, üründeki en pahalı sessiz hata."""
    import re
    for yol in _kural_dosyalari():
        kural_ = _yukle(yol)
        kalip, bicim = (kural_.get("kanonik_yol_kalibi"),
                        kural_.get("kanonik_yol_bicimi"))
        if not kalip:
            assert not bicim, f"{yol.name}: `bicim` var ama `kalibi` yok"
            continue
        derlenmis = re.compile(kalip)        # bozuksa burada patlar
        if bicim:
            # `\1` yazıp tek grup tanımlamamak sessizce ham yolu bırakmaz,
            # `expand` çağrısında patlar — ama ancak o siteden link eklenince.
            for numara in re.findall(r"\\(\d+)", bicim):
                assert int(numara) <= derlenmis.groups, (
                    f"{yol.name}: biçim \\{numara} istiyor, kalıpta "
                    f"{derlenmis.groups} grup var")


def test_toplayicida_pazar_seçicileri_tam():
    """Eksik `saticilar_secici`, koruma ölçütünü (pazar_aykiri) SESSİZCE
    kapatır: geçmişi olmayan üründe tek uyarı işaretimiz odur."""
    for yol in _kural_dosyalari():
        kural_ = _yukle(yol)
        if not kural_.get("toplayici"):
            continue
        assert kural_.get("fiyat_secici"), f"{yol.name}: toplayıcı, fiyat yok"
        # cimri.com'da liste seçicisi henüz yazılmadı; eksikliği görünür
        # kılmak için `notlar` zorunlu — sessizce eksik kalmasın.
        if not kural_.get("saticilar_secici"):
            assert kural_.get("notlar"), (
                f"{yol.name}: satıcı listesi seçicisi yok ve `notlar` boş — "
                "koruma ölçütü sessizce devre dışı")


def test_bozuk_kural_dosyasi_sessizce_atlanmaz(tmp_path, monkeypatch):
    """Girinti hatası yüzünden atlanan dosya, dışarıdan "site okumuyor" diye
    görünür ve kimse kural dosyasına bakmaz. Süreci düşürmeyelim ama log'a
    düşsün: aranacak yeri söyleyen tek şey o satır.

    Olay stdout'tan değil `capture_logs` ile okunuyor: `gunluk.kur()` bir kez
    çalıştıktan sonra structlog akışı sabitliyor ve capsys hiçbir şey görmüyor
    — testin sırası değişince sessizce yeşile dönüyordu.
    """
    from structlog.testing import capture_logs

    from keepmoney import siteler as s

    (tmp_path / "bozuk_com.yaml").write_text(
        "domain: 'bozuk.com'\n  fiyat_secici: ']['\n", encoding="utf-8")
    (tmp_path / "adsiz_com.yaml").write_text("satici: 'Adsız'\n",
                                             encoding="utf-8")
    (tmp_path / "saglam_com.yaml").write_text(
        "domain: 'saglam.com'\nsatici: 'Sağlam'\n", encoding="utf-8")
    monkeypatch.setattr(s, "SITELER_DIZINI", tmp_path)
    s._tum_kurallar.cache_clear()
    try:
        with capture_logs() as kayitlar:
            kurallar = s._tum_kurallar()
        assert set(kurallar) == {"saglam.com"}          # süreç düşmedi
        olaylar = {(k["event"], k.get("dosya")) for k in kayitlar}
        assert ("site_kurali_bozuk", "bozuk_com.yaml") in olaylar
        assert ("site_kurali_domainsiz", "adsiz_com.yaml") in olaylar
    finally:
        s._tum_kurallar.cache_clear()                   # gerçek kurallara dön

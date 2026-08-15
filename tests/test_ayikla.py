"""Çıkarıcı testleri — gerçek Türk e-ticaret sayfa kalıpları üzerinden."""
from keepmoney.ayikla import (
    baslik_ayikla,
    cikar,
    engel_mi,
    fiyat_ayikla,
    olu_mu,
    puan_ayikla,
)


def sayfa(govde: str, baslik: str = "Ürün Sayfası") -> str:
    return f"<html><head><title>{baslik}</title></head><body>{govde}</body></html>"


def ld(icerik: str) -> str:
    return f'<script type="application/ld+json">{icerik}</script>'


# ---------- güven zinciri sırası ----------

def test_jsonld_once_gelir():
    html = sayfa(
        ld('{"@type":"Product","offers":{"price":"52999.90","priceCurrency":"TRY"}}')
        + '<span class="product-price">99,00 TL</span>'
    )
    assert fiyat_ayikla(html) == (52999.90, "json-ld")


def test_jsonld_yoksa_siteye_ozel_secici():
    html = sayfa('<span class="prc-dsc">2.798,80 ₺</span>')
    assert fiyat_ayikla(html, {"fiyat_secici": "span.prc-dsc"}) == (2798.80, "secici")


def test_genel_secici_config_olmadan():
    html = sayfa('<div class="product-price">1.499,00 TL</div>')
    assert fiyat_ayikla(html) == (1499.0, "secici")


def test_meta_etiketi():
    html = '<html><head><meta property="og:price:amount" content="3499.00">' \
           '</head><body>fiyat yok</body></html>'
    assert fiyat_ayikla(html) == (3499.0, "meta")


def test_govde_regex_son_care():
    html = sayfa("<p>Bu ürün 12.345,67 TL fiyatla satışta</p>")
    assert fiyat_ayikla(html) == (12345.67, "regex")


def test_hicbir_yontem_bulamazsa():
    assert fiyat_ayikla(sayfa("<p>stokta yok</p>")) == (None, "yok")


# ---------- gerçek vaka korumaları ----------

def test_jsonld_try_disi_para_birimini_reddeder():
    """Bazı siteler USD fiyat da gömüyor; 1.299 USD, 1.299 TL sanılıyordu."""
    html = sayfa(ld('{"@type":"Product","offers":'
                    '{"price":"1299.00","priceCurrency":"USD"}}'))
    _fiyat, guven = fiyat_ayikla(html)
    assert guven != "json-ld"


def test_metin_alani_yoksa_regex_atlanir():
    """KRİTİK: ana fiyat bloğu sayfada yoksa (stok tükendi), regex sponsorlu
    ürün karuselinin fiyatını ana fiyat sanıyordu. Kapsam yoksa 'yok' de."""
    html = sayfa('<div id="oneriler">Benzer ürün: 4.999,00 TL</div>')
    assert fiyat_ayikla(html, {"metin_alani": "#anaKolon"}) == (None, "yok")


def test_metin_alani_varsa_icinde_arar():
    html = sayfa('<div id="anaKolon">Fiyat 8.750,00 TL</div>'
                 '<div id="oneriler">Benzer: 999,00 TL</div>')
    assert fiyat_ayikla(html, {"metin_alani": "#anaKolon"}) == (8750.0, "regex")


def test_bozuk_jsonld_cokmez():
    html = sayfa(ld("{bozuk json,,,") + '<span class="price">750,00 TL</span>')
    assert fiyat_ayikla(html) == (750.0, "secici")


def test_ic_ice_jsonld_object_icinde():
    """mediamarkt gibi siteler Product'ı BuyAction.object içine gömer."""
    html = sayfa(ld('{"@type":"BuyAction","object":{"@type":"Product",'
                    '"offers":{"price":"15750.00","priceCurrency":"TRY"}}}'))
    assert fiyat_ayikla(html) == (15750.0, "json-ld")


def test_jsonld_graph_icinde():
    html = sayfa(ld('{"@graph":[{"@type":"WebPage"},{"@type":"Product",'
                    '"offers":{"price":"999.90","priceCurrency":"TRY"}}]}'))
    assert fiyat_ayikla(html) == (999.90, "json-ld")


# ---------- puan / yorum ----------

def test_puan_ve_yorum_sayisi():
    html = sayfa(ld('{"@type":"Product","aggregateRating":'
                    '{"ratingValue":"4.5","reviewCount":"1284"}}'))
    assert puan_ayikla(html) == (4.5, 1284)


def test_puan_virgullu_deger():
    html = sayfa(ld('{"@type":"Product","aggregateRating":{"ratingValue":"4,7"}}'))
    puan, _ = puan_ayikla(html)
    assert puan == 4.7


def test_puan_100luk_sistemi_normalize_eder():
    html = sayfa(ld('{"@type":"Product","aggregateRating":'
                    '{"ratingValue":"90","ratingCount":"50"}}'))
    assert puan_ayikla(html) == (4.5, 50)


def test_puan_yoksa_none():
    assert puan_ayikla(sayfa("<p>ürün</p>")) == (None, None)


# ---------- başlık ----------

def test_baslik_og_title_onceligi():
    html = '<html><head><meta property="og:title" content="Palit RTX 5070 Ti 16GB">' \
           '<title>Palit RTX 5070 Ti | Mağaza</title></head><body><h1>Başka</h1></body></html>'
    assert baslik_ayikla(html) == "Palit RTX 5070 Ti 16GB"


def test_baslik_site_adi_kirpilir():
    html = sayfa("<p>x</p>", baslik="Kingston Beast 32GB DDR5 | Hepsiburada")
    assert baslik_ayikla(html) == "Kingston Beast 32GB DDR5"


def test_baslik_kisa_parcayi_kirpmaz():
    """'RTX 4070 - 12GB' gibi adlarda ayraçtan öncesi çok kısaysa kırpma."""
    html = sayfa("<p>x</p>", baslik="RTX - 12GB Ekran Kartı")
    assert baslik_ayikla(html) == "RTX - 12GB Ekran Kartı"


# ---------- engel / ölü sayfa ----------

def test_engel_basliktan():
    assert engel_mi(sayfa("<p>...</p>", baslik="Just a moment...")) is True


def test_engel_govdeden():
    assert engel_mi(sayfa("<p>Erişim engellendi</p>")) is True


def test_normal_sayfa_engelli_degil():
    assert engel_mi(sayfa("<p>Sepete ekle</p>")) is False


def test_olu_http_kodundan():
    assert olu_mu(sayfa("<p>x</p>"), 404) is True
    assert olu_mu(sayfa("<p>x</p>"), 200) is False


def test_olu_basliktan():
    assert olu_mu(sayfa("<p>x</p>", baslik="Sayfa bulunamadı")) is True


# ---------- birleşik çıkarım ----------

def test_cikar_hepsini_toplar():
    html = sayfa(ld('{"@type":"Product","name":"Ürün",'
                    '"offers":{"price":"25999.00","priceCurrency":"TRY"},'
                    '"aggregateRating":{"ratingValue":"4.3","reviewCount":"87"}}'),
                 baslik="Kingston Beast 32GB | Mağaza")
    c = cikar(html)
    assert c.fiyat == 25999.0
    assert c.guven == "json-ld"
    assert c.puan == 4.3
    assert c.yorum_sayisi == 87
    assert c.baslik == "Kingston Beast 32GB"
    assert c.engelli is False and c.olu is False


def test_cikar_olu_sayfada_fiyat_okumaz():
    c = cikar(sayfa('<span class="price">1,00 TL</span>'), http_kodu=404)
    assert c.olu is True
    assert c.fiyat is None


def test_cikar_engelli_sayfada_fiyat_okumaz():
    c = cikar(sayfa('<span class="price">1,00 TL</span>', baslik="Captcha"))
    assert c.engelli is True
    assert c.fiyat is None

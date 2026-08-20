"""Çıkarıcı testleri — gerçek Türk e-ticaret sayfa kalıpları üzerinden."""
from keepmoney.ayikla import (
    baslik_ayikla,
    cikar,
    engel_mi,
    fiyat_ayikla,
    olu_mu,
    pazar_ayikla,
    puan_ayikla,
    stok_yok_mu,
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


# ---------- yapısal engel imzaları ----------
# Bu blok ilk GERÇEK link denemesinden geldi: Amazon'un captcha sayfası
# görünür metninde hiçbir engel kelimesi taşımıyor (başlığı yalnızca
# "Amazon.com.tr") ve sistem onu "fiyat okunamadı" diye raporladı. Yanlış
# teşhis yanlış çözüme götürür — seçici yazmaya çalışırsın, oysa geri
# çekilmen gerekir; ayrıca engel sayılmadığı için throttle cezası ve
# KAYNAK_BOZUK uyarısı da devreye girmez.

def test_amazon_captcha_sayfasi_engel_sayilir():
    """Görünür metinde tek bir engel kelimesi yok — imza formun hedefinde."""
    html = sayfa(
        '<form method="get" action="/errors/validateCaptcha">'
        '<input name="amzn" value="x"></form>', baslik="Amazon.com.tr")
    assert engel_mi(html) is True


def test_datadome_engel_sayilir():
    html = sayfa('<script src="https://ct.captcha-delivery.com/c.js"></script>')
    assert engel_mi(html) is True


def test_cloudflare_challenge_engel_sayilir():
    html = sayfa('<script src="/cdn-cgi/challenge-platform/h/b/orchestrate"></script>')
    assert engel_mi(html) is True


def test_urun_sayfasindaki_robot_kelimesi_engel_saymaz():
    """YANLIŞ POZİTİF KORUMASI: 'robot süpürge' bir üründür, engel değil.

    Ham HTML'de kelime aramanın bariz riski budur; imzalar bu yüzden dile
    bağlı olmayan yol/alan adı kalıpları — serbest kelimeler değil.
    """
    html = sayfa('<h1>Robot Süpürge</h1><span class="a-offscreen">4.999 TL</span>')
    assert engel_mi(html) is False


def test_engel_sayfasindan_fiyat_okunmaya_calisilmaz():
    """Uçtan uca: `cikar` engelli bayrağını kaldırmalı, fiyat UYDURMAMALI."""
    html = sayfa(
        '<form action="/errors/validateCaptcha"></form>'
        '<span>Sadece 99,90 TL</span>', baslik="Amazon.com.tr")
    c = cikar(html)
    assert c.engelli is True
    assert c.fiyat is None


def test_olu_http_kodundan():
    assert olu_mu(sayfa("<p>x</p>"), 404) is True
    assert olu_mu(sayfa("<p>x</p>"), 200) is False


def test_olu_basliktan():
    assert olu_mu(sayfa("<p>x</p>", baslik="Sayfa bulunamadı")) is True


def test_olu_yumusak_404():
    """HTTP 200 dönen 404 sayfası.

    Gerçek bir denemede vatanbilgisayar.com kaldırılmış bir ürüne 1 KB'lık
    "404 - File or directory not found." başlıklı bir sayfa döndürdü — ama
    HTTP 200 ile. Kaydedilen HTML'de HTTP kodu yok, yani tek işaret başlık.
    Yakalanmazsa ölü link "fiyat okunamadı" diye raporlanıyor ve düzeltilecek
    bir ayıklayıcı hatası sanılıyor.
    """
    html = sayfa("<h1>Server Error</h1>",
                 baslik="404 - File or directory not found.")
    assert olu_mu(html) is True


def test_olu_normal_urun_sayfasini_isaretlemez():
    """Yanlış pozitif pahalı: ölü sayılan ürün bir daha taranmaz.

    "not found" kısa ve genel bir kalıp; bu yüzden yalnızca <title> içinde
    aranıyor. Gövdede geçmesi (yorum, JS metni) ürünü öldürmemeli.
    """
    html = sayfa("<p>Aradığınız sayfa bulunamadı diyen bir yorum</p>"
                 "<script>if(!el) throw new Error('not found')</script>",
                 baslik="MSI 271QP QD-OLED Gaming Monitör")
    assert olu_mu(html) is False


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


def test_captcha_imzasi_yol_onekinden_bagimsiz():
    """Amazon captcha formunun hedefi siteye/sürüme göre değişiyor:
    `/errors/validateCaptcha`, `/gp/errors/validateCaptcha`, hatta göreli
    `validateCaptcha`. İmza yol önekine bağlanırsa sessizce ıskalanır —
    gerçek bir koşuda tam olarak bu oldu."""
    for hedef in ("/errors/validateCaptcha", "/gp/errors/validateCaptcha",
                  "validateCaptcha", "https://www.amazon.com.tr/errors/validateCaptcha"):
        html = sayfa(f'<form action="{hedef}"></form>', baslik="Amazon.com.tr")
        assert engel_mi(html) is True, hedef


# ---------- ürün adı: sessiz yanlış okuma ----------
# Gerçek bir Amazon sayfasında ürün adı "Ürün özeti, temel ürün bilgilerini
# sunar…" diye okundu — sayfanın ilk <h1>i bir erişilebilirlik başlığıydı ve
# doğru <title>ı gölgeliyordu. Fiyat doğru olsa bile kullanıcı listesinde
# tanımadığı bir ad görüyor ve neyi izlediğini anlamıyordu.

GORUNMEZ_H1_SAYFASI = (
    '<html><head><title>HyperX Cloud III S : Amazon.com.tr</title></head>'
    '<body><h1 class="a-size-base a11y-header">Ürün özeti, temel ürün '
    'bilgilerini sunar</h1>'
    '<span id="productTitle">HyperX Cloud III S Wireless</span></body></html>')


def test_gorunmez_h1_urun_adi_sayilmaz():
    """Ekran okuyucu başlıkları asla ürün adı değildir."""
    assert baslik_ayikla(GORUNMEZ_H1_SAYFASI) == "HyperX Cloud III S"


def test_site_baslik_secicisi_oncelikli():
    ad = baslik_ayikla(GORUNMEZ_H1_SAYFASI, {"baslik_secici": "#productTitle"})
    assert ad == "HyperX Cloud III S Wireless"


def test_gorunur_h1_hala_kullanilir():
    """Yanlış pozitif olmasın: normal sayfalarda h1 doğru kaynak."""
    html = ('<html><head><title>X | Mağaza</title></head>'
            '<body><h1 class="product-name">Ekran Kartı RTX 5080</h1></body></html>')
    assert baslik_ayikla(html) == "Ekran Kartı RTX 5080"


def test_gecersiz_baslik_secicisi_zinciri_kesmez():
    html = '<html><head><title>Ürün Adı Buradadır</title></head><body></body></html>'
    assert baslik_ayikla(html, {"baslik_secici": "((("}) == "Ürün Adı Buradadır"


# ---------- stokta yok: arıza değil, olgu ----------
# Gerçek denemede 13 linkin 2'si stoktan düşmüştü. Sistem ikisini de "fiyat
# okunamadı" diye raporluyor, tanı aracı da "seçici güncellenmeli" diyerek
# asla tutmayacak bir seçici yazmaya gönderiyordu.

def test_jsonld_availability_stok_yok():
    html = sayfa(ld('{"@type":"Product","offers":'
                    '{"availability":"https://schema.org/OutOfStock"}}'))
    assert stok_yok_mu(html) is True


def test_mikroveri_availability_stok_yok():
    html = sayfa('<link itemprop="availability" href="https://schema.org/SoldOut">')
    assert stok_yok_mu(html) is True


def test_serbest_metin_yalnizca_kapsam_icinde_sayilir():
    """1,5 MB'lık sayfada 'stokta yok' sponsorlu kutuda geçebilir. Tüm belgede
    aramak, KIRIK bir ayıklayıcıyı 'ürün tükenmiş' diye maskelerdi."""
    html = sayfa('<div id="oneriler">Bu ürün stokta yok</div>'
                 '<div id="anaKolon">Sepete ekle</div>')
    assert stok_yok_mu(html, {"metin_alani": "#anaKolon"}) is False
    assert stok_yok_mu(html, {"metin_alani": "#oneriler"}) is True


def test_kapsam_tanimsizsa_serbest_metin_aranmaz():
    """Kapsamı olmayan sitede metin araması yapmak, maskeleme riskini
    kontrolsüz bırakırdı."""
    html = sayfa("<p>Şu anda mevcut değil</p>")
    assert stok_yok_mu(html) is False


def test_stok_var_olan_sayfa_stok_yok_sayilmaz():
    html = sayfa(ld('{"@type":"Product","offers":'
                    '{"availability":"https://schema.org/InStock",'
                    '"price":"1500.00","priceCurrency":"TRY"}}'))
    assert stok_yok_mu(html) is False


def test_fiyat_bulunursa_stok_yok_ISARETLENMEZ():
    """Sıralama kasıtlı: bulunan fiyat her zaman kazanır. Yanlış bir 'stokta
    yok' tespiti, satılan ürünün fiyatını kaydetmemize engel olurdu."""
    html = sayfa(ld('{"@type":"Product","offers":'
                    '{"availability":"https://schema.org/OutOfStock",'
                    '"price":"1500.00","priceCurrency":"TRY"}}'))
    c = cikar(html)
    assert c.fiyat == 1500.0
    assert c.stok_yok is False


def test_cikar_stok_yok_isaretler():
    html = sayfa(ld('{"@type":"Product","offers":'
                    '{"availability":"https://schema.org/OutOfStock"}}'))
    c = cikar(html)
    assert c.stok_yok is True
    assert c.fiyat is None
    assert c.olu is False and c.engelli is False


# ---------- pazar derinliği (toplayıcı sayfaları) ----------

AKAKCE_SAYFASI = """<html><head><title>RTX 5070 Ti fiyatları</title></head><body>
  <span class="pt_v8">38.999,00 TL</span>
  <ul id="PL">
    <li><img alt="UcuzSepet"><span class="pt_v8">38.999,00 TL</span></li>
    <li><img alt="Vatan"><span class="pt_v8">41.500,00 TL</span></li>
    <li><img alt="İtopya"><span class="pt_v8">42.750,00 TL</span></li>
  </ul></body></html>"""

TOPLAYICI = {"toplayici": True, "fiyat_secici": "span.pt_v8",
             "satici_secici": "#PL > li:first-child img[alt]",
             "saticilar_secici": "#PL > li",
             "saticilar_fiyat_secici": "span.pt_v8"}


def test_pazar_derinligi_okunur():
    ad, sayi, ikinci = pazar_ayikla(AKAKCE_SAYFASI, TOPLAYICI)
    assert ad == "UcuzSepet"          # metin yok, alt niteliğinden
    assert sayi == 3
    assert ikinci == 41500.0


def test_toplayici_olmayan_sitede_pazar_okunmaz():
    """'Pazar' kavramı yalnızca toplayıcıda var; mağaza sayfasında yok."""
    assert pazar_ayikla(AKAKCE_SAYFASI, {"saticilar_secici": "#PL > li"}) \
        == (None, None, None)


def test_tek_saticida_ikinci_fiyat_yok():
    html = AKAKCE_SAYFASI.replace(
        '<li><img alt="Vatan"><span class="pt_v8">41.500,00 TL</span></li>', "")
    html = html.replace(
        '<li><img alt="İtopya"><span class="pt_v8">42.750,00 TL</span></li>', "")
    _ad, sayi, ikinci = pazar_ayikla(html, TOPLAYICI)
    assert sayi == 1
    assert ikinci is None


def test_secici_tanimsizsa_sessizce_atlanir():
    """Kural dosyası eksikse çıkarım ÇÖKMEMELİ — pazar verisi opsiyoneldir."""
    assert pazar_ayikla(AKAKCE_SAYFASI, {"toplayici": True}) == (None, None, None)


def test_bozuk_secici_cikarimi_dusurmez():
    kural = dict(TOPLAYICI, saticilar_secici="((( bozuk")
    ad, sayi, _ikinci = pazar_ayikla(AKAKCE_SAYFASI, kural)
    assert ad == "UcuzSepet"          # diğer alanlar çalışmaya devam etmeli
    assert sayi is None


def test_cikar_pazar_verisini_tasir():
    c = cikar(AKAKCE_SAYFASI, TOPLAYICI)
    assert c.fiyat == 38999.0
    assert c.satici_adi == "UcuzSepet"
    assert c.satici_sayisi == 3
    assert c.ikinci_fiyat == 41500.0

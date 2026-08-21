"""Kanonik URL testleri — GERÇEK linklerle.

NEDEN AYRI DOSYA: Buradaki her URL, tarayıcıdan kopyalanmış gerçek bir
linktir. Mevcut testler temiz, elle yazılmış URL'ler kullanıyordu ve bu
yüzden ciddi bir hatayı kaçırdılar: Amazon takip verisini sorgu dizesine
DEĞİL yolun içine gömüyor (`/dp/ASIN/ref=.../262-370...`), dolayısıyla aynı
ürünün iki linki iki ayrı kanonik URL üretiyordu.

Sonucu şuydu: iki kullanıcı aynı ürünü farklı yerlerden eklediğinde iki ayrı
`Source` satırı oluşuyor, küresel fiyat geçmişi ikiye bölünüyor ve "90 günün
dibi" yanlış hesaplanıyordu. Ürünün temel vaadi olan küresel hafıza sessizce
bozuluyordu (bkz. MIMARI.md K16).

İlk gerçek link denemesinde yakalandı. Ders: sentetik girdiyle yazılmış test,
sentetik girdinin doğruluğunu ölçer.
"""
from __future__ import annotations

import pytest

from keepmoney.servisler.izleme import url_normalize

# Tarayıcıdan kopyalanmış gerçek linkler.
AMAZON_ONERIDEN = (
    "https://www.amazon.com.tr/XG27AQDMGR-monit%C3%B6r%C3%BC-Glossy-s%C3%BCresi"
    "-DisplayPort/dp/B09CD32DNH/ref=pd_lpo_d_sccl_4/262-3702812-9941328"
    "?pd_rd_w=6aZNk&content-id=amzn1.sym.be428933&pf_rd_p=be428933"
    "&pf_rd_r=XM8DFDMZ2XN7D8F500V4&pd_rd_wg=YWtbr&pd_rd_r=c43de982"
    "&pd_rd_i=B0GZPNQ28H&th=1")

AMAZON_DOGRUDAN = (
    "https://www.amazon.com.tr/XG27AQDMGR-monit%C3%B6r%C3%BC-Glossy-s%C3%BCresi"
    "-DisplayPort/dp/B09CD32DNH")

HEPSIBURADA_AKAKCEDEN = (
    "https://www.hepsiburada.com/logitech-g-g309-lightspeed-25-600-dpi-kablosuz"
    "-siyah-oyuncu-mouse-910-007200-p-HBCV00006RVYU8?magaza=UcuzSepet"
    "&utm_source=akakce&utm_medium=cpc&utm_campaign=sc%3Ahb-ecom"
    "&wt_pc=akakce&adj_t=1fmpah5v_1fmqteof&adj_campaign=akakce&v=1.66.4")


def test_amazon_ayni_urun_ayni_kanonik_url():
    """ÜRÜNÜN TEMEL VAADİ: aynı ürün = aynı satır = tek fiyat geçmişi."""
    assert url_normalize(AMAZON_ONERIDEN) == url_normalize(AMAZON_DOGRUDAN)


def test_amazon_asin_korunur():
    """Kırpma agresif olmamalı — ürünü tanımlayan ASIN yolda kalmalı."""
    assert url_normalize(AMAZON_ONERIDEN).endswith("/dp/B09CD32DNH")


def test_amazon_yanlis_asin_sizmiyor():
    """`pd_rd_i` linkin GELDİĞİ ürünün ASIN'i — kanonik URL'ye karışmamalı."""
    assert "B0GZPNQ28H" not in url_normalize(AMAZON_ONERIDEN)


def test_hepsiburada_takip_parametreleri_temizlenir():
    kanonik = url_normalize(HEPSIBURADA_AKAKCEDEN)
    assert kanonik == (
        "https://hepsiburada.com/logitech-g-g309-lightspeed-25-600-dpi-"
        "kablosuz-siyah-oyuncu-mouse-910-007200-p-HBCV00006RVYU8")
    for iz in ("magaza", "utm_", "wt_pc", "adj_", "v="):
        assert iz not in kanonik


@pytest.mark.parametrize("ham", [AMAZON_ONERIDEN, HEPSIBURADA_AKAKCEDEN])
def test_kanoniklestirme_sabit_noktadir(ham):
    """İki kez uygulamak bir kez uygulamakla aynı olmalı.

    Değilse kanonik URL'nin 'kanonik' olduğu iddiası çöker: aynı kayıt farklı
    yollardan farklı anahtarlar üretir.
    """
    bir = url_normalize(ham)
    assert url_normalize(bir) == bir


def test_anlamli_sorgu_parametreleri_korunur():
    """Kırpma körü körüne değil: bazı sitelerde varyant sorguda taşınıyor."""
    kanonik = url_normalize("https://ornek.com/urun?varyant=mavi&utm_source=x")
    assert "varyant=mavi" in kanonik
    assert "utm_source" not in kanonik


def test_ref_icermeyen_yol_bozulmaz():
    url = "https://vatanbilgisayar.com/logitech-mx-master-3s.html"
    assert url_normalize(url) == url


def test_yol_ortasindaki_ref_sonrasi_tamamen_atilir():
    """`ref=` parçasını atıp sonrasını bırakmak YETMEZ — oturum kimliği kalır
    ve kanonik URL yine kullanıcıya göre değişir."""
    kanonik = url_normalize(
        "https://amazon.com.tr/x/dp/B01/ref=zg_bs/262-6227750-2475204")
    assert kanonik == "https://amazon.com.tr/x/dp/B01"


# ── Aynı ürüne giden iki geçerli adres ──────────────────────────
# Kullanıcının gerçek link listesinde yakalandı: aynı ASIN, iki farklı yol.
# Amazon ikisini de aynı ürüne çözüyor; biz iki ayrı kayda düşürüyorduk.

AMAZON_KISA = "https://www.amazon.com.tr/dp/B0BSLHZKB6?ref=ppx_yo2ov_dt_b_fed"
AMAZON_SLUGLU = (
    "https://www.amazon.com.tr/MSI-271QP-QD-OLED-Gaming-Monit%C3%B6r"
    "/dp/B0BSLHZKB6")


def test_slugsuz_ve_sluglu_adres_ayni_urun():
    """Öndeki metin insan için; Amazon onu yok sayıyor. Biz de saymalıyız —
    yoksa aynı ürün iki kayda düşer ve '90 günün dibi' yanlış hesaplanır."""
    assert url_normalize(AMAZON_KISA) == url_normalize(AMAZON_SLUGLU)
    assert url_normalize(AMAZON_KISA).endswith("/dp/B0BSLHZKB6")


def test_gp_product_bicimi_de_ayni_kanonige_duser():
    assert url_normalize("https://www.amazon.com.tr/gp/product/B0BSLHZKB6") \
        == url_normalize(AMAZON_KISA)


def test_farkli_asin_farkli_urun_kalir():
    """Kırpma AŞIRIYA KAÇMAMALI: iki ürünü birleştirmek, ayırmaktan kötüdür —
    fiyat geçmişleri karışır ve geri alınamaz."""
    a = url_normalize("https://www.amazon.com.tr/x/dp/B0BSLHZKB6")
    b = url_normalize("https://www.amazon.com.tr/x/dp/B09CD32DNH")
    assert a != b


def test_kanonik_kalibi_olmayan_site_etkilenmez():
    """Kural tanımlı değilse yol OLDUĞU GİBİ kalmalı; başka sitelerde slug
    ürünün kimliğinin parçası olabilir."""
    url = "https://vatanbilgisayar.com/hyperx-cloud-iii-s-kulaklik.html"
    assert url_normalize(url) == url


def test_akakce_yolu_bozulmuyor():
    """Toplayıcı linkleri kimliği ',<id>.html' ile taşıyor."""
    url = ("https://www.akakce.com/monitor/en-ucuz-msi-mag-271qp-qd-oled"
           "-fiyati,1077309366.html")
    assert url_normalize(url).endswith("fiyati,1077309366.html")


# ── Google Shopping tıklama kimliği ─────────────────────────────
# Gerçek bir link listesinde yakalandı:
#   .../products/vxe-r1-kablosuz-mouse?srsltid=AfmBOoqy...&variant=475...
# `srsltid` HER TIKLAMADA değişiyor. Atılmazsa aynı ürünün Google'dan gelen
# iki linki iki ayrı kanonik URL üretir; ürün ikiye bölünür, aynı sayfa iki
# kez taranır ve fiyat geçmişi parçalanır.

def test_google_tiklama_kimligi_atilir():
    a = ("https://wraithesports.com/products/vxe-r1-kablosuz-mouse"
         "?srsltid=AfmBOoqyVmp6aK4Bup1VjyQyQ8qLgvuMlmTMBgiK8hPWvqZ68znZqDXp"
         "&variant=47501043728577")
    b = ("https://wraithesports.com/products/vxe-r1-kablosuz-mouse"
         "?srsltid=BAMBASKAtiklamaKimligi999&variant=47501043728577")
    assert url_normalize(a) == url_normalize(b)
    assert "srsltid" not in url_normalize(a)


def test_shopify_varyanti_KORUNUR():
    """Karşı test — ve bu daha tehlikeli yön.

    Shopify'da varyant AYRI BİR ÜRÜNDÜR (farklı renk/boyut, farklı fiyat).
    `variant` atılsaydı iki ayrı ürün TEK kayda birleşirdi: bölünmekten
    beter, çünkü yanlış ürünün fiyatı doğru ürünün geçmişine yazılır.
    """
    tekil = "https://wraithesports.com/products/vxe-r1?variant=47501043728577"
    baska = "https://wraithesports.com/products/vxe-r1?variant=99999999999999"
    assert url_normalize(tekil) != url_normalize(baska)
    assert "variant=47501043728577" in url_normalize(tekil)


@pytest.mark.parametrize("parametre", [
    "gad_source", "gbraid", "wbraid", "msclkid", "ttclid", "yclid",
])
def test_diger_reklam_tiklama_kimlikleri_de_atilir(parametre):
    """Aynı sınıftan olan hepsi birden eklendi; biri unutulursa sessizce böler."""
    url = f"https://magaza.com/urun-x?{parametre}=abc123XYZ"
    assert url_normalize(url) == "https://magaza.com/urun-x"


# ── Kimlik yolda ise sorgu dizesi tümüyle atılır ──────────────────
#
# GERÇEK LİNK LİSTESİNDE YAKALANDI: çöp parametre listesi bir KARA LİSTE ve
# her zaman geriden geliyor. Amazon'un arama/oturum parametreleri listede
# yoktu ve aynı ASIN ÜÇ ayrı kanonik URL üretiyordu — yani aynı ürün üç kez
# taranıp fiyat geçmişi üçe bölünüyordu (K16 ihlali).


def test_ayni_asin_farkli_arama_parametreleriyle_tek_urun():
    """Üç biçim de aynı kanonik URL'ye düşmeli."""
    bicimler = [
        "https://www.amazon.com.tr/dp/B0DVGVZZYY",
        "https://www.amazon.com.tr/dp/B0DVGVZZYY?ie=UTF8",
        "https://www.amazon.com.tr/dp/B0DVGVZZYY?tag=akakcetr-21&linkCode=ogi&th=1",
        # Arama sonucundan gelen hâli: bu parametrelerin HİÇBİRİ çöp
        # listesinde yoktu.
        ("https://www.amazon.com.tr/Prime-PRIME-RTX5070TI/dp/B0DVGVZZYY/ref=sr_1_2"
         "?__mk_tr_TR=ÅMÅŽÕÑ&crid=160AGU6GVP7IV&dib_tag=se&keywords=Asus"
         "&qid=1784717962&s=computers&sprefix=asus&sr=1-2&th=1"),
    ]
    kanonikler = {url_normalize(u) for u in bicimler}
    assert kanonikler == {"https://amazon.com.tr/dp/B0DVGVZZYY"}


def test_gp_product_ve_dp_arama_parametreleriyle_de_birlesir():
    a = url_normalize(
        "https://www.amazon.com.tr/gp/product/B0B7CMZ3QH/ref=sw_img_1?smid=&th=1")
    b = url_normalize(
        "https://www.amazon.com.tr/WD_BLACK-SN850X/dp/B0B7CMZ3QH/ref=sr_1_1"
        "?adgrpid=121291478378&dib_tag=se&keywords=wd+black&qid=1783204141&sr=8-1")
    assert a == b == "https://amazon.com.tr/dp/B0B7CMZ3QH"


def test_kimlik_tanimsiz_sitede_sorgu_KORUNUR():
    """Kural yoksa sorgu atılmaz: orada bir parametre gerçekten ürünü
    belirleyebilir. Shopify'da `variant` AYRI bir üründür; atmak iki ayrı
    ürünü birleştirirdi — bölmekten beter."""
    assert url_normalize(
        "https://wraithesports.com/products/vxe-r1?srsltid=ABC&variant=475"
    ) == "https://wraithesports.com/products/vxe-r1?variant=475"


def test_kimlik_tanimsiz_sitede_saticiya_dokunulmaz():
    """idefix'te `vendorId` satıcıyı belirtiyor: farklı satıcı = farklı fiyat."""
    assert url_normalize(
        "https://www.idefix.com/asus-p-6313910?vendorId=20207&utm_source=akakce"
    ) == "https://idefix.com/asus-p-6313910?vendorId=20207"


def test_kalip_tutmayan_amazon_yolunda_sorgu_korunur():
    """Şablon eşleşmezse kimlik BELİRLENMEMİŞTİR; sorguyu atmak, farklı iki
    sayfayı yanlışlıkla birleştirme riski taşır."""
    sonuc = url_normalize("https://www.amazon.com.tr/s?k=ekran+karti")
    assert "k=ekran+karti" in sonuc

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

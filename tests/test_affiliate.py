"""Ortaklık linki testleri.

Buradaki testler bir gelir özelliğinden çok, bir DÜRÜSTLÜK sözleşmesini
koruyor: saklanan URL kirlenmemeli, başkasının kodu ezilmemeli ve ortaklık
"en ucuz" seçimini etkilememeli.
"""
from keepmoney import affiliate, siteler
from keepmoney.karar import KaynakOkumasi, en_iyi_kaynak


def test_kural_yoksa_url_degismez():
    url = "https://bilinmeyen-magaza.com/urun/x"
    assert affiliate.cikis_linki(url) == (url, False)


def test_kural_varsa_parametre_eklenir(monkeypatch):
    monkeypatch.setattr(
        siteler, "kural",
        lambda _: {"ortaklik": {"parametre": "tag", "deger": "keepmoney-21"}})
    link, var = affiliate.cikis_linki("https://magaza.com/urun/x")
    assert var is True
    assert "tag=keepmoney-21" in link


def test_mevcut_sorgu_parametreleri_korunur(monkeypatch):
    monkeypatch.setattr(
        siteler, "kural",
        lambda _: {"ortaklik": {"parametre": "tag", "deger": "km-21"}})
    link, _ = affiliate.cikis_linki("https://magaza.com/u?renk=siyah")
    assert "renk=siyah" in link
    assert "tag=km-21" in link


def test_baskasinin_ortaklik_kodu_ezilmez(monkeypatch):
    """Başkasının kodunu çalmak, programdan atılma sebebidir."""
    monkeypatch.setattr(
        siteler, "kural",
        lambda _: {"ortaklik": {"parametre": "tag", "deger": "km-21"}})
    url = "https://magaza.com/u?tag=baskasi-99"
    link, var = affiliate.cikis_linki(url)
    assert link == url
    assert var is False


def test_eksik_yapilandirma_yok_sayilir(monkeypatch):
    """Yarım kural (değer yok) ortaklık sayılmaz — bozuk link üretmektense
    hiç üretmemek doğru."""
    monkeypatch.setattr(siteler, "kural", lambda _: {"ortaklik": {"parametre": "tag"}})
    url = "https://magaza.com/u"
    assert affiliate.cikis_linki(url) == (url, False)


def test_ortaklik_en_ucuz_secimini_etkilemez():
    """TARAFSIZLIK: karar katmanı affiliate modülünü hiç tanımaz.
    Komisyonlu mağaza pahalıysa yine de seçilmez."""
    komisyonlu = KaynakOkumasi(url="https://komisyonlu.com/u",
                               host="komisyonlu.com", fiyat=1200)
    komisyonsuz = KaynakOkumasi(url="https://komisyonsuz.com/u",
                                host="komisyonsuz.com", fiyat=1100)
    assert en_iyi_kaynak([komisyonlu, komisyonsuz]).host == "komisyonsuz.com"


def test_saklanan_url_kirletilmez(monkeypatch):
    """Kanonik URL ortaklık etiketi taşımamalı — yoksa aynı ürün farklı
    etiketlerle farklı satırlara bölünür (K16 bozulur)."""
    from keepmoney.servisler.izleme import url_normalize

    monkeypatch.setattr(
        siteler, "kural",
        lambda _: {"ortaklik": {"parametre": "tag", "deger": "km-21"}})
    kanonik = url_normalize("https://magaza.com/urun/x")
    assert "tag=" not in kanonik

    cikis, _ = affiliate.cikis_linki(kanonik)
    assert "tag=km-21" in cikis
    assert url_normalize(kanonik) == kanonik      # kanonik hâlâ temiz

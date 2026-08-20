"""Toplayıcı arama testleri — gerçek ağ YOK.

Bu modülün en kritik özelliği yaptığı DEĞİL, YAPMADIĞI şey: aday bulur ama
hiçbir şeyi bağlamaz. "RTX 5070 Ti Prime" ile "Prime OC" ayrı ürünlerdir ve
otomatik eşleştirme, yanlış ürünün fiyatını doğru ürünün geçmişine yazar —
grafiğe işleyen, geri alınamayan, sessiz bir veri hatası.
"""
from __future__ import annotations

from keepmoney.cekici import Cekim
from keepmoney.toplayici import Oneri, _sonuclari_ayikla, ara

ARAMA_SAYFASI = """<html><body>
  <ul>
    <li><a href="/ekran-karti/en-ucuz-asus-rtx-5070-ti-prime-fiyati,1234567.html">
        Asus RTX 5070 Ti Prime 16GB</a></li>
    <li><a href="https://www.akakce.com/ekran-karti/msi-rtx-5070-fiyati,7654321.html">
        MSI RTX 5070 Ventus</a></li>
    <li><a href="/kategori/ekran-karti.html">Tüm ekran kartları</a></li>
    <li><a href="/ekran-karti/en-ucuz-asus-rtx-5070-ti-prime-fiyati,1234567.html?x=1">
        Asus RTX 5070 Ti Prime 16GB</a></li>
  </ul></body></html>"""


class _SahteCekici:
    def __init__(self, cekim: Cekim):
        self.cekim = cekim
        self.cagrilar: list[str] = []
        self.kurallar: list[dict | None] = []

    def cek(self, url: str, kural: dict | None = None) -> Cekim:
        self.cagrilar.append(url)
        self.kurallar.append(kural)
        return self.cekim


# ── Ayrıştırma ───────────────────────────────────────────────────

def test_urun_linkleri_url_kalibindan_bulunur():
    """Sayfa YAPISINA değil, Akakçe'nin değişmez URL kalıbına dayanıyoruz:
    CSS sınıfları değişse de `fiyati,<id>.html` değişmiyor."""
    oneriler = _sonuclari_ayikla(ARAMA_SAYFASI, 5)
    assert [o.ad for o in oneriler] == [
        "Asus RTX 5070 Ti Prime 16GB", "MSI RTX 5070 Ventus"]


def test_kategori_linkleri_elenir():
    for o in _sonuclari_ayikla(ARAMA_SAYFASI, 5):
        assert "fiyati," in o.url


def test_ayni_urun_tekrar_edilmez():
    """Sorgu parametreli ikinci link aynı ürüne gidiyor."""
    assert len(_sonuclari_ayikla(ARAMA_SAYFASI, 5)) == 2


def test_goreli_adres_mutlaklastirilir():
    assert _sonuclari_ayikla(ARAMA_SAYFASI, 5)[0].url.startswith(
        "https://www.akakce.com/")


def test_sorgu_parametreleri_atilir():
    for o in _sonuclari_ayikla(ARAMA_SAYFASI, 5):
        assert "?" not in o.url


def test_limit_uygulanir():
    assert len(_sonuclari_ayikla(ARAMA_SAYFASI, 1)) == 1


def test_adsiz_link_atlanir():
    """Ad olmadan kullanıcı doğru ürünü seçemez — göstermenin anlamı yok."""
    html = '<html><body><a href="/x-fiyati,1.html"></a></body></html>'
    assert _sonuclari_ayikla(html, 5) == []


def test_gorsel_baginda_ad_nitelikten_alinir():
    html = ('<html><body><a href="/x-fiyati,1.html" title="Asus RTX 5070">'
            '<img src="a.jpg"></a></body></html>')
    assert _sonuclari_ayikla(html, 5) == [
        Oneri(ad="Asus RTX 5070", url="https://www.akakce.com/x-fiyati,1.html")]


# ── Arama akışı ──────────────────────────────────────────────────

def test_arama_dogru_adresi_cagirir():
    c = _SahteCekici(Cekim(html=ARAMA_SAYFASI, http_kodu=200))
    ara(c, "Asus RTX 5070 Ti")
    assert c.cagrilar == ["https://www.akakce.com/arama/?q=Asus+RTX+5070+Ti"]


def test_arama_render_zorlamaz():
    """Maliyet kararı: arama sayfası sunucu HTML'inde geliyor. Bot duvarı
    çıkarsa çekim zinciri zaten kendiliğinden tarayıcıya yükseliyor — pahalı
    yol (Playwright, ~8 sn ve ~250 MB) yalnızca gerektiğinde ödensin."""
    c = _SahteCekici(Cekim(html=ARAMA_SAYFASI, http_kodu=200))
    ara(c, "x")
    assert c.kurallar == [{}]
    assert not c.kurallar[0].get("render")


def test_bos_sorgu_aga_cikmaz():
    c = _SahteCekici(Cekim(html=ARAMA_SAYFASI, http_kodu=200))
    assert ara(c, "   ") == []
    assert c.cagrilar == []


def test_cekim_basarisizsa_bos_liste():
    """Arama bir KOLAYLIK, kritik yol değil: toplayıcı erişilemezse kullanıcı
    linki elle de ekleyebilir. Ürün ekleme akışı kırılmamalı."""
    c = _SahteCekici(Cekim(html=None, http_kodu=503))
    assert ara(c, "x") == []


def test_cekici_patlarsa_bos_liste():
    class _Patlayan:
        def cek(self, url, kural=None):
            raise OSError("ağ yok")
    assert ara(_Patlayan(), "x") == []


# ── Eşzamanlılık: kuyruğa girme, hızlı reddet ────────────────────
# İlk yazımda semaforda BEKLENİYORDU ve bu ürünün tamamını düşürebilirdi:
# FastAPI senkron uçları sınırlı bir iş parçacığı havuzunda çalışıyor
# (varsayılan 40). Beklemek o parçacığı tutar; kırk kullanıcı aynı anda
# "ara"ya basarsa havuz tükenir ve panel de, giriş de, sağlık kontrolü de
# durur. İkincil bir kolaylık, kritik yolu kilitleyemez.

def test_slot_dolunca_beklenmez_hizli_reddedilir(monkeypatch):
    import threading
    import time

    from keepmoney import toplayici

    monkeypatch.setattr(toplayici, "SLOT_BEKLEME_SN", 0.05)
    monkeypatch.setattr(toplayici, "_ARAMA_SLOTU", threading.Semaphore(1))

    class _Yavas:
        def cek(self, url, kural=None):
            time.sleep(0.6)
            return Cekim(html=ARAMA_SAYFASI, http_kodu=200)

    hatalar: list[Exception] = []
    basladi = threading.Event()

    def uzun():
        basladi.set()
        toplayici.ara(_Yavas(), "x")

    t = threading.Thread(target=uzun)
    t.start()
    basladi.wait(timeout=2)
    time.sleep(0.1)                       # ilk arama slotu almış olsun

    basla = time.perf_counter()
    try:
        toplayici.ara(_Yavas(), "y")
    except toplayici.MesgulHata as e:
        hatalar.append(e)
    gecen = time.perf_counter() - basla
    t.join(timeout=5)

    assert hatalar, "slot doluyken bekleyip geçmemeli"
    assert gecen < 0.3, f"beklemede kaldı: {gecen:.2f} sn"


def test_slot_bosaldiginda_yeniden_calisir():
    """Reddetme KALICI olmamalı: sonraki istek normal çalışmalı."""
    from keepmoney import toplayici

    c = _SahteCekici(Cekim(html=ARAMA_SAYFASI, http_kodu=200))
    for _ in range(3):
        assert len(toplayici.ara(c, "x")) == 2


def test_hata_durumunda_slot_birakilir():
    """Sızdırılan slot, aramayı kalıcı olarak kilitlerdi."""
    from keepmoney import toplayici

    class _Patlayan:
        def cek(self, url, kural=None):
            raise OSError("ağ yok")

    for _ in range(5):
        assert toplayici.ara(_Patlayan(), "x") == []
    # Slot sızmadıysa normal arama hâlâ çalışır.
    c = _SahteCekici(Cekim(html=ARAMA_SAYFASI, http_kodu=200))
    assert len(toplayici.ara(c, "x")) == 2

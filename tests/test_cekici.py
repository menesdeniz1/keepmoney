"""Çekici testleri — SSRF'in yönlendirmeyle atlatılamadığını ve gövde
sınırının/karakter kodlamasının doğru çalıştığını doğrular.

Gerçek ağ YOK: `requests.get` yerine sahte bir çağrılabilir veriliyor.
"""
from __future__ import annotations

import pytest

from keepmoney import aglar
from keepmoney.cekici import HttpCekici


class SahteYanit:
    """`requests.Response`un testte kullanılan yüzeyi."""

    def __init__(self, kod=200, govde=b"<html>selam</html>", basliklar=None,
                 konum=None):
        self.status_code = kod
        self._govde = govde
        self.headers = dict(basliklar or {})
        if konum:
            self.headers["location"] = konum
        self.kapandi = False

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308) \
            and "location" in self.headers

    is_permanent_redirect = False

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._govde), chunk_size):
            yield self._govde[i:i + chunk_size]

    def close(self):
        self.kapandi = True


class SahteOturum:
    """İstenen URL'lere göre yanıt döndürür ve gidilen adresleri kaydeder."""

    def __init__(self, yanitlar: dict):
        self.yanitlar = yanitlar
        self.gidilen: list[str] = []

    def get(self, url, **kw):
        self.gidilen.append(url)
        return self.yanitlar.get(url, SahteYanit(404, b"yok"))


@pytest.fixture(autouse=True)
def _halka_acik_dns(monkeypatch):
    """Alan adları halka açık IP'ye çözülsün; iç ağ testleri yazılı IP kullanır."""
    monkeypatch.setattr(aglar, "_cozumle", lambda h: ["93.184.216.34"])


# ── SSRF: yönlendirme zinciri ────────────────────────────────────

def test_yonlendirme_ic_aga_saparsa_engellenir(monkeypatch):
    """ASIL AÇIK: ilk adres halka açık olduğu için kontrolü geçiyor, sonra
    302 ile bulut metadata ucuna sapıyor. Tek seferlik doğrulama yetmez.

    Uçtan uca `_requests` üzerinden sınanıyor: istisna orada `Cekim`e
    çevrilmeli, worker çökmemeli ve metadata ucuna İSTEK ATILMAMALI.
    """
    import requests

    c = HttpCekici()
    oturum = SahteOturum({
        "https://masum.com/urun": SahteYanit(
            302, konum="http://169.254.169.254/latest/meta-data/"),
    })
    monkeypatch.setattr(requests, "get", oturum.get)

    sonuc = c._requests("https://masum.com/urun")

    assert sonuc.html is None
    assert "guvensiz_hedef" in (sonuc.hata or "")
    assert not any("169.254" in u for u in oturum.gidilen)


def test_guvensiz_yonlendirme_istisna_firlatir():
    c = HttpCekici()
    oturum = SahteOturum({
        "https://masum.com/x": SahteYanit(302, konum="http://127.0.0.1:8000/"),
    })
    with pytest.raises(aglar.GuvensizHedef):
        c._yonlendirmeli_cek(oturum.get, "https://masum.com/x", "test")


def test_gecerli_yonlendirme_takip_edilir():
    c = HttpCekici()
    oturum = SahteOturum({
        "https://magaza.com/eski": SahteYanit(301, konum="/yeni"),
        "https://magaza.com/yeni": SahteYanit(200, b"<html>urun</html>"),
    })
    sonuc = c._yonlendirmeli_cek(oturum.get, "https://magaza.com/eski", "test")
    assert sonuc.http_kodu == 200
    assert "urun" in sonuc.html
    assert oturum.gidilen == ["https://magaza.com/eski", "https://magaza.com/yeni"]


def test_yonlendirme_dongusu_kirilir():
    """Sonsuz döngü worker'ı kilitler."""
    c = HttpCekici()
    oturum = SahteOturum({
        "https://magaza.com/a": SahteYanit(302, konum="https://magaza.com/b"),
        "https://magaza.com/b": SahteYanit(302, konum="https://magaza.com/a"),
    })
    sonuc = c._yonlendirmeli_cek(oturum.get, "https://magaza.com/a", "test")
    assert "yönlendirme" in (sonuc.hata or "")
    assert len(oturum.gidilen) <= aglar.MAKS_YONLENDIRME + 1


def test_cloudscraper_ayni_korumayi_kullanir():
    """Koruma iki yerde kopyalanmasın: cloudscraper de aynı döngüden geçmeli.
    Eskiden orada tek bir `dogrula(url)` vardı, yönlendirme kütüphaneye
    bırakılıyordu — yani atlatılabilir bir ikinci kapı."""
    import inspect
    kaynak = inspect.getsource(HttpCekici._cloudscraper_cek)
    assert "_yonlendirmeli_cek" in kaynak


# ── gövde sınırı ─────────────────────────────────────────────────

def test_dev_govde_kesilir():
    """Sıkıştırma bombası ya da dev sayfa worker'ın belleğini bitirmesin."""
    c = HttpCekici()
    dev = b"x" * (aglar.MAKS_GOVDE_BAYT + 500_000)
    oturum = SahteOturum({"https://magaza.com/dev": SahteYanit(200, dev)})
    sonuc = c._yonlendirmeli_cek(oturum.get, "https://magaza.com/dev", "test")
    assert len(sonuc.html) <= aglar.MAKS_GOVDE_BAYT + 64 * 1024


# ── karakter kodlaması ───────────────────────────────────────────

def test_meta_charset_ile_turkce_bozulmaz():
    """requests, charset'siz text/html yanıtta ISO-8859-1 varsayar (RFC 2616).
    Bu varsayıma uyulursa "Ekran Kartı" mojibake olur ve BOZUK AD kullanıcıya
    ürün adı diye gösterilir."""
    c = HttpCekici()
    govde = ('<html><head><meta charset="utf-8"></head>'
             '<body>Ekran Kartı — Şahin Güç</body></html>').encode()
    oturum = SahteOturum({"https://magaza.com/tr": SahteYanit(
        200, govde, basliklar={"Content-Type": "text/html"})})

    sonuc = c._yonlendirmeli_cek(oturum.get, "https://magaza.com/tr", "test")
    assert "Ekran Kartı" in sonuc.html
    assert "Şahin Güç" in sonuc.html


def test_basliktaki_charset_onceliklidir():
    c = HttpCekici()
    govde = "fiyat: 1.299 ₺".encode()
    oturum = SahteOturum({"https://magaza.com/x": SahteYanit(
        200, govde, basliklar={"Content-Type": "text/html; charset=utf-8"})})
    sonuc = c._yonlendirmeli_cek(oturum.get, "https://magaza.com/x", "test")
    assert "1.299 ₺" in sonuc.html


def test_kodlama_bilinmiyorsa_utf8_varsayilir():
    c = HttpCekici()
    govde = "Türkçe".encode()
    oturum = SahteOturum({"https://magaza.com/y": SahteYanit(200, govde)})
    sonuc = c._yonlendirmeli_cek(oturum.get, "https://magaza.com/y", "test")
    assert "Türkçe" in sonuc.html


# ── yanıt kapatma ────────────────────────────────────────────────

def test_yanit_kapatilir():
    """Akış (stream=True) kapatılmazsa bağlantı havuzu sızar."""
    c = HttpCekici()
    yanit = SahteYanit(200, b"<html>x</html>")
    oturum = SahteOturum({"https://magaza.com/z": yanit})
    c._yonlendirmeli_cek(oturum.get, "https://magaza.com/z", "test")
    assert yanit.kapandi is True


# ── Sessiz üretim açığı: tarayıcı motoru yokluğu ─────────────────

def test_playwright_yoklugu_tespit_edilebiliyor(monkeypatch):
    """`render: true` kurallar Playwright yokken SESSİZCE requests'e düşüyor
    ve o kaynaktan hiç fiyat gelmiyordu. Açılışta bunu bilmek şart."""
    import builtins

    from keepmoney.cekici import playwright_var_mi

    gercek = builtins.__import__

    def yok(ad, *a, **kw):
        if ad.startswith("playwright"):
            raise ImportError("yok")
        return gercek(ad, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", yok)
    assert playwright_var_mi() is False


def _kayitci():
    """structlog benzeri, kwargs kabul eden basit kaydedici."""
    kayitlar = []

    class _K:
        def warning(self, olay, **kw):
            kayitlar.append((olay, kw))

        def info(self, *a, **kw):
            pass

    return _K(), kayitlar


def test_motor_yoksa_zamanlayici_uyarir(monkeypatch):
    """Uyarı ETKİLENEN SİTELERİ saymalı — 'bir şeyler eksik' demek yetmez;
    hangi kaynakların sessizce boş döneceği görünmeli."""
    from keepmoney import zamanlayici

    sahte, kayitlar = _kayitci()
    monkeypatch.setattr(zamanlayici, "logger", sahte)
    monkeypatch.setattr("keepmoney.cekici.playwright_var_mi", lambda: False)

    zamanlayici.tarayici_motorunu_denetle()

    assert [o for o, _ in kayitlar] == ["tarayici_motoru_yok"]
    etkilenen = kayitlar[0][1]["etkilenen"]
    assert "akakce.com" in etkilenen and "amazon.com.tr" in etkilenen


def test_motor_varsa_uyarmaz(monkeypatch):
    from keepmoney import zamanlayici

    sahte, kayitlar = _kayitci()
    monkeypatch.setattr(zamanlayici, "logger", sahte)
    monkeypatch.setattr("keepmoney.cekici.playwright_var_mi", lambda: True)

    zamanlayici.tarayici_motorunu_denetle()
    assert kayitlar == []

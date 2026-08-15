"""SSRF koruması testleri (OWASP A10).

Bu testler DNS sahtelemesini BİLEREK devre dışı bırakır — korumanın kendisini
sınıyoruz, sahtesini değil. Yazılı IP'ler zaten DNS gerektirmez.
"""
import pytest

from keepmoney import aglar


@pytest.fixture(autouse=True)
def _gercek_cozumleme(monkeypatch):
    """conftest'teki sahte çözümleyiciyi geri al — asıl mantığı test ediyoruz."""
    monkeypatch.setattr(aglar, "_cozumle", aglar._cozumle)


# ── Yazılı IP hedefleri (DNS gerekmez) ──────────────────────────

@pytest.mark.parametrize("url,ipucu", [
    # Bulut metadata ucu — IAM anahtarları döndürür. En kritik hedef.
    ("https://169.254.169.254/latest/meta-data/", "link-local"),
    ("https://127.0.0.1:8000/", "loopback"),
    ("https://10.0.0.5/admin", "özel ağ"),
    ("https://192.168.1.1/", "özel ağ"),
    ("https://172.16.0.1/", "özel ağ"),
    ("https://[::1]:8000/", "IPv6 loopback"),
    ("https://[fd00::1]/", "IPv6 özel"),
    ("https://0.0.0.0/", "belirsiz"),
    ("https://224.0.0.1/", "multicast"),
])
def test_ic_ag_adresleri_engellenir(url, ipucu):
    sorun = aglar.url_sorunu(url)
    assert sorun is not None, f"{ipucu} engellenmeliydi: {url}"


def test_halka_acik_ip_gecer():
    assert aglar.url_sorunu("https://93.184.216.34/urun") is None


# ── Şema kontrolü ───────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "gopher://icsunucu:70/",
    "ftp://dosya.sunucu/",
    "redis://veritabani:6379/",
])
def test_http_disi_semalar_engellenir(url):
    assert "http/https" in (aglar.url_sorunu(url) or "")


def test_ana_makine_yoksa_engellenir():
    assert aglar.url_sorunu("https:///yol") is not None


# ── DNS ile iç ağa çözülen adlar ────────────────────────────────

def test_ic_aga_cozulen_ad_engellenir(monkeypatch):
    """Yazılı IP'ye bakmak YETMEZ: saldırgan kendi alan adını 10.0.0.5'e
    yönlendirebilir. Çözülen adresler kontrol edilmeli."""
    monkeypatch.setattr(aglar, "_cozumle", lambda h: ["10.0.0.5"])
    sorun = aglar.url_sorunu("https://masum-gorunen-site.com/urun")
    assert sorun is not None
    assert "iç ağ" in sorun


def test_karisik_cozumlemede_de_engellenir(monkeypatch):
    """Bir kaydı bile iç ağa düşen ad reddedilir — kısmi güven yok."""
    monkeypatch.setattr(aglar, "_cozumle", lambda h: ["93.184.216.34", "127.0.0.1"])
    assert aglar.url_sorunu("https://karisik.com/x") is not None


def test_cozulemeyen_ad_engellenir(monkeypatch):
    """Docker servis adları (veritabani, redis) dışarıdan çözülmez ama iç
    ağda çözülür — çözülemeyen adı geçirmek riskli."""
    monkeypatch.setattr(aglar, "_cozumle", lambda h: [])
    assert "çözümlenemedi" in (aglar.url_sorunu("https://veritabani:5432/") or "")


def test_halka_acik_cozumleme_gecer(monkeypatch):
    monkeypatch.setattr(aglar, "_cozumle", lambda h: ["93.184.216.34"])
    assert aglar.url_sorunu("https://www.magaza.com/urun") is None


# ── Yardımcılar ─────────────────────────────────────────────────

def test_dogrula_istisna_firlatir(monkeypatch):
    monkeypatch.setattr(aglar, "_cozumle", lambda h: ["127.0.0.1"])
    with pytest.raises(aglar.GuvensizHedef):
        aglar.dogrula("https://kotu.com/x")


def test_guvenli_mi_kisayolu(monkeypatch):
    monkeypatch.setattr(aglar, "_cozumle", lambda h: ["93.184.216.34"])
    assert aglar.guvenli_mi("https://iyi.com/x") is True
    assert aglar.guvenli_mi("https://127.0.0.1/x") is False

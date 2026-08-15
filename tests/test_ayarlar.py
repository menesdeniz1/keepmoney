"""Ayar doğrulama testleri.

Buradaki testler üretimde sessizce yanlış yapılandırılmış bir sunucuyu
engelliyor — hatanın açılışta patlaması, 3 ay sonra token sahteciliği olarak
ortaya çıkmasından iyidir.
"""
import pytest

from keepmoney.ayarlar import MIN_ANAHTAR_BAYT, Ayarlar, ayarlar
from keepmoney.db import VERITABANI_URL
from keepmoney.guvenlik import jwt_kullanici_id, jwt_uret


@pytest.fixture(autouse=True)
def _onbellek_temiz():
    ayarlar.cache_clear()
    yield
    ayarlar.cache_clear()


def _ortam(monkeypatch, **degerler):
    for anahtar in ("ORTAM", "JWT_GIZLI_ANAHTAR", "VERITABANI_URL"):
        monkeypatch.delenv(f"KEEPMONEY_{anahtar}", raising=False)
    for anahtar, deger in degerler.items():
        monkeypatch.setenv(f"KEEPMONEY_{anahtar.upper()}", deger)


def test_uretimde_anahtarsiz_acilmaz(monkeypatch):
    _ortam(monkeypatch, ortam="uretim")
    with pytest.raises(RuntimeError, match="zorunludur"):
        ayarlar()


def test_uretimde_kisa_anahtar_reddedilir(monkeypatch):
    """RFC 7518 §3.2 — kısa HMAC anahtarı token sahteciliğine açık."""
    _ortam(monkeypatch, ortam="uretim", jwt_gizli_anahtar="kisa")
    with pytest.raises(RuntimeError, match="en az 32 bayt"):
        ayarlar()


def test_uretimde_yeterli_anahtar_kabul(monkeypatch):
    _ortam(monkeypatch, ortam="uretim", jwt_gizli_anahtar="x" * MIN_ANAHTAR_BAYT)
    assert ayarlar().uretim_mi is True


def test_gelistirmede_kisa_anahtar_uyarir_ama_durdurmaz(monkeypatch, caplog):
    _ortam(monkeypatch, ortam="gelistirme", jwt_gizli_anahtar="kisa")
    a = ayarlar()
    assert a.jwt_gizli_anahtar == "kisa"
    assert "en az 32 bayt" in caplog.text


def test_gelistirmede_anahtarsizsa_uretilir(monkeypatch):
    _ortam(monkeypatch, ortam="gelistirme")
    a = ayarlar()
    assert len(a.jwt_gizli_anahtar.encode()) >= MIN_ANAHTAR_BAYT


def test_cors_virgullu_liste_olarak_verilebilir(monkeypatch):
    _ortam(monkeypatch, ortam="test")
    monkeypatch.setenv("KEEPMONEY_CORS_KAYNAKLARI",
                       "https://a.com, https://b.com")
    ayarlar.cache_clear()
    assert ayarlar().cors_kaynaklari == ["https://a.com", "https://b.com"]


def test_gecersiz_ortam_reddedilir(monkeypatch):
    _ortam(monkeypatch, ortam="canli")
    with pytest.raises(ValueError):
        Ayarlar()


def test_veritabani_adresi_tek_kaynaktan_gelir():
    """REGRESYON: db.py bir zamanlar os.environ['DATABASE_URL']'i kendisi
    okuyordu; ayarlar modülü eklenince iki doğruluk kaynağı oluştu ve testler
    bir dosyaya, Alembic başka dosyaya yazdı (CI yakaladı)."""
    assert ayarlar().veritabani_url == VERITABANI_URL


def test_uretilen_token_cozulebiliyor():
    assert jwt_kullanici_id(jwt_uret(42)) == 42


def test_bozuk_token_none_doner():
    assert jwt_kullanici_id("bu.bir.token.degil") is None


def test_cors_json_dizisi_olarak_da_verilebilir(monkeypatch):
    _ortam(monkeypatch, ortam="test")
    monkeypatch.setenv("KEEPMONEY_CORS_KAYNAKLARI", '["https://a.com"]')
    ayarlar.cache_clear()
    assert ayarlar().cors_kaynaklari == ["https://a.com"]

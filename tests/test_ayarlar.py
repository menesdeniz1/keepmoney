"""Ayar doğrulama testleri.

Buradaki testler üretimde sessizce yanlış yapılandırılmış bir sunucuyu
engelliyor — hatanın açılışta patlaması, 3 ay sonra token sahteciliği olarak
ortaya çıkmasından iyidir.
"""
import secrets

import pytest

from keepmoney.ayarlar import (
    MIN_ANAHTAR_BAYT,
    MIN_ANAHTAR_BIT,
    ONERILEN_ANAHTAR_BAYT,
    Ayarlar,
    anahtar_sorunu,
    ayarlar,
)
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


def test_uretimde_gercek_rastgele_anahtar_kabul(monkeypatch):
    _ortam(monkeypatch, ortam="uretim",
           jwt_gizli_anahtar=secrets.token_urlsafe(ONERILEN_ANAHTAR_BAYT))
    assert ayarlar().uretim_mi is True


def test_uretimde_dusuk_entropili_anahtar_reddedilir(monkeypatch):
    """UZUNLUK YETMEZ: 'aaaa...' 32 bayttır ama ~5 bit entropi taşır.
    Anahtar bir parola değil, CSPRNG çıktısı olmalı."""
    _ortam(monkeypatch, ortam="uretim", jwt_gizli_anahtar="a" * 64)
    with pytest.raises(RuntimeError, match="rastgele değil"):
        ayarlar()


def test_uretimde_sablon_degeri_reddedilir(monkeypatch):
    """.env.example'dan kopyalanıp unutulan değerler."""
    _ortam(monkeypatch, ortam="uretim",
           jwt_gizli_anahtar="changeme-changeme-1234567890-abcdefgh")
    with pytest.raises(RuntimeError, match="şablon"):
        ayarlar()


def test_anahtar_politikasi_dogrudan():
    assert MIN_ANAHTAR_BIT == 256 and MIN_ANAHTAR_BAYT == 32
    assert anahtar_sorunu(secrets.token_urlsafe(48)) is None
    assert "en az 32 bayt" in anahtar_sorunu("kisa")
    assert "rastgele değil" in anahtar_sorunu("a" * 64)
    assert "şablon" in anahtar_sorunu("Gz7-Kq2mPx9Lw4Rt6Yn1Bv8Cd3Fh5Jk-secret")


def test_uretimde_yildiz_cors_reddedilir(monkeypatch):
    """`*` + allow_credentials CORS spesifikasyonunca yasak; tarayıcı reddeder.
    Starlette yapılandırmayı kabul ettiği için hata ancak üretimde görülürdü."""
    _ortam(monkeypatch, ortam="uretim",
           jwt_gizli_anahtar=secrets.token_urlsafe(48))
    monkeypatch.setenv("KEEPMONEY_CORS_KAYNAKLARI", "*")
    with pytest.raises(RuntimeError, match="'\\*' olamaz"):
        ayarlar()


def test_gelistirmede_yildiz_cors_serbest(monkeypatch):
    _ortam(monkeypatch, ortam="gelistirme")
    monkeypatch.setenv("KEEPMONEY_CORS_KAYNAKLARI", "*")
    assert ayarlar().cors_kaynaklari == ["*"]


def test_gelistirmede_zayif_anahtar_uyarir_ama_durdurmaz(monkeypatch, caplog):
    """Yerel akışı kesmenin faydası yok — uyar, geç."""
    _ortam(monkeypatch, ortam="gelistirme", jwt_gizli_anahtar="kisa")
    a = ayarlar()
    assert a.jwt_gizli_anahtar == "kisa"
    assert "en az 32 bayt" in caplog.text


def test_gelistirmede_anahtarsizsa_guclu_uretilir(monkeypatch):
    _ortam(monkeypatch, ortam="gelistirme")
    a = ayarlar()
    assert len(a.jwt_gizli_anahtar.encode()) >= ONERILEN_ANAHTAR_BAYT
    assert anahtar_sorunu(a.jwt_gizli_anahtar) is None


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


def test_her_ayar_env_ornekte_belgeli():
    """`.env.example` yapılandırmanın TEK belgesi; eksik kalan ayar,
    varlığından haberdar olunmayan ayardır.

    Yeni bir ayar eklerken bu test onu belgelemeye zorlar — belge, koddan
    ayrı yaşamaya başladığı anda yanlış belgeye dönüşür.
    """
    import pathlib

    from keepmoney.ayarlar import Ayarlar

    ornek = pathlib.Path(__file__).resolve().parents[1] / ".env.example"
    metin = ornek.read_text(encoding="utf-8")

    eksik = [f"KEEPMONEY_{ad.upper()}" for ad in Ayarlar.model_fields
             if f"KEEPMONEY_{ad.upper()}" not in metin]
    assert not eksik, f".env.example'da belgelenmemiş ayar: {eksik}"


def test_env_ornekte_gercek_sir_yok():
    """Örnek dosya depoya işleniyor: içinde çalışan bir sır bulunmamalı."""
    import pathlib

    from keepmoney.ayarlar import anahtar_sorunu

    ornek = pathlib.Path(__file__).resolve().parents[1] / ".env.example"
    for satir in ornek.read_text(encoding="utf-8").splitlines():
        if satir.startswith("KEEPMONEY_JWT_GIZLI_ANAHTAR="):
            deger = satir.split("=", 1)[1].strip()
            # Boş olmalı; dolu ve politikadan GEÇEN bir değer, gerçek bir
            # anahtarın yanlışlıkla işlendiği anlamına gelir.
            assert not deger or anahtar_sorunu(deger) is not None, (
                ".env.example'da politikaya uyan gerçek bir anahtar var")

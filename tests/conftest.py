"""Test ortamı — uygulama modülleri import EDİLMEDEN önce çalışır.

Ayarlar `lru_cache`'li olduğu için ortam değişkenleri ilk `ayarlar()`
çağrısından önce yerinde olmalı. conftest.py pytest tarafından en başta
yüklendiğinden doğru yer burası.
"""
import os

os.environ.setdefault("KEEPMONEY_ORTAM", "test")
os.environ.setdefault(
    "KEEPMONEY_JWT_GIZLI_ANAHTAR",
    # Sabit ama gerçek CSPRNG çıktısı: testlerin tekrarlanabilir olması için
    # sabit, politikadan geçmesi için rastgele. Yalnızca test ortamı içindir.
    "kQ7vZ2xR9tL4mB6nH1wY8sJ3pD5gF0aC-eU2iO7kN4qT9rV6zX1yM8bW3hG5jS0dA")
# Testler bellek içi DB kullanır; bu değer yalnızca yanlışlıkla gerçek
# veritabanına yazılmasın diye var.
os.environ.setdefault("KEEPMONEY_VERITABANI_URL", "sqlite:///./data/test.sqlite")


import pytest


@pytest.fixture(autouse=True)
def _dns_cozumlemesi_sahte(monkeypatch):
    """Testlerde DNS çözümlemesini sahteler.

    SSRF koruması (aglar.py) ad → IP çözümlemesi yapıyor. Testlerde bu:
      • gerçek DNS'e çıkar (yavaş, kırılgan, ağsız ortamda çalışmaz),
      • `magaza.com` gibi uydurma adlar çözülemediği için her şeyi engeller.

    Korumayı KAPATMIYORUZ — yalnızca ad çözümlemesini sahteliyoruz. IP
    yazılı URL'ler (127.0.0.1, 169.254.169.254) gerçek kontrolden geçmeye
    devam ediyor, yani SSRF testleri hâlâ anlamlı.
    """
    from keepmoney import aglar

    def sahte_cozumle(host: str) -> list[str]:
        # example.com'un gerçek genel IP'si — halka açık kabul edilir
        return ["93.184.216.34"]

    monkeypatch.setattr(aglar, "_cozumle", sahte_cozumle)


@pytest.fixture(autouse=True)
def _hiz_sinirlari_sifirla():
    """Hız sınırı sayaçları modül düzeyinde (süreç belleği) tutuluyor.

    Testler arası paylaşılırsa 6. test "çok fazla deneme" alır. Her test
    bağımsız bir senaryodur; sayaç sıfırlanır. Sınırın KENDİSİ ayrıca
    test_api.py'de açıkça test ediliyor.
    """
    from keepmoney.api.koruma import sinirlayicilar

    sinirlayicilar.sifirla()
    yield
    sinirlayicilar.sifirla()


# ─────────────────── veritabanı motoru ───────────────────
#
# Testler varsayılan olarak bellek içi SQLite'ta koşar (hızlı, kurulumsuz).
# `KEEPMONEY_TEST_VERITABANI_URL` verilirse GERÇEK bir veritabanına karşı
# koşar — üretimde Postgres kullanılıyor ve "SQLite'ta geçiyor" ile
# "Postgres'te çalışıyor" aynı şey değil. Aradaki farklar sessizdir:
# tarih/saat tipleri, boolean, dizi/sözlük dönüşümleri, kilitleme,
# `CASE`/`GREATEST` gibi ifade farkları.
#
#   KEEPMONEY_TEST_VERITABANI_URL=postgresql+psycopg://... pytest -q

import pytest as _pytest
from sqlalchemy import create_engine as _create_engine
from sqlalchemy.pool import StaticPool as _StaticPool


def test_veritabani_url() -> str:
    return os.environ.get("KEEPMONEY_TEST_VERITABANI_URL", "sqlite:///:memory:")


def motor_olustur():
    """Test motoru. SQLite bellek içi DB'nin tek bağlantıda paylaşılması
    gerekir (StaticPool), yoksa her oturum boş bir veritabanı görür."""
    url = test_veritabani_url()
    if url.startswith("sqlite"):
        return _create_engine(url, future=True,
                              connect_args={"check_same_thread": False},
                              poolclass=_StaticPool)
    return _create_engine(url, future=True)


@_pytest.fixture
def motor():
    """Her teste TEMİZ şema. Şemayı her testte kurup yıkmak, kimlik
    sayaçlarını da sıfırlar — testler kayıt kimliklerinin 1'den başladığını
    varsayabiliyor ve bu varsayım iki motorda da geçerli kalıyor."""
    from keepmoney.db import Base

    m = motor_olustur()
    Base.metadata.drop_all(m)
    Base.metadata.create_all(m)
    yield m
    Base.metadata.drop_all(m)
    m.dispose()


@pytest.fixture(autouse=True)
def _robots_ag_yok(monkeypatch):
    """Testlerde robots.txt İNDİRİLMEZ.

    Kapının KENDİSİ devrede kalır (worker onu çağırmaya devam eder); yalnızca
    ağ adımı sahtelenir ve "okunamadı" davranışına düşer — üretimdeki
    varsayılan da bu: beyan yoksa yasak yoktur.

    Gerçek ayrıştırma mantığı `test_robots.py`de, ağa çıkmadan sınanıyor.
    """
    from keepmoney.robots import RobotsKapisi

    monkeypatch.setattr(RobotsKapisi, "_oku", lambda self, taban: None)

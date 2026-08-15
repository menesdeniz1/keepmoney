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
    from keepmoney.api.koruma import giris_sinirlayici, kayit_sinirlayici

    giris_sinirlayici.temizle()
    kayit_sinirlayici.temizle()
    yield
    giris_sinirlayici.temizle()
    kayit_sinirlayici.temizle()

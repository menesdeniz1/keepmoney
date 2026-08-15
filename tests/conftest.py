"""Test ortamı — uygulama modülleri import EDİLMEDEN önce çalışır.

Ayarlar `lru_cache`'li olduğu için ortam değişkenleri ilk `ayarlar()`
çağrısından önce yerinde olmalı. conftest.py pytest tarafından en başta
yüklendiğinden doğru yer burası.
"""
import os

os.environ.setdefault("KEEPMONEY_ORTAM", "test")
os.environ.setdefault(
    "KEEPMONEY_JWT_GIZLI_ANAHTAR",
    # >= 32 bayt: PyJWT kısa HMAC anahtarına uyarı veriyor (RFC 7518 §3.2)
    "test-ortami-icin-sabit-gizli-anahtar-en-az-32-bayt")
# Testler bellek içi DB kullanır; bu değer yalnızca yanlışlıkla gerçek
# veritabanına yazılmasın diye var.
os.environ.setdefault("KEEPMONEY_VERITABANI_URL", "sqlite:///./data/test.sqlite")

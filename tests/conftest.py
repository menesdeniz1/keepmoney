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

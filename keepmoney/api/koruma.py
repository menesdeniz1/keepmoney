"""HTTP güvenlik katmanı: başlıklar ve hız sınırı.

OWASP karşılıkları:
  A05 Security Misconfiguration → güvenlik başlıkları
  A07 Identification and Authentication Failures → giriş hız sınırı
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from ..ayarlar import ayarlar

# ── Hız sınırı ayarları ──────────────────────────────────────────
# Kaba ama etkili: parola denemesini insan hızına indirmek yeterlidir.
# Amaç kararlı bir saldırganı tamamen durdurmak değil (o mümkün değil),
# sözlük saldırısını ekonomik olmaktan çıkarmaktır.
GIRIS_PENCERE_SN = 300           # 5 dakika
GIRIS_LIMIT = 8                  # pencere başına başarısız deneme
KAYIT_PENCERE_SN = 3600
KAYIT_LIMIT = 5                  # IP başına saatte hesap açma

# Parola sıfırlama isteği kimlik doğrulaması İSTEMEZ. Sınırsız bırakılırsa
# birinin posta kutusuna e-posta bombardımanı yapılabilir (taciz aracı) ve
# SMTP kotası tükenir. Anahtar IP+adres: hem tek IP'den birçok adrese, hem
# birçok IP'den tek adrese saldırıyı yavaşlatır.
SIFIRLAMA_PENCERE_SN = 3600
SIFIRLAMA_LIMIT = 5


class HizSinirlayici:
    """Bellek içi kayan pencere sayacı.

    SINIRI: süreç belleğinde. Birden fazla API instance'ı çalıştığında her
    biri kendi sayacını tutar ve efektif limit N katına çıkar; yeniden
    başlatmada sayaç sıfırlanır. Tek instance için doğru ve bağımlılıksız
    çözüm budur. Çok instance'a geçildiği gün Redis'e taşınacak — o gün
    gelmeden Redis eklemek, tek bir sayaç için koca bir bileşen işletmektir.
    """

    def __init__(self, limit: int, pencere_sn: int):
        self.limit = limit
        self.pencere_sn = pencere_sn
        self._olaylar: dict[str, deque[float]] = defaultdict(deque)

    def _buda(self, anahtar: str, simdi: float) -> deque[float]:
        kuyruk = self._olaylar[anahtar]
        sinir = simdi - self.pencere_sn
        while kuyruk and kuyruk[0] < sinir:
            kuyruk.popleft()
        return kuyruk

    def asildi_mi(self, anahtar: str) -> bool:
        return len(self._buda(anahtar, time.monotonic())) >= self.limit

    def kaydet(self, anahtar: str) -> None:
        simdi = time.monotonic()
        self._buda(anahtar, simdi).append(simdi)

    def sifirla(self, anahtar: str) -> None:
        """Başarılı girişte sayacı temizle — meşru kullanıcı cezalanmasın."""
        self._olaylar.pop(anahtar, None)

    def temizle(self) -> None:
        self._olaylar.clear()


giris_sinirlayici = HizSinirlayici(GIRIS_LIMIT, GIRIS_PENCERE_SN)
kayit_sinirlayici = HizSinirlayici(KAYIT_LIMIT, KAYIT_PENCERE_SN)
sifirlama_sinirlayici = HizSinirlayici(SIFIRLAMA_LIMIT, SIFIRLAMA_PENCERE_SN)


def istemci_ip(istek: Request) -> str:
    """Ters vekil arkasında gerçek IP.

    DİKKAT: `X-Forwarded-For` istemci tarafından uydurulabilir. Yalnızca
    GÜVENDİĞİN bir ters vekilin arkasındaysan anlamlıdır — vekil bu başlığı
    kendisi yazar/üzerine yazar. Doğrudan internete açık çalıştırıyorsan
    bu başlığa güvenme.
    """
    iletilen = istek.headers.get("x-forwarded-for")
    if iletilen:
        return iletilen.split(",")[0].strip()
    return istek.client.host if istek.client else "bilinmiyor"


def giris_denemesi_kontrol(istek: Request, eposta: str) -> None:
    """Limit aşıldıysa 429. Anahtar IP+e-posta: tek IP'den birçok hesaba
    saldırıyı da, birçok IP'den tek hesaba saldırıyı da yavaşlatır."""
    anahtar = f"{istemci_ip(istek)}|{eposta.lower()}"
    if giris_sinirlayici.asildi_mi(anahtar):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Çok fazla başarısız giriş denemesi. Birkaç dakika sonra tekrar dene.",
            headers={"Retry-After": str(GIRIS_PENCERE_SN)},
        )


def giris_basarisiz(istek: Request, eposta: str) -> None:
    giris_sinirlayici.kaydet(f"{istemci_ip(istek)}|{eposta.lower()}")


def giris_basarili(istek: Request, eposta: str) -> None:
    giris_sinirlayici.sifirla(f"{istemci_ip(istek)}|{eposta.lower()}")


def kayit_kontrol(istek: Request) -> None:
    ip = istemci_ip(istek)
    if kayit_sinirlayici.asildi_mi(ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Çok fazla hesap oluşturma denemesi. Daha sonra tekrar dene.",
            headers={"Retry-After": str(KAYIT_PENCERE_SN)},
        )
    kayit_sinirlayici.kaydet(ip)


def sifirlama_kontrol(istek: Request, eposta: str) -> None:
    """Parola sıfırlama isteği hız sınırı.

    Aşıldığında 429 döner. Hata mesajı NÖTR tutulur — "bu adrese çok istek
    gönderildi" demek, adresin kayıtlı olduğunu sızdırırdı; oysa uç bunu
    özellikle gizliyor.
    """
    anahtar = f"{istemci_ip(istek)}|{eposta.lower()}"
    if sifirlama_sinirlayici.asildi_mi(anahtar):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Çok fazla istek gönderildi. Birazdan tekrar dene.",
            headers={"Retry-After": str(SIFIRLAMA_PENCERE_SN)},
        )
    sifirlama_sinirlayici.kaydet(anahtar)


class GuvenlikBasliklari(BaseHTTPMiddleware):
    """Tarayıcı tarafı savunma başlıkları.

    CSP burada dar tutulabiliyor çünkü arayüz aynı kaynaktan servis ediliyor
    ve harici script/stil kullanmıyor. `unsafe-inline` yalnızca style için
    var: Tailwind'in ürettiği stil dosyası harici, ama React satır içi stil
    (`style={{...}}`) kullanabiliyor.
    """

    async def dispatch(self, istek: Request, sonraki):
        yanit = await sonraki(istek)
        a = ayarlar()

        yanit.headers.setdefault("X-Content-Type-Options", "nosniff")
        yanit.headers.setdefault("X-Frame-Options", "DENY")
        yanit.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        yanit.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        yanit.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        if a.uretim_mi:
            # Yalnızca üretimde: yerelde HTTP kullanılıyor ve HSTS tarayıcıda
            # kalıcı olarak kayıtlı kalıp geliştirmeyi bozar.
            yanit.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains")
        return yanit

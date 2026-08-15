"""Uygulama ayarları — TEK kaynak.

Ortam değişkenlerinden okunur (`KEEPMONEY_` öneki) ya da `.env` dosyasından.
Koda hiçbir yerde `os.environ` yazılmaz; her ayar burada tiplenmiş olarak
tanımlıdır. Yanlış tipte bir değer verilirse uygulama AÇILIRKEN patlar —
üretimde 3 saat sonra tuhaf bir davranış olarak ortaya çıkmaktansa.
"""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Ayarlar(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KEEPMONEY_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ortam: Literal["gelistirme", "test", "uretim"] = "gelistirme"

    # ── Veritabanı ────────────────────────────────────────────────
    veritabani_url: str = "sqlite:///./data/keepmoney.sqlite"

    # ── Kimlik ────────────────────────────────────────────────────
    # Üretimde ZORUNLU. Geliştirmede boşsa süreç başına rastgele üretilir —
    # repoya sabit bir secret gömmektense her restart'ta oturum düşsün.
    # En az MIN_ANAHTAR_BAYT olmalı (RFC 7518 §3.2): kısa HMAC anahtarı
    # brute-force'a açıktır ve token sahteciliği demektir.
    jwt_gizli_anahtar: str = ""
    jwt_omur_dk: int = 60 * 24 * 7          # 7 gün
    jwt_algoritma: str = "HS256"

    # ── Telegram ──────────────────────────────────────────────────
    telegram_bot_token: str | None = None
    telegram_baglama_omru_dk: int = 10      # deep-link token ömrü

    # ── Web ───────────────────────────────────────────────────────
    # NoDecode: pydantic-settings karmaşık tipleri env'den JSON olarak
    # çözmeye çalışır ve `a.com,b.com` girdisinde patlar. NoDecode ham
    # string'i aşağıdaki doğrulayıcıya bırakır — deploy ortamlarında CORS
    # listesi virgülle yazılabilsin (JSON dizisi yazdırmak kullanıcı düşmanı).
    cors_kaynaklari: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"])

    # ── Kota (ücretsiz katman) ────────────────────────────────────
    kullanici_basina_izleme_limiti: int = 30

    @field_validator("cors_kaynaklari", mode="before")
    @classmethod
    def _virgullu_liste(cls, v):
        """Hem virgüllü hem JSON biçimini kabul eder:
        `https://a.com,https://b.com`  ya da  `["https://a.com"]`
        """
        if isinstance(v, str):
            ham = v.strip()
            if ham.startswith("["):
                import json
                return json.loads(ham)
            return [p.strip() for p in ham.split(",") if p.strip()]
        return v

    @property
    def uretim_mi(self) -> bool:
        return self.ortam == "uretim"


# ── JWT anahtar politikası ────────────────────────────────────────
#
# RFC 7518 §3.2 (JSON Web Algorithms), HS256 için:
#   "A key of the same size as the hash output (for instance, 256 bits for
#    HS256) or larger MUST be used with this algorithm."
#
# Yani ZORUNLU taban 256 bit = 32 bayt. Sektör pratiği de budur; OWASP ve
# Auth0/Okta dokümanları aynı sayıyı verir.
#
# Biz 384 bit (48 bayt) ÜRETİYORUZ. Sebep: taban değeri tam sınırda kullanmak,
# ileride HS384'e geçmek gerektiğinde anahtarı yenilemek demektir. 16 bayt
# fazlanın maliyeti sıfır.
MIN_ANAHTAR_BIT = 256
MIN_ANAHTAR_BAYT = MIN_ANAHTAR_BIT // 8          # 32
ONERILEN_ANAHTAR_BAYT = 48                       # 384 bit

# UZUNLUK YETMEZ — ENTROPİ GEREKİR. "aaaa...aaaa" 32 bayttır ama ~5 bitlik
# entropi taşır; sözlük saldırısıyla saniyeler içinde kırılır. Anahtar bir
# PAROLA DEĞİL, rastgele bir bit dizisidir ve CSPRNG'den üretilmelidir.
# Aşağıdaki iki sezgisel kontrol, elle yazılmış "anahtar"ları yakalar.
MIN_BENZERSIZ_KARAKTER = 12
_SUPHELI_KALIPLAR = (
    "changeme", "change-me", "secret", "password", "parola", "gizli",
    "example", "ornek", "placeholder", "degistir", "todo", "xxx",
)

_ANAHTAR_URET_IPUCU = (
    "Üret: python -c \"import secrets; print(secrets.token_urlsafe"
    f"({ONERILEN_ANAHTAR_BAYT}))\"")


def anahtar_sorunu(anahtar: str) -> str | None:
    """Anahtar politikaya uyuyor mu? Uymuyorsa sebebi döner.

    Entropiyi bir string'den kesin ölçmek mümkün değil; amaç mükemmel ölçüm
    değil, AÇIKÇA zayıf olanı yakalamak: kısa, tek karakterden ibaret, ya da
    "changeme" gibi şablondan kopyalanmış değerler.
    """
    bayt = len(anahtar.encode("utf-8"))
    if bayt < MIN_ANAHTAR_BAYT:
        return (f"en az {MIN_ANAHTAR_BAYT} bayt ({MIN_ANAHTAR_BIT} bit) olmalı "
                f"— şu an {bayt} bayt")

    if len(set(anahtar)) < MIN_BENZERSIZ_KARAKTER:
        return (f"yeterince rastgele değil (yalnızca {len(set(anahtar))} farklı "
                "karakter). Uzunluk tek başına yetmez; anahtar CSPRNG ile "
                "üretilmelidir")

    kucuk = anahtar.lower()
    for kalip in _SUPHELI_KALIPLAR:
        if kalip in kucuk:
            return f"şablon/örnek değer içeriyor ('{kalip}')"

    return None


@lru_cache(maxsize=1)
def ayarlar() -> Ayarlar:
    """Süreç ömrü boyunca tekil. Testler `ayarlar.cache_clear()` çağırabilir."""
    a = Ayarlar()
    _jwt_anahtarini_dogrula(a)
    _cors_dogrula(a)
    return a


def _jwt_anahtarini_dogrula(a: Ayarlar) -> None:
    log = logging.getLogger("keepmoney.ayarlar")

    if not a.jwt_gizli_anahtar:
        if a.uretim_mi:
            raise RuntimeError(
                "KEEPMONEY_JWT_GIZLI_ANAHTAR üretimde zorunludur. "
                + _ANAHTAR_URET_IPUCU)
        # Geliştirme/test: süreç başına rastgele. Her restart'ta oturumlar
        # düşer ama repoya sabit secret gömülmemiş olur.
        a.jwt_gizli_anahtar = secrets.token_urlsafe(ONERILEN_ANAHTAR_BAYT)
        return

    sorun = anahtar_sorunu(a.jwt_gizli_anahtar)
    if sorun is None:
        return

    mesaj = f"KEEPMONEY_JWT_GIZLI_ANAHTAR {sorun}. " + _ANAHTAR_URET_IPUCU
    if a.uretim_mi:
        # Üretimde AÇILIŞTA dur: zayıf imza anahtarı, istediğin kullanıcı
        # adına geçerli token üretilebilmesi demektir (tam hesap devralma).
        raise RuntimeError(mesaj)
    log.warning(mesaj)


def _cors_dogrula(a: Ayarlar) -> None:
    """Üretimde `*` + kimlik bilgisi kombinasyonunu engeller.

    `allow_origins=["*"]` ile `allow_credentials=True` birlikte KULLANILAMAZ:
    CORS spesifikasyonu bunu yasaklar, tarayıcılar isteği reddeder. Starlette
    yine de bu yapılandırmayı kabul eder ve hata üretimde "neden çalışmıyor"
    şeklinde ortaya çıkar. Açılışta yakalamak daha ucuz.
    """
    if a.uretim_mi and "*" in a.cors_kaynaklari:
        raise RuntimeError(
            "KEEPMONEY_CORS_KAYNAKLARI üretimde '*' olamaz — kimlik bilgisi "
            "taşıyan isteklerde tarayıcı bunu reddeder. Alan adlarını "
            "açıkça listele: https://keepmoney.com,https://www.keepmoney.com")

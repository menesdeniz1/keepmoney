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


# RFC 7518 §3.2: HS256 anahtarı hash çıktısı kadar (32 bayt) olmalı.
# Daha kısası brute-force'a açıktır — kırılan anahtar, istediğin kullanıcı
# adına token üretmek demektir.
MIN_ANAHTAR_BAYT = 32

_ANAHTAR_URET_IPUCU = (
    'Üret: python -c "import secrets; print(secrets.token_urlsafe(48))"')


@lru_cache(maxsize=1)
def ayarlar() -> Ayarlar:
    """Süreç ömrü boyunca tekil. Testler `ayarlar.cache_clear()` çağırabilir."""
    a = Ayarlar()

    if not a.jwt_gizli_anahtar:
        if a.uretim_mi:
            raise RuntimeError(
                "KEEPMONEY_JWT_GIZLI_ANAHTAR üretimde zorunludur. "
                + _ANAHTAR_URET_IPUCU)
        # Geliştirme/test: süreç başına rastgele. Her restart'ta oturumlar
        # düşer ama repoya sabit secret gömülmemiş olur.
        a.jwt_gizli_anahtar = secrets.token_urlsafe(48)

    elif len(a.jwt_gizli_anahtar.encode()) < MIN_ANAHTAR_BAYT:
        mesaj = (f"KEEPMONEY_JWT_GIZLI_ANAHTAR en az {MIN_ANAHTAR_BAYT} bayt "
                 f"olmalı (şu an {len(a.jwt_gizli_anahtar.encode())}). "
                 + _ANAHTAR_URET_IPUCU)
        if a.uretim_mi:
            raise RuntimeError(mesaj)
        # Geliştirmede engellemek yerine uyar — yerel .env'ler kısa olabiliyor
        # ve akışı kesmenin bir faydası yok.
        logging.getLogger("keepmoney.ayarlar").warning(mesaj)

    return a

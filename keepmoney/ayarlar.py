"""Uygulama ayarları — TEK kaynak.

Ortam değişkenlerinden okunur (`KEEPMONEY_` öneki) ya da `.env` dosyasından.
Koda hiçbir yerde `os.environ` yazılmaz; her ayar burada tiplenmiş olarak
tanımlıdır. Yanlış tipte bir değer verilirse uygulama AÇILIRKEN patlar —
üretimde 3 saat sonra tuhaf bir davranış olarak ortaya çıkmaktansa.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    jwt_gizli_anahtar: str = ""
    jwt_omur_dk: int = 60 * 24 * 7          # 7 gün
    jwt_algoritma: str = "HS256"

    # ── Telegram ──────────────────────────────────────────────────
    telegram_bot_token: str | None = None
    telegram_baglama_omru_dk: int = 10      # deep-link token ömrü

    # ── Web ───────────────────────────────────────────────────────
    cors_kaynaklari: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"])

    # ── Kota (ücretsiz katman) ────────────────────────────────────
    kullanici_basina_izleme_limiti: int = 30

    @field_validator("cors_kaynaklari", mode="before")
    @classmethod
    def _virgullu_liste(cls, v):
        """CORS_KAYNAKLARI="https://a.com,https://b.com" biçimini destekler."""
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @property
    def uretim_mi(self) -> bool:
        return self.ortam == "uretim"


@lru_cache(maxsize=1)
def ayarlar() -> Ayarlar:
    """Süreç ömrü boyunca tekil. Testler `ayarlar.cache_clear()` çağırabilir."""
    a = Ayarlar()
    if not a.jwt_gizli_anahtar:
        if a.uretim_mi:
            raise RuntimeError(
                "KEEPMONEY_JWT_GIZLI_ANAHTAR üretimde zorunludur. "
                "Üret: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        a.jwt_gizli_anahtar = secrets.token_hex(32)
    return a

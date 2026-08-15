"""Yapılandırılmış loglama.

Geliştirmede renkli/okunaklı, üretimde JSON. Neden JSON: üretimde logları
gözle okumazsın, sorgularsın. `grep "fiyat okunamadı"` ile
`domain="trendyol.com" AND olay="okuma_basarisiz"` arasındaki fark, bir
arızayı 10 dakikada mı 2 saatte mi bulacağındır.

Anahtar-değer disiplini: mesaj metnine değer GÖMME.
    kötü : log.info(f"{lp.ad} için fiyat {fiyat} okundu")
    iyi  : log.info("fiyat_okundu", urun=lp.ad, fiyat=fiyat, domain=host)
"""
from __future__ import annotations

import logging
import sys

import structlog

from .ayarlar import ayarlar


def kur() -> None:
    """Süreç başında bir kez çağrılır (API, worker, bot)."""
    a = ayarlar()
    uretim = a.uretim_mi

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

    islemciler: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    islemciler.append(
        structlog.processors.JSONRenderer()
        if uretim
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    structlog.configure(
        processors=islemciler,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Gürültü kısma: uvicorn erişim logu yapılandırılmış logla çakışıyor.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def log(ad: str):
    return structlog.get_logger(ad)

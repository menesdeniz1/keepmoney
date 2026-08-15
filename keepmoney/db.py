"""Veritabanı bağlantısı.

Bağlantı adresi TEK kaynaktan gelir: `ayarlar().veritabani_url`.

Bu dosya bir zamanlar `os.environ["DATABASE_URL"]`i kendisi okuyordu; ayarlar
modülü eklendiğinde iki ayrı doğruluk kaynağı oluştu ve CI bunu yakaladı:
testler bir dosyaya, Alembic başka bir dosyaya yazıyordu. Bağlantı adresini
buradan başka hiçbir yerde okuma.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .ayarlar import ayarlar

VERITABANI_URL = ayarlar().veritabani_url

# check_same_thread: tarama worker'ı ayrı thread'lerden aynı oturumu kullanır.
_baglanti_args = (
    {"check_same_thread": False} if VERITABANI_URL.startswith("sqlite") else {}
)

engine = create_engine(VERITABANI_URL, connect_args=_baglanti_args, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI bağımlılığı. Testler bunu kendi oturumlarıyla değiştirir."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sqlite_dizinini_hazirla(url: str = VERITABANI_URL) -> None:
    """SQLite dosya yolunun dizini yoksa oluşturur."""
    if not url.startswith("sqlite:///"):
        return
    yol = Path(url.removeprefix("sqlite:///"))
    if str(yol.parent) not in (".", ""):
        os.makedirs(yol.parent, exist_ok=True)


def init_db() -> None:
    """Tabloları doğrudan modelden oluşturur.

    SADECE geliştirme ve testler için. Üretimde şema `alembic upgrade head`
    ile yönetilir (bkz. docs/MIMARI.md K15) — `create_all` var olan tabloyu
    GÜNCELLEMEZ, sessizce eski şemayla devam eder.
    """
    from . import models  # noqa: F401 — modeller metadata'ya kaydolsun

    sqlite_dizinini_hazirla()
    Base.metadata.create_all(bind=engine)

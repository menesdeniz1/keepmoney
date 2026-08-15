"""Veritabanı bağlantısı.

Bağlantı adresi TEK kaynaktan gelir: `ayarlar().veritabani_url`.

Bu dosya bir zamanlar `os.environ["DATABASE_URL"]`i kendisi okuyordu; ayarlar
modülü eklendiğinde iki ayrı doğruluk kaynağı oluştu ve CI bunu yakaladı:
testler bir dosyaya, Alembic başka bir dosyaya yazıyordu. Bağlantı adresini
buradan başka hiçbir yerde okuma.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .ayarlar import ayarlar

VERITABANI_URL = ayarlar().veritabani_url

# check_same_thread: tarama worker'ı ayrı thread'lerden aynı oturumu kullanır.
_baglanti_args = (
    {"check_same_thread": False} if VERITABANI_URL.startswith("sqlite") else {}
)

engine = create_engine(VERITABANI_URL, connect_args=_baglanti_args, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@event.listens_for(Engine, "connect")
def _sqlite_yabanci_anahtar(dbapi_baglanti, _):
    """SQLite'ta yabancı anahtar kısıtlarını AÇ.

    SQLite bunu varsayılan olarak KAPALI tutar — yani `ON DELETE` kuralları
    hiç çalışmaz ve bozuk referanslar sessizce kabul edilir. Postgres ise
    zorlar. Bu fark, "testler yeşil ama üretimde 500" üreten en sinsi
    kaynaklardan biri: uyarısı olan bir izlemeyi silmek Postgres'te yabancı
    anahtar ihlaliyle patlarken SQLite'ta sorunsuz görünüyordu ve o hâliyle
    337 test bunu göremiyordu.

    Dinleyici TEK BİR motora değil, `Engine` sınıfına bağlı: testler kendi
    motorlarını kuruyor ve yalnızca uygulama motoruna bağlansaydı testler
    yine gevşek kurallarla koşardı — yani düzeltme, düzeltmek istediği
    boşluğu kapatmazdı.

    Geliştirme veritabanı üretimle aynı katılıkta davranmalı.
    """
    if isinstance(dbapi_baglanti, sqlite3.Connection):
        imlec = dbapi_baglanti.cursor()
        imlec.execute("PRAGMA foreign_keys=ON")
        imlec.close()


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

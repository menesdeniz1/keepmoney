"""Veritabanı bağlantısı. SQLite ile başlar, Postgres'e DATABASE_URL ile geçer.

SQLite tek makinede 5.000 kullanıcıya kadar rahat yeter; asıl darboğaz her
zaman scraping olur, veritabanı değil. Postgres'e geçiş noktası: tarama
worker'ını ayrı makineye almak istediğin gün.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/keepmoney.sqlite")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI bağımlılığı."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tabloları oluşturur. Şema gerçekten evrilmeye başlayınca Alembic'e
    geçilecek — o güne kadar create_all yeterli ve dürüst."""
    from . import models  # noqa: F401 — modeller metadata'ya kaydolsun
    if DATABASE_URL.startswith("sqlite:///./"):
        os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)

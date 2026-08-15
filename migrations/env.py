"""Alembic ortamı.

Veritabanı URL'i ve modeller uygulamanın kendi ayarlarından okunur — iki yerde
iki farklı bağlantı dizesi tutulmasın (DRY).
"""
import pathlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from keepmoney import models  # noqa: F401 — tablolar metadata'ya kaydolsun
from keepmoney.ayarlar import ayarlar
from keepmoney.db import Base

config = context.config
_url = ayarlar().veritabani_url
config.set_main_option("sqlalchemy.url", _url)

# SQLite dosya yolu için dizin yoksa oluştur — migrasyon boş bir makinede de
# tek komutla çalışabilmeli.
if _url.startswith("sqlite:///"):
    _yol = pathlib.Path(_url.removeprefix("sqlite:///"))
    if _yol.parent and str(_yol.parent) not in (".", ""):
        _yol.parent.mkdir(parents=True, exist_ok=True)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite ALTER TABLE kısıtlı — batch mod tabloyu yeniden yaratarak
        # kolon silme/değiştirmeyi mümkün kılar.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    baglanti_yapilandirmasi = config.get_section(config.config_ini_section, {})
    motor = engine_from_config(
        baglanti_yapilandirmasi, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with motor.connect() as baglanti:
        context.configure(
            connection=baglanti,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

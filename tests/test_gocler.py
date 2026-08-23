"""Göçlerin VERİYİ KORUDUĞUNU doğrulayan testler.

NEDEN VAR: `alembic check` yalnızca "model ile şema uyuşuyor mu" sorusunu
cevaplıyor — göçün veriyi taşıyıp taşımadığını değil. Aradaki fark gerçek bir
kayıpla öğrenildi:

`Watch.set_id` → `set_uyeleri` göçünün ilk hâli ara tabloyu önce kurup
satırları oraya yazıyor, sonra sütunu düşürüyordu. SQLite sütun düşürmeyi
desteklemediği için Alembic o adımda `watches` tablosunu DROP edip yeniden
kuruyor; yabancı anahtarlar açık olduğundan (bkz. db.py) `set_uyeleri`
üzerindeki ON DELETE CASCADE tetiklendi ve YENİ TAŞINAN SATIRLAR SİLİNDİ.
Göç hatasız tamamlandı, `alembic check` temiz dedi, üyelikler gitti.

Bu dosya göçü GERÇEK VERİYLE koşturur: önceki sürümde bir kayıt yaratır,
`upgrade head` yapar ve verinin karşı tarafta durduğunu doğrular.
"""
from __future__ import annotations

import pathlib

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

KOK = pathlib.Path(__file__).resolve().parents[1]

# Çoklu set üyeliğini getiren göç ve bir öncesi.
ONCEKI = "28f883ebaff7"
COKLU_SET = "a3c81f47b2d9"


@pytest.fixture
def gecici_veritabani(tmp_path, monkeypatch):
    """Boş bir SQLite dosyası + o dosyaya bakan alembic yapılandırması.

    Ayarlar `lru_cache`li ve `migrations/env.py` adresi ORADAN okuyor; bu
    yüzden ortam değişkeni ayarlanıp önbellek temizleniyor. Gerçek
    veritabanına dokunmamak kritik: göç testi tabloları yeniden kuruyor.
    """
    from keepmoney.ayarlar import ayarlar

    yol = tmp_path / "goc-denemesi.sqlite"
    monkeypatch.setenv("KEEPMONEY_VERITABANI_URL", f"sqlite:///{yol}")
    ayarlar.cache_clear()

    cfg = Config(str(KOK / "alembic.ini"))
    yield cfg, yol

    ayarlar.cache_clear()


def test_coklu_set_gocu_uyelikleri_korur(gecici_veritabani):
    """Göçten önce yazılan set üyeliği, göçten sonra ara tabloda olmalı."""
    cfg, yol = gecici_veritabani

    command.upgrade(cfg, ONCEKI)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi) "
            "VALUES (1, 'a@b.c', 'x', 0)"))
        b.execute(sa.text(
            "INSERT INTO products (id, ad) VALUES (1, 'Ekran Kartı'), "
            "(2, 'İşlemci')"))
        b.execute(sa.text(
            "INSERT INTO watch_sets (id, user_id, ad, hedef_butce) "
            "VALUES (1, 1, 'PC Toplama', 150000)"))
        # Biri sette, biri değil: göç ikisini de doğru işlemeli.
        b.execute(sa.text(
            "INSERT INTO watches (id, user_id, product_id, set_id) "
            "VALUES (10, 1, 1, 1), (11, 1, 2, NULL)"))

    command.upgrade(cfg, COKLU_SET)

    with motor.begin() as b:
        uyelikler = list(b.execute(sa.text(
            "SELECT watch_id, set_id FROM set_uyeleri")))
        izlemeler = b.execute(sa.text("SELECT COUNT(*) FROM watches")).scalar()
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('watches')"))]
    motor.dispose()

    assert uyelikler == [(10, 1)], "set üyeliği göçte kayboldu"
    assert izlemeler == 2, "izlemeler göçte kayboldu"
    assert "set_id" not in sutunlar, "eski sütun düşürülmemiş"


def test_coklu_set_gocu_geri_alinabilir(gecici_veritabani):
    """Geri alma da veriyi taşımalı: üyelik `set_id` sütununa dönmeli.

    Çoklu üyelik tek sütuna sığmadığı için fazlası düşer — bu bilinçli ve
    göç dosyasında yazılı. Test EN AZ birinin döndüğünü doğruluyor.
    """
    cfg, yol = gecici_veritabani

    command.upgrade(cfg, COKLU_SET)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi) "
            "VALUES (1, 'a@b.c', 'x', 0)"))
        b.execute(sa.text("INSERT INTO products (id, ad) VALUES (1, 'Ürün')"))
        b.execute(sa.text(
            "INSERT INTO watch_sets (id, user_id, ad) VALUES (1, 1, 'Set'), "
            "(2, 1, 'İkinci set')"))
        b.execute(sa.text(
            "INSERT INTO watches (id, user_id, product_id) VALUES (10, 1, 1)"))
        # AYNI ürün İKİ sette — yeni modelin izin verdiği durum.
        b.execute(sa.text(
            "INSERT INTO set_uyeleri (watch_id, set_id) VALUES (10, 1), (10, 2)"))

    command.downgrade(cfg, ONCEKI)

    with motor.begin() as b:
        satir = b.execute(sa.text(
            "SELECT set_id FROM watches WHERE id = 10")).one()
    motor.dispose()

    assert satir[0] in (1, 2), "geri almada üyelik tamamen kayboldu"

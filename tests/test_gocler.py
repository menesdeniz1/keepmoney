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

# Ürün bağlam sütunlarını getiren göç (BACKLOG A1) ve bir öncesi.
BAGLAM_SUTUNLARI = "c7e5a92f1b4d"

# İzlemeye yüzde eşiği ve yeniden kurma süresi sütunlarını getiren göç
# (BACKLOG E1) — bir öncesi BAGLAM_SUTUNLARI.
YUZDE_ESIGI = "a9edb33fc2b8"

# `price_readings.fiyat`i nullable yapan + `stokta_var` ekleyen göç
# (BACKLOG B4) — bir öncesi YUZDE_ESIGI.
STOK_BOSLUKLARI = "864f6f6e8aa7"

# `users.oturum_surumu` — parola değişince eski token'ları düşüren sayaç.
# Bir öncesi STOK_BOSLUKLARI.
OTURUM_SURUMU = "c5f2a71e8d40"

# `alerts.telegram_deneme` — iletim kuyruğunun tıkanmasını önleyen sayaç.
TELEGRAM_DENEME = "846b4730b906"


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


def test_baglam_gocu_urun_ve_set_uyeligini_korur(gecici_veritabani):
    """A1 (ürün bağlam sütunları) veriyi bozmamalı — hem ürün satırını hem de
    üzerinden geçtiği `set_uyeleri` ara tablosunu.

    Bu göç `batch_alter_table` KULLANMIYOR (emsal: 9b47605c0346) — düz
    `add_column`/`drop_column`. Bilinçli seçim ama yine de gerçek veriyle
    doğrulanır: `products` tablosunu SQLite'ın tabloyu yeniden kurmadan
    değiştirdiğini varsaymak yerine ÖLÇMEK, tam da bu dosyanın var oluş
    sebebi (§5.19 — `alembic check` şemayı doğrular, veriyi değil)."""
    cfg, yol = gecici_veritabani

    command.upgrade(cfg, COKLU_SET)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi) "
            "VALUES (1, 'a@b.c', 'x', 0)"))
        b.execute(sa.text(
            "INSERT INTO products (id, ad, guncel_fiyat) "
            "VALUES (1, 'Ekran Kartı', 45499)"))
        b.execute(sa.text(
            "INSERT INTO watch_sets (id, user_id, ad) VALUES (1, 1, 'Set')"))
        b.execute(sa.text(
            "INSERT INTO watches (id, user_id, product_id) VALUES (10, 1, 1)"))
        b.execute(sa.text(
            "INSERT INTO set_uyeleri (watch_id, set_id) VALUES (10, 1)"))

    command.upgrade(cfg, BAGLAM_SUTUNLARI)

    with motor.begin() as b:
        urun = b.execute(sa.text(
            "SELECT id, ad, guncel_fiyat FROM products")).one()
        uyelikler = list(b.execute(sa.text(
            "SELECT watch_id, set_id FROM set_uyeleri")))
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('products')"))]

    assert urun == (1, "Ekran Kartı", 45499), "ürün göçte bozuldu/kayboldu"
    assert uyelikler == [(10, 1)], "set üyeliği göçte kayboldu"
    for sutun in ("sinyal", "dip90", "medyan90", "yuzdelik", "gecmis_gun", "baglam_ts"):
        assert sutun in sutunlar, f"beklenen sütun eksik: {sutun}"

    command.downgrade(cfg, COKLU_SET)

    with motor.begin() as b:
        urun = b.execute(sa.text(
            "SELECT id, ad, guncel_fiyat FROM products")).one()
        uyelikler = list(b.execute(sa.text(
            "SELECT watch_id, set_id FROM set_uyeleri")))
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('products')"))]
    motor.dispose()

    assert urun == (1, "Ekran Kartı", 45499), "geri almada ürün bozuldu/kayboldu"
    assert uyelikler == [(10, 1)], "geri almada set üyeliği kayboldu"
    for sutun in ("sinyal", "dip90", "medyan90", "yuzdelik", "gecmis_gun", "baglam_ts"):
        assert sutun not in sutunlar, f"geri almada sütun düşürülmemiş: {sutun}"


def test_yuzde_esigi_gocu_izleme_verisini_korur(gecici_veritabani):
    """E1 (yüzde eşiği sütunları) `watches` tablosunu bozmamalı — ne kendi
    satırını (hedef_fiyat gibi mevcut alanlar) ne üzerinden geçtiği
    `set_uyeleri` ara tablosunu.

    `c7e5a92f1b4d` (A1) ile AYNI desen: `batch_alter_table` KULLANILMIYOR,
    düz `add_column`/`drop_column` — ama yine GERÇEK VERİYLE doğrulanır
    (§5.19 — `alembic check` şemayı doğrular, veriyi değil)."""
    cfg, yol = gecici_veritabani

    command.upgrade(cfg, BAGLAM_SUTUNLARI)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi) "
            "VALUES (1, 'a@b.c', 'x', 0)"))
        b.execute(sa.text("INSERT INTO products (id, ad) VALUES (1, 'Ürün')"))
        b.execute(sa.text(
            "INSERT INTO watch_sets (id, user_id, ad) VALUES (1, 1, 'Set')"))
        b.execute(sa.text(
            "INSERT INTO watches (id, user_id, product_id, hedef_fiyat) "
            "VALUES (10, 1, 1, 5000)"))
        b.execute(sa.text(
            "INSERT INTO set_uyeleri (watch_id, set_id) VALUES (10, 1)"))

    command.upgrade(cfg, YUZDE_ESIGI)

    with motor.begin() as b:
        izleme = b.execute(sa.text(
            "SELECT id, hedef_fiyat FROM watches")).one()
        uyelikler = list(b.execute(sa.text(
            "SELECT watch_id, set_id FROM set_uyeleri")))
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('watches')"))]

    assert izleme == (10, 5000), "izleme göçte bozuldu/kayboldu"
    assert uyelikler == [(10, 1)], "set üyeliği göçte kayboldu"
    for sutun in ("dusus_yuzdesi", "yeniden_kur_gun"):
        assert sutun in sutunlar, f"beklenen sütun eksik: {sutun}"

    command.downgrade(cfg, BAGLAM_SUTUNLARI)

    with motor.begin() as b:
        izleme = b.execute(sa.text(
            "SELECT id, hedef_fiyat FROM watches")).one()
        uyelikler = list(b.execute(sa.text(
            "SELECT watch_id, set_id FROM set_uyeleri")))
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('watches')"))]
    motor.dispose()

    assert izleme == (10, 5000), "geri almada izleme bozuldu/kayboldu"
    assert uyelikler == [(10, 1)], "geri almada set üyeliği kayboldu"
    for sutun in ("dusus_yuzdesi", "yeniden_kur_gun"):
        assert sutun not in sutunlar, f"geri almada sütun düşürülmemiş: {sutun}"


def test_stok_bosluklari_gocu_fiyatli_okumalari_korur(gecici_veritabani):
    """B4 — göçten ÖNCE yazılmış (hepsi fiyatlı) okumalar bozulmamalı ve
    hepsi `stokta_var=True` almalı — "eski okumalar stokta sayılır" kabul
    ölçütü. `batch_alter_table` burada GEREKLİ (`fiyat`in NOT NULL kısıtı
    kaldırılıyor); testin var oluş sebebi tam da `alembic check`in bunu
    DOĞRULAMAMASI (şemayı kontrol eder, veriyi değil)."""
    cfg, yol = gecici_veritabani

    command.upgrade(cfg, YUZDE_ESIGI)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi) "
            "VALUES (1, 'a@b.c', 'x', 0)"))
        b.execute(sa.text("INSERT INTO products (id, ad) VALUES (1, 'Ürün')"))
        b.execute(sa.text(
            "INSERT INTO sources (id, product_id, url, host, durum) "
            "VALUES (1, 1, 'https://m.com/u', 'm.com', 'OK')"))
        b.execute(sa.text(
            "INSERT INTO price_readings (id, source_id, product_id, fiyat, ts) "
            "VALUES (100, 1, 1, 45000, '2026-08-20 10:00:00'), "
            "(101, 1, 1, 44000, '2026-08-21 10:00:00')"))

    command.upgrade(cfg, STOK_BOSLUKLARI)

    with motor.begin() as b:
        okumalar = list(b.execute(sa.text(
            "SELECT id, fiyat, stokta_var FROM price_readings ORDER BY id")))
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('price_readings')"))]
    motor.dispose()

    assert okumalar == [(100, 45000, 1), (101, 44000, 1)], \
        "fiyatlı okumalar göçte bozuldu/kayboldu"
    assert "stokta_var" in sutunlar, "beklenen sütun eksik: stokta_var"


def test_stok_bosluklari_gocu_geri_alinca_stok_yok_satirlari_siler(gecici_veritabani):
    """Geri alma `fiyat`i yeniden NOT NULL yapıyor — göçten SONRA yazılmış
    `fiyat IS NULL` (stokta yok) satırlar bu kısıtla var olamaz, bilinçli
    olarak silinir. Fiyatlı satırlar dokunulmadan kalır."""
    cfg, yol = gecici_veritabani

    command.upgrade(cfg, STOK_BOSLUKLARI)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi) "
            "VALUES (1, 'a@b.c', 'x', 0)"))
        b.execute(sa.text("INSERT INTO products (id, ad) VALUES (1, 'Ürün')"))
        b.execute(sa.text(
            "INSERT INTO sources (id, product_id, url, host, durum) "
            "VALUES (1, 1, 'https://m.com/u', 'm.com', 'STOKTA_YOK')"))
        b.execute(sa.text(
            "INSERT INTO price_readings (id, source_id, product_id, fiyat, stokta_var, ts) "
            "VALUES (100, 1, 1, 45000, 1, '2026-08-20 10:00:00'), "
            "(101, 1, 1, NULL, 0, '2026-08-21 10:00:00')"))

    command.downgrade(cfg, YUZDE_ESIGI)

    with motor.begin() as b:
        kalanlar = list(b.execute(sa.text("SELECT id, fiyat FROM price_readings")))
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('price_readings')"))]
    motor.dispose()

    assert kalanlar == [(100, 45000)], "fiyatlı satır geri almada kaybolmamalı"
    assert "stokta_var" not in sutunlar, "geri almada sütun düşürülmemiş: stokta_var"


def test_oturum_surumu_gocu_kullanici_verisini_koruyor(gecici_veritabani):
    """BACKLOG dışı, güvenlik denetiminden gelen göç (users.oturum_surumu).

    Mevcut kullanıcılar 0'da başlamalı: token'ında `ver` olmayan açık
    oturumlar da 0 sayılıyor, yani göç KİMSENİN oturumunu kapatmamalı.
    """
    cfg, yol = gecici_veritabani
    command.upgrade(cfg, STOK_BOSLUKLARI)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi) "
            "VALUES (1, 'a@b.c', 'x', 0)"))
        b.execute(sa.text("INSERT INTO products (id, ad) VALUES (1, 'Ürün')"))
        b.execute(sa.text(
            "INSERT INTO watches (id, user_id, product_id) VALUES (1, 1, 1)"))
        b.execute(sa.text(
            "INSERT INTO alerts (id, user_id, watch_id, tur, baslik, mesaj) "
            "VALUES (1, 1, 1, 'DIP', 'b', 'm')"))

    command.upgrade(cfg, OTURUM_SURUMU)

    with motor.begin() as b:
        assert b.execute(sa.text("SELECT oturum_surumu FROM users")).scalar() == 0
        assert b.execute(sa.text("SELECT count(*) FROM watches")).scalar() == 1
        assert b.execute(sa.text("SELECT count(*) FROM alerts")).scalar() == 1
    motor.dispose()


def test_oturum_surumu_gocu_veri_varken_geri_alinabiliyor(gecici_veritabani):
    """BU TEST BİR ARIZADAN DOĞDU — ölçüldü.

    Göçün ilk hâli `op.batch_alter_table` kullanıyordu. Batch SQLite'ta
    tabloyu YENİDEN KURUYOR (`DROP TABLE users`) ve `PRAGMA foreign_keys=ON`
    (db.py) altında, `users`a bağlı GERÇEK SATIRLAR varken geri alma şununla
    patlıyor:

        sqlite3.IntegrityError: FOREIGN KEY constraint failed

    Boş veritabanında hiç görünmüyor — bu yüzden test veriyi ÖNCE yazıyor.
    Göç artık iki yönde de yerel `ALTER TABLE` kullanıyor (SQLite 3.35+),
    tablo yeniden kurulmadığı için hiçbir yabancı anahtar tetiklenmiyor.
    """
    cfg, yol = gecici_veritabani
    command.upgrade(cfg, OTURUM_SURUMU)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi) "
            "VALUES (1, 'a@b.c', 'x', 0)"))
        b.execute(sa.text("INSERT INTO products (id, ad) VALUES (1, 'Ürün')"))
        b.execute(sa.text(
            "INSERT INTO watches (id, user_id, product_id) VALUES (1, 1, 1)"))
        b.execute(sa.text(
            "INSERT INTO watch_sets (id, user_id, ad) VALUES (1, 1, 'Set')"))
        b.execute(sa.text(
            "INSERT INTO alerts (id, user_id, watch_id, tur, baslik, mesaj) "
            "VALUES (1, 1, 1, 'DIP', 'b', 'm')"))

    command.downgrade(cfg, STOK_BOSLUKLARI)

    with motor.begin() as b:
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('users')"))]
        assert "oturum_surumu" not in sutunlar
        # Asıl mesele: geri alma HİÇBİR SATIRI götürmemeli.
        assert b.execute(sa.text("SELECT count(*) FROM users")).scalar() == 1
        assert b.execute(sa.text("SELECT count(*) FROM watches")).scalar() == 1
        assert b.execute(sa.text("SELECT count(*) FROM watch_sets")).scalar() == 1
        assert b.execute(sa.text("SELECT count(*) FROM alerts")).scalar() == 1
    motor.dispose()


def test_telegram_deneme_gocu_bekleyen_uyarilari_dusurmuyor(gecici_veritabani):
    """Sayaç 0'dan başlamalı: göç, o an kuyrukta bekleyen bildirimlerin
    hiçbirini iptal etmemeli."""
    cfg, yol = gecici_veritabani
    command.upgrade(cfg, OTURUM_SURUMU)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi, "
            "oturum_surumu) VALUES (1, 'a@b.c', 'x', 0, 0)"))
        b.execute(sa.text(
            "INSERT INTO alerts (id, user_id, tur, baslik, mesaj, "
            "telegram_gonderildi) VALUES (1, 1, 'DIP', 'b', 'm', 0)"))

    command.upgrade(cfg, TELEGRAM_DENEME)

    with motor.begin() as b:
        satir = b.execute(sa.text(
            "SELECT telegram_deneme, telegram_gonderildi FROM alerts")).one()
    motor.dispose()
    assert satir == (0, 0), "bekleyen uyarı göçte bırakılmış sayılmamalı"


def test_telegram_deneme_gocu_veri_varken_geri_alinabiliyor(gecici_veritabani):
    """`c5f2a71e8d40` ile aynı tuzak: batch modu `alerts` tablosunu yeniden
    kurmaya kalkarsa gerçek veri varken patlar. Yerel ALTER kullanılıyor."""
    cfg, yol = gecici_veritabani
    command.upgrade(cfg, TELEGRAM_DENEME)

    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO users (id, email, password_hash, eposta_dogrulandi, "
            "oturum_surumu) VALUES (1, 'a@b.c', 'x', 0, 0)"))
        b.execute(sa.text("INSERT INTO products (id, ad) VALUES (1, 'Ürün')"))
        b.execute(sa.text(
            "INSERT INTO watches (id, user_id, product_id) VALUES (1, 1, 1)"))
        b.execute(sa.text(
            "INSERT INTO alerts (id, user_id, watch_id, tur, baslik, mesaj) "
            "VALUES (1, 1, 1, 'DIP', 'b', 'm')"))

    command.downgrade(cfg, OTURUM_SURUMU)

    with motor.begin() as b:
        sutunlar = [r[1] for r in b.execute(sa.text("PRAGMA table_info('alerts')"))]
        assert "telegram_deneme" not in sutunlar
        assert b.execute(sa.text("SELECT count(*) FROM alerts")).scalar() == 1
        assert b.execute(sa.text("SELECT count(*) FROM watches")).scalar() == 1
        assert b.execute(sa.text("SELECT count(*) FROM users")).scalar() == 1
    motor.dispose()

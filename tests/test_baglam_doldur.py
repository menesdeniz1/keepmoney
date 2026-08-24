"""`betikler/baglam_doldur.py` testi (BACKLOG A3).

NEDEN TEST EDİLİYOR: bu betik geriye dönük veri yazan tek seferlik bir araç
— aynı ürün için iki kez çalıştırıldığında SESSİZCE farklı bir sonuç
üretmesi (idempotent olmaması) fark edilmesi zor bir hata sınıfı olurdu.
Ayrıca `analiz.fiyat_baglami`'nin MIN_GUN eşiğinin altındaki ürünlerde
`gecmis_gun`ı hâlâ yazması (A7'nin "N/7 gün" göstergesinin temeli)
davranışın kendisi kadar önemli ve kolayca bozulabilir.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import timedelta

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

KOK = pathlib.Path(__file__).resolve().parents[1]
BETIK = KOK / "betikler" / "baglam_doldur.py"


def _betigi_yukle():
    """Betik paket içinde değil; dosya yolundan modül olarak yüklenir
    (test_kurulum.py ile aynı yaklaşım)."""
    spec = importlib.util.spec_from_file_location("baglam_doldur", BETIK)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["baglam_doldur"] = modul
    spec.loader.exec_module(modul)                       # type: ignore[union-attr]
    return modul


bd = _betigi_yukle()


@pytest.fixture
def gecici_veritabani(tmp_path, monkeypatch):
    """Boş bir SQLite dosyası, head'e göçürülmüş — gerçek veritabanına
    dokunmamak kritik (bkz. test_gocler.py aynı desen).

    EK YAMA GEREKİYOR (test_gocler.py'de yok, orası ham motor kullanıyor):
    `keepmoney.db.SessionLocal` ilk import anında TEK SEFER kuruluyor
    (bkz. db.py docstring: "Bağlantı adresini buradan başka hiçbir yerde
    okuma"). `KEEPMONEY_VERITABANI_URL` sonradan değiştirilse bile o motor
    GÜNCELLENMEZ — conftest.py `sys.modules` içinde `keepmoney.db`'yi test
    paketinin paylaşılan `data/test.sqlite`'ına bağlı hâlde tutar.
    `baglam_doldur.py` üretim kodundaki gibi `keepmoney.db.SessionLocal`ı
    kullandığı için (betikler DI almıyor — `linkleri_ekle.py` ile aynı
    desen), test bu iki niteliği GEÇİCİ dosyaya işaret edecek şekilde
    yamamalı. Yamamazsak betik sessizce paylaşılan test veritabanına
    yazar/okur ve bu test hiçbir şeyi doğrulamamış olur."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from keepmoney import db as db_modulu
    from keepmoney.ayarlar import ayarlar

    yol = tmp_path / "baglam-denemesi.sqlite"
    monkeypatch.setenv("KEEPMONEY_VERITABANI_URL", f"sqlite:///{yol}")
    ayarlar.cache_clear()

    command.upgrade(Config(str(KOK / "alembic.ini")), "head")

    gecici_motor = create_engine(f"sqlite:///{yol}",
                                 connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_modulu, "engine", gecici_motor)
    monkeypatch.setattr(
        db_modulu, "SessionLocal",
        sessionmaker(bind=gecici_motor, autocommit=False, autoflush=False))

    yield yol

    ayarlar.cache_clear()
    gecici_motor.dispose()


def _urun_ve_gecmis_ekle(yol, urun_id, ad, guncel_fiyat, gun_sayisi):
    """`gun_sayisi` FARKLI güne yayılan okuma ekler."""
    from keepmoney.zaman import utc_simdi

    simdi = utc_simdi()
    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO products (id, ad, guncel_fiyat) VALUES (:id, :ad, :f)"),
            {"id": urun_id, "ad": ad, "f": guncel_fiyat})
        b.execute(sa.text(
            "INSERT INTO sources (id, product_id, url, host) "
            "VALUES (:id, :pid, :url, 'test.com')"),
            {"id": urun_id, "pid": urun_id, "url": f"https://test.com/{urun_id}"})
        for gun in range(gun_sayisi, 0, -1):
            # `ts` ISO DİZGE olarak bağlanıyor: ham `sa.text()` bir Python
            # `datetime` nesnesini doğrudan sqlite3 sürücüsüne verirse
            # Python 3.12'de kullanımdan kaldırılmış varsayılan adaptöre
            # düşer (ORM'un DateTime tipi bunu kendi çevirir, ham SQL değil).
            b.execute(sa.text(
                "INSERT INTO price_readings (source_id, product_id, fiyat, ts) "
                "VALUES (:sid, :pid, :f, :ts)"),
                {"sid": urun_id, "pid": urun_id, "f": guncel_fiyat + gun,
                 "ts": (simdi - timedelta(days=gun)).isoformat()})
    motor.dispose()


def _urunu_oku(yol, urun_id):
    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        satir = b.execute(sa.text(
            "SELECT sinyal, dip90, medyan90, yuzdelik, gecmis_gun, baglam_ts "
            "FROM products WHERE id = :id"), {"id": urun_id}).one()
    motor.dispose()
    return dict(satir._mapping)


def test_yeterli_gecmiste_sinyal_doluyor(gecici_veritabani):
    """Kabul ölçütü: betik çalıştıktan sonra geçmişi olan üründe sinyal
    dolu."""
    yol = gecici_veritabani
    _urun_ve_gecmis_ekle(yol, urun_id=1, ad="Ekran Kartı",
                         guncel_fiyat=45000, gun_sayisi=6)

    kod = bd.main([])
    assert kod == 0

    satir = _urunu_oku(yol, 1)
    assert satir["sinyal"] in ("dip", "ucuz", "pahali")
    assert satir["dip90"] is not None
    assert satir["baglam_ts"] is not None
    assert satir["gecmis_gun"] == 6


def test_yetersiz_gecmiste_gecmis_gun_yine_de_yaziliyor(gecici_veritabani):
    """MIN_GUN (5) altındaki ürün: sinyal boş kalır ama `gecmis_gun` A7'nin
    "N/7 gün" göstergesi için yine de yazılmalı."""
    yol = gecici_veritabani
    _urun_ve_gecmis_ekle(yol, urun_id=1, ad="Yeni Ürün",
                         guncel_fiyat=1000, gun_sayisi=2)

    bd.main([])

    satir = _urunu_oku(yol, 1)
    assert satir["sinyal"] is None
    assert satir["gecmis_gun"] == 2


def test_iki_kez_calistirma_ayni_sonucu_verir(gecici_veritabani):
    """Kabul ölçütü: idempotent. `baglam_ts` (hesaplama zamanı) DIŞINDA
    hiçbir alan değişmemeli — girdi (fiyat geçmişi) değişmedi."""
    yol = gecici_veritabani
    _urun_ve_gecmis_ekle(yol, urun_id=1, ad="Ekran Kartı",
                         guncel_fiyat=45000, gun_sayisi=6)

    bd.main([])
    ilk = _urunu_oku(yol, 1)

    bd.main([])
    ikinci = _urunu_oku(yol, 1)

    for alan in ("sinyal", "dip90", "medyan90", "yuzdelik", "gecmis_gun"):
        assert ilk[alan] == ikinci[alan], f"idempotent değil: {alan}"


def test_deneme_modu_yazmaz(gecici_veritabani, capsys):
    """`--deneme` hiçbir sütunu değiştirmemeli, yalnızca ne olacağını
    göstermeli."""
    yol = gecici_veritabani
    _urun_ve_gecmis_ekle(yol, urun_id=1, ad="Ekran Kartı",
                         guncel_fiyat=45000, gun_sayisi=6)

    bd.main(["--deneme"])

    satir = _urunu_oku(yol, 1)
    assert satir["sinyal"] is None                # hiçbir şey yazılmadı
    assert satir["baglam_ts"] is None
    cikti = capsys.readouterr().out
    assert "deneme modu" in cikti


def test_gecmisi_olmayan_urun_atlanir(gecici_veritabani):
    """Hiç fiyat geçmişi olmayan ürün (yeni eklenmiş, hiç taranmamış)
    hatasız atlanmalı."""
    yol = gecici_veritabani
    motor = sa.create_engine(f"sqlite:///{yol}")
    with motor.begin() as b:
        b.execute(sa.text(
            "INSERT INTO products (id, ad, guncel_fiyat) VALUES (1, 'Yeni', NULL)"))
    motor.dispose()

    kod = bd.main([])
    assert kod == 0

    satir = _urunu_oku(yol, 1)
    assert satir["sinyal"] is None
    assert satir["baglam_ts"] is None

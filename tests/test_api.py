"""API testleri — gerçek HTTP çağrılarıyla, bellek içi veritabanında."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from keepmoney.api.app import uygulama_olustur
from keepmoney.db import Base, get_db
from keepmoney.models import Alert, PriceReading, Product, Source, Watch


@pytest.fixture
def oturum_fabrikasi():
    # StaticPool + tek bağlantı: bellek içi DB testler arası paylaşılsın
    motor = create_engine("sqlite:///:memory:", future=True,
                          connect_args={"check_same_thread": False},
                          poolclass=StaticPool)
    Base.metadata.create_all(motor)
    return sessionmaker(bind=motor)


@pytest.fixture
def istemci(oturum_fabrikasi):
    app = uygulama_olustur()

    def test_db():
        db = oturum_fabrikasi()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(oturum_fabrikasi):
    s = oturum_fabrikasi()
    yield s
    s.close()


def kayit_ol(istemci, eposta="a@ornek.com", parola="parola1234") -> dict:
    istemci.post("/api/auth/kayit", json={"eposta": eposta, "parola": parola})
    y = istemci.post("/api/auth/giris",
                     json={"eposta": eposta, "parola": parola})
    token = y.json()["erisim_tokeni"]
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────── sistem ───────────────────────────

def test_saglik(istemci):
    y = istemci.get("/saglik")
    assert y.status_code == 200
    assert y.json()["durum"] == "ayakta"


def test_openapi_uretiliyor(istemci):
    y = istemci.get("/openapi.json")
    assert y.status_code == 200
    yollar = y.json()["paths"]
    assert "/api/izlemeler" in yollar
    assert "/api/auth/giris" in yollar


# ─────────────────────────── kimlik ───────────────────────────

def test_kayit_ve_giris(istemci):
    y = istemci.post("/api/auth/kayit",
                     json={"eposta": "yeni@ornek.com", "parola": "parola1234"})
    assert y.status_code == 201
    assert y.json()["eposta"] == "yeni@ornek.com"

    y = istemci.post("/api/auth/giris",
                     json={"eposta": "yeni@ornek.com", "parola": "parola1234"})
    assert y.status_code == 200
    assert y.json()["erisim_tokeni"]


def test_ayni_eposta_iki_kez_kayit_olamaz(istemci):
    istemci.post("/api/auth/kayit",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})
    y = istemci.post("/api/auth/kayit",
                     json={"eposta": "a@ornek.com", "parola": "baska1234"})
    assert y.status_code == 409


def test_yanlis_parola_401(istemci):
    istemci.post("/api/auth/kayit",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})
    y = istemci.post("/api/auth/giris",
                     json={"eposta": "a@ornek.com", "parola": "yanlis1234"})
    assert y.status_code == 401


def test_olmayan_kullanici_ayni_hatayi_verir(istemci):
    """Kullanıcı numaralandırmayı önler: 'yok' ile 'parola yanlış' ayrımı
    hangi e-postaların kayıtlı olduğunu sızdırır."""
    y = istemci.post("/api/auth/giris",
                     json={"eposta": "yok@ornek.com", "parola": "parola1234"})
    assert y.status_code == 401
    assert "hatalı" in y.json()["detail"].lower()


def test_kisa_parola_reddedilir(istemci):
    y = istemci.post("/api/auth/kayit",
                     json={"eposta": "a@ornek.com", "parola": "kisa"})
    assert y.status_code == 422


def test_gecersiz_eposta_reddedilir(istemci):
    y = istemci.post("/api/auth/kayit",
                     json={"eposta": "eposta-degil", "parola": "parola1234"})
    assert y.status_code == 422


def test_token_olmadan_401(istemci):
    assert istemci.get("/api/izlemeler").status_code == 401


def test_bozuk_token_401(istemci):
    y = istemci.get("/api/izlemeler",
                    headers={"Authorization": "Bearer sacmasapan"})
    assert y.status_code == 401


def test_ben_kendi_bilgisini_doner(istemci):
    b = kayit_ol(istemci)
    y = istemci.get("/api/auth/ben", headers=b)
    assert y.status_code == 200
    assert y.json()["eposta"] == "a@ornek.com"
    assert y.json()["telegram_bagli"] is False


# ─────────────────────────── izleme ───────────────────────────

def test_link_yapistirinca_izlemeye_alinir(istemci):
    b = kayit_ol(istemci)
    y = istemci.post("/api/izlemeler", headers=b, json={
        "url": "https://www.magaza.com/urun/rtx-5070-ti", "hedef_fiyat": 50000})
    assert y.status_code == 201
    veri = y.json()
    assert veri["hedef_fiyat"] == 50000
    assert veri["urun"]["ad"]           # URL'den geçici ad üretildi
    assert veri["aktif"] is True


def test_izleme_listelenir(istemci):
    b = kayit_ol(istemci)
    istemci.post("/api/izlemeler", headers=b,
                 json={"url": "https://magaza.com/a"})
    istemci.post("/api/izlemeler", headers=b,
                 json={"url": "https://magaza.com/b"})
    y = istemci.get("/api/izlemeler", headers=b)
    assert len(y.json()) == 2


def test_ayni_urun_iki_kez_eklenemez(istemci):
    b = kayit_ol(istemci)
    istemci.post("/api/izlemeler", headers=b,
                 json={"url": "https://magaza.com/a"})
    y = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"})
    assert y.status_code == 400


def test_takip_parametreleri_ayni_urune_duser(istemci, db):
    """KRİTİK: kampanya etiketli link aynı kaynağa düşmeli, yoksa aynı sayfa
    iki kez taranır ve fiyat geçmişi ikiye bölünür."""
    b = kayit_ol(istemci)
    istemci.post("/api/izlemeler", headers=b, json={
        "url": "https://www.magaza.com/urun/x?utm_source=google&gclid=abc"})
    y = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/urun/x"})
    assert y.status_code == 400          # zaten izliyorsun
    assert db.query(Source).count() == 1


def test_iki_kullanici_ayni_urunu_paylasir(istemci, db):
    """Küresel ürün modelinin varlık sebebi."""
    a = kayit_ol(istemci, "a@ornek.com")
    c = kayit_ol(istemci, "c@ornek.com")
    url = "https://magaza.com/paylasilan"
    assert istemci.post("/api/izlemeler", headers=a,
                        json={"url": url}).status_code == 201
    assert istemci.post("/api/izlemeler", headers=c,
                        json={"url": url}).status_code == 201

    assert db.query(Product).count() == 1
    assert db.query(Source).count() == 1
    assert db.query(Watch).count() == 2
    assert db.query(Product).one().izleyen_sayisi == 2


def test_baskasinin_izlemesi_gorunmez(istemci):
    a = kayit_ol(istemci, "a@ornek.com")
    c = kayit_ol(istemci, "c@ornek.com")
    y = istemci.post("/api/izlemeler", headers=a,
                     json={"url": "https://magaza.com/gizli"})
    izleme_id = y.json()["id"]

    assert istemci.get(f"/api/izlemeler/{izleme_id}", headers=c).status_code == 404
    assert istemci.get("/api/izlemeler", headers=c).json() == []


def test_hedef_guncellenir(istemci):
    b = kayit_ol(istemci)
    y = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"})
    i = y.json()["id"]
    y = istemci.patch(f"/api/izlemeler/{i}", headers=b,
                      json={"hedef_fiyat": 42000})
    assert y.json()["hedef_fiyat"] == 42000


def test_susturma_gun_olarak_verilir(istemci):
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    y = istemci.patch(f"/api/izlemeler/{i}", headers=b, json={"sustur_gun": 7})
    assert y.json()["sustur_bitis"] is not None


def test_izleme_silinince_sayac_duser(istemci, db):
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    assert istemci.delete(f"/api/izlemeler/{i}", headers=b).status_code == 204
    assert db.query(Product).one().izleyen_sayisi == 0


def test_izleme_silinince_kuresel_gecmis_kalir(istemci, db):
    """Birinin vazgeçmesi diğerlerinin fiyat hafızasını silmemeli."""
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    urun = db.query(Product).one()
    kaynak = db.query(Source).one()
    db.add(PriceReading(product_id=urun.id, source_id=kaynak.id, fiyat=1000))
    db.commit()

    istemci.delete(f"/api/izlemeler/{i}", headers=b)
    assert db.query(PriceReading).count() == 1
    assert db.query(Product).count() == 1


def test_kota_asilinca_402(istemci, monkeypatch):
    from keepmoney import ayarlar as ayar_modul
    ayar_modul.ayarlar.cache_clear()
    monkeypatch.setenv("KEEPMONEY_KULLANICI_BASINA_IZLEME_LIMITI", "2")
    monkeypatch.setenv("KEEPMONEY_JWT_GIZLI_ANAHTAR", "test" * 8)

    b = kayit_ol(istemci)
    for n in range(2):
        assert istemci.post("/api/izlemeler", headers=b, json={
            "url": f"https://magaza.com/{n}"}).status_code == 201
    y = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/fazla"})
    assert y.status_code == 402
    ayar_modul.ayarlar.cache_clear()


def test_detay_grafik_ve_yorum_dondurur(istemci, db):
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]

    urun = db.query(Product).one()
    kaynak = db.query(Source).one()
    from datetime import timedelta

    from keepmoney.zaman import utc_simdi
    for gun, fiyat in enumerate([1000, 1000, 1000, 1000, 1000, 850]):
        db.add(PriceReading(product_id=urun.id, source_id=kaynak.id,
                            fiyat=fiyat,
                            ts=utc_simdi() - timedelta(days=5 - gun)))
    urun.guncel_fiyat = 850
    db.commit()

    y = istemci.get(f"/api/izlemeler/{i}", headers=b)
    assert y.status_code == 200
    urun_veri = y.json()["urun"]
    assert len(urun_veri["gecmis"]) == 6          # gün başına tek nokta
    baglam = urun_veri["baglam"]
    assert baglam["sinyal"] == "dip"
    assert "en düşüğü" in baglam["yorum"] or "dip" in baglam["yorum"].lower()


# ─────────────────────────── set ───────────────────────────

def test_set_olustur_ve_toplam(istemci, db):
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b,
                     json={"ad": "PC Toplama", "hedef_butce": 100000}).json()
    assert s["toplam"] == 0

    for n, fiyat in enumerate([30000, 60000]):
        i = istemci.post("/api/izlemeler", headers=b, json={
            "url": f"https://magaza.com/{n}", "set_id": s["id"]}).json()["id"]
        w = db.query(Watch).filter(Watch.id == i).one()
        w.product.guncel_fiyat = fiyat
    db.commit()

    y = istemci.get(f"/api/setler/{s['id']}", headers=b).json()
    assert y["toplam"] == 90000
    assert y["uye_sayisi"] == 2
    assert y["hedefte"] is True


def test_eksik_uyeli_set_hedefte_demez(istemci, db):
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b,
                     json={"ad": "Set", "hedef_butce": 100000}).json()
    i = istemci.post("/api/izlemeler", headers=b, json={
        "url": "https://magaza.com/a", "set_id": s["id"]}).json()["id"]
    istemci.post("/api/izlemeler", headers=b, json={
        "url": "https://magaza.com/b", "set_id": s["id"]})

    w = db.query(Watch).filter(Watch.id == i).one()
    w.product.guncel_fiyat = 1000
    db.commit()

    y = istemci.get(f"/api/setler/{s['id']}", headers=b).json()
    assert y["eksik_uye"] == 1
    assert y["hedefte"] is False


def test_set_silinince_uyeler_silinmez(istemci, db):
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b, json={"ad": "Set"}).json()
    istemci.post("/api/izlemeler", headers=b, json={
        "url": "https://magaza.com/a", "set_id": s["id"]})

    assert istemci.delete(f"/api/setler/{s['id']}", headers=b).status_code == 204
    assert db.query(Watch).count() == 1
    assert db.query(Watch).one().set_id is None


def test_baskasinin_setine_urun_eklenemez(istemci):
    a = kayit_ol(istemci, "a@ornek.com")
    c = kayit_ol(istemci, "c@ornek.com")
    s = istemci.post("/api/setler", headers=a, json={"ad": "Gizli"}).json()
    y = istemci.post("/api/izlemeler", headers=c, json={
        "url": "https://magaza.com/a", "set_id": s["id"]})
    assert y.status_code == 400


# ─────────────────────────── uyarı ───────────────────────────

def test_uyari_listesi_ve_okundu(istemci, db):
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    w = db.query(Watch).filter(Watch.id == i).one()
    db.add(Alert(user_id=w.user_id, watch_id=w.id, tur="HEDEF",
                 baslik="Fiyat düştü", mesaj="Hedefin altına indi"))
    db.commit()

    assert istemci.get("/api/uyarilar/sayi", headers=b).json()["okunmamis"] == 1

    uyarilar = istemci.get("/api/uyarilar", headers=b).json()
    assert len(uyarilar) == 1

    assert istemci.post(f"/api/uyarilar/{uyarilar[0]['id']}/okundu",
                        headers=b).status_code == 204
    assert istemci.get("/api/uyarilar/sayi", headers=b).json()["okunmamis"] == 0


def test_baskasinin_uyarisi_gorunmez(istemci, db):
    a = kayit_ol(istemci, "a@ornek.com")
    c = kayit_ol(istemci, "c@ornek.com")
    i = istemci.post("/api/izlemeler", headers=a,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    w = db.query(Watch).filter(Watch.id == i).one()
    db.add(Alert(user_id=w.user_id, watch_id=w.id, tur="HEDEF",
                 baslik="Gizli", mesaj="x"))
    db.commit()

    assert istemci.get("/api/uyarilar", headers=c).json() == []

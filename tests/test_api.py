"""API testleri — gerçek HTTP çağrılarıyla, bellek içi veritabanında."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from keepmoney.api.app import uygulama_olustur
from keepmoney.db import get_db
from keepmoney.models import Alert, PriceReading, Product, Source, Watch


@pytest.fixture
def oturum_fabrikasi(motor):
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


def test_liste_ucu_sinyali_donduruyor(istemci, db):
    """BACKLOG A4: sinyal artık ürüne tıklamadan panelde görünüyor.

    `worker.py` bu sütunları A2'de yazıyor; burada doğrudan `Product`
    üzerinde kurup liste ucunun bunu OKUDUĞUNU doğruluyoruz."""
    b = kayit_ol(istemci)
    istemci.post("/api/izlemeler", headers=b, json={"url": "https://magaza.com/a"})

    urun = db.query(Product).one()
    urun.sinyal = "dip"
    urun.dip90 = 850.0
    urun.medyan90 = 1000.0
    urun.yuzdelik = 92
    urun.gecmis_gun = 14
    db.commit()

    y = istemci.get("/api/izlemeler", headers=b)
    veri = y.json()[0]["urun"]
    assert veri["sinyal"] == "dip"
    assert veri["dip90"] == 850.0
    assert veri["medyan90"] == 1000.0
    assert veri["yuzdelik"] == 92
    assert veri["gecmis_gun"] == 14


def test_liste_ucu_gecmisi_olmayan_urunde_null_doner(istemci):
    """Kabul ölçütü: geçmişi olmayan üründe beş alan da null, istek hata
    vermiyor — yeni eklenen bir ürün henüz hiç taranmamış olabilir."""
    b = kayit_ol(istemci)
    istemci.post("/api/izlemeler", headers=b, json={"url": "https://magaza.com/a"})

    y = istemci.get("/api/izlemeler", headers=b)
    assert y.status_code == 200
    veri = y.json()[0]["urun"]
    for alan in ("sinyal", "dip90", "medyan90", "yuzdelik", "gecmis_gun"):
        assert veri[alan] is None, f"{alan} null olmalıydı: {veri[alan]}"


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


def test_detay_ucu_kaydedilmis_baglam_sutunlarini_da_dondurur(istemci, db):
    """BACKLOG A7'de GERÇEK TARAYICIDA yakalandı: `urun_svc.detay()` bir
    sözlük döndürüyordu ve bu sözlükte A4'ün beş alanı (sinyal, dip90,
    medyan90, yuzdelik, gecmis_gun) hiç yoktu — Pydantic eksik anahtarı
    şemanın varsayılanıyla (None) dolduruyordu. Sonuç: detay sayfasında
    grafik veri gösterirken analiz kutusu "hiç fiyat okunmadı" diyordu,
    DB'de gecmis_gun=4 yazılı olsa bile.

    Liste ucu (`test_liste_ucu_sinyali_donduruyor`, A4) aynı sütunları
    zaten doğru döndürüyordu — hata yalnızca DETAY ucundaydı, ikisi aynı
    Product sütununu farklı kod yollarından okuyor."""
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]

    urun = db.query(Product).one()
    urun.sinyal = "ucuz"
    urun.dip90 = 850.0
    urun.medyan90 = 1000.0
    urun.yuzdelik = 60
    urun.gecmis_gun = 4
    db.commit()

    y = istemci.get(f"/api/izlemeler/{i}", headers=b)
    urun_veri = y.json()["urun"]
    assert urun_veri["sinyal"] == "ucuz"
    assert urun_veri["dip90"] == 850.0
    assert urun_veri["medyan90"] == 1000.0
    assert urun_veri["yuzdelik"] == 60
    assert urun_veri["gecmis_gun"] == 4


# ─────────────────────────── set ───────────────────────────

def test_set_olustur_ve_toplam(istemci, db):
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b,
                     json={"ad": "PC Toplama", "hedef_butce": 100000}).json()
    assert s["toplam"] == 0

    for n, fiyat in enumerate([30000, 60000]):
        i = istemci.post("/api/izlemeler", headers=b, json={
            "url": f"https://magaza.com/{n}", "set_idler": [s["id"]]}).json()["id"]
        w = db.query(Watch).filter(Watch.id == i).one()
        w.product.guncel_fiyat = fiyat
    db.commit()

    y = istemci.get(f"/api/setler/{s['id']}", headers=b).json()
    assert y["toplam"] == 90000
    assert y["uye_sayisi"] == 2
    assert y["hedefte"] is True


def test_bos_set_hedefte_demez(istemci, db):
    """Üyesi olmayan set "🎯 bütçe altında" DEMEZ.

    Eskiden derdi: üye yokken `eksik == 0` ve `toplam (0) <= bütçe` sağlanıyor,
    kullanıcı seti kurar kurmaz yeşil rozeti görüyordu. Hiçbir şey almadan
    bütçenin altında olmak bir başarı değil, boş bir listedir — bu, eksik
    üyeli sette zaten uygulanan ilkenin (aşağıdaki test) uç hâli.
    """
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b,
                     json={"ad": "Boş set", "hedef_butce": 100000}).json()

    y = istemci.get(f"/api/setler/{s['id']}", headers=b).json()
    assert y["uye_sayisi"] == 0
    assert y["toplam"] == 0
    assert y["hedefte"] is False


def test_eksik_uyeli_set_hedefte_demez(istemci, db):
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b,
                     json={"ad": "Set", "hedef_butce": 100000}).json()
    i = istemci.post("/api/izlemeler", headers=b, json={
        "url": "https://magaza.com/a", "set_idler": [s["id"]]}).json()["id"]
    istemci.post("/api/izlemeler", headers=b, json={
        "url": "https://magaza.com/b", "set_idler": [s["id"]]})

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
        "url": "https://magaza.com/a", "set_idler": [s["id"]]})

    assert istemci.delete(f"/api/setler/{s['id']}", headers=b).status_code == 204
    assert db.query(Watch).count() == 1
    # Üyelik satırı gider (ON DELETE CASCADE), izlemenin kendisi kalır.
    assert db.query(Watch).one().setler == []


def test_baskasinin_setine_urun_eklenemez(istemci):
    a = kayit_ol(istemci, "a@ornek.com")
    c = kayit_ol(istemci, "c@ornek.com")
    s = istemci.post("/api/setler", headers=a, json={"ad": "Gizli"}).json()
    y = istemci.post("/api/izlemeler", headers=c, json={
        "url": "https://magaza.com/a", "set_idler": [s["id"]]})
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


# ─────────────────────── çerez tabanlı oturum ───────────────────────

def test_giris_httponly_cerez_kurar(istemci):
    """Tarayıcı istemcisi token'a hiç dokunmaz — XSS ile çalınamaz."""
    istemci.post("/api/auth/kayit",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})
    y = istemci.post("/api/auth/giris",
                     json={"eposta": "a@ornek.com", "parola": "parola1234"})
    cerez = y.headers["set-cookie"]
    assert "km_oturum=" in cerez
    assert "HttpOnly" in cerez
    assert "SameSite=lax" in cerez.replace("samesite", "SameSite")


def test_cerezle_kimlik_dogrulanir(istemci):
    """Authorization başlığı OLMADAN, sadece çerezle."""
    istemci.post("/api/auth/kayit",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})
    istemci.post("/api/auth/giris",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})
    y = istemci.get("/api/auth/ben")          # TestClient çerezi taşır
    assert y.status_code == 200
    assert y.json()["eposta"] == "a@ornek.com"


def test_cikis_cerezi_siler(istemci):
    istemci.post("/api/auth/kayit",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})
    istemci.post("/api/auth/giris",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})
    assert istemci.post("/api/auth/cikis").status_code == 204
    istemci.cookies.clear()
    assert istemci.get("/api/auth/ben").status_code == 401


def test_bearer_hala_calisir(istemci):
    """Programatik istemciler için standart yol korunuyor."""
    b = kayit_ol(istemci)
    istemci.cookies.clear()
    assert istemci.get("/api/auth/ben", headers=b).status_code == 200


# ─────────────────────── sistem uçları ───────────────────────

def test_saglik_veritabanina_dokunur(istemci):
    """Sadece 'ayakta' dönen uç, DB düşmüşken de sağlıklı görünür."""
    y = istemci.get("/saglik")
    assert y.status_code == 200
    assert y.json()["veritabani"] == "ayakta"


def test_metrics_prometheus_bicimi(istemci):
    y = istemci.get("/metrics")
    assert y.status_code == 200
    assert "keepmoney_" in y.text


def test_domain_sagligi_oran_hesaplar(istemci, db):
    from keepmoney.models import DomainHealth
    b = kayit_ol(istemci)
    db.add(DomainHealth(domain="magaza.com", basarili=8, basarisiz=2,
                        son_durum="OK"))
    db.commit()

    y = istemci.get("/api/sistem/domainler", headers=b)
    assert y.status_code == 200
    kayit = y.json()[0]
    assert kayit["domain"] == "magaza.com"
    assert kayit["basari_orani"] == 80.0


def test_sistem_ozeti_bayat_urunu_sayar(istemci, db):
    from datetime import timedelta

    from keepmoney.models import Product
    from keepmoney.zaman import utc_simdi

    b = kayit_ol(istemci)
    db.add(Product(ad="Taze", son_kontrol=utc_simdi()))
    db.add(Product(ad="Bayat", son_kontrol=utc_simdi() - timedelta(days=3)))
    db.add(Product(ad="Hiç okunmamış"))
    db.commit()

    y = istemci.get("/api/sistem/ozet", headers=b).json()
    assert y["toplam_urun"] == 3
    assert y["bayat_urun"] == 2


def test_sistem_uclari_kimlik_ister(istemci):
    assert istemci.get("/api/sistem/domainler").status_code == 401


def test_kaynak_cikis_linki_dondurur(istemci, db):
    """Ortaklık kuralı olmayan mağazada çıkış linki = kanonik URL."""
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/urun/x"}).json()["id"]
    y = istemci.get(f"/api/izlemeler/{i}", headers=b).json()
    kaynak = y["urun"]["kaynaklar"][0]
    assert kaynak["cikis_url"] == kaynak["url"]
    assert kaynak["ortaklik"] is False


# ─────────────────────── güvenlik: hız sınırı ───────────────────────

def test_giris_brute_force_frenleniyor(istemci):
    """OWASP A07 — sözlük saldırısını ekonomik olmaktan çıkarır."""
    from keepmoney.ayarlar import ayarlar as _a

    GIRIS_LIMIT = _a().giris_limiti

    istemci.post("/api/auth/kayit",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})

    for _ in range(GIRIS_LIMIT):
        y = istemci.post("/api/auth/giris",
                         json={"eposta": "a@ornek.com", "parola": "yanlis1234"})
        assert y.status_code == 401

    y = istemci.post("/api/auth/giris",
                     json={"eposta": "a@ornek.com", "parola": "yanlis1234"})
    assert y.status_code == 429
    assert "Retry-After" in y.headers


def test_dogru_parola_sayaci_sifirlar(istemci):
    """Meşru kullanıcı, birkaç yanlış denemeden sonra kilitlenmemeli."""
    from keepmoney.ayarlar import ayarlar as _a

    GIRIS_LIMIT = _a().giris_limiti

    istemci.post("/api/auth/kayit",
                 json={"eposta": "a@ornek.com", "parola": "parola1234"})
    for _ in range(GIRIS_LIMIT - 1):
        istemci.post("/api/auth/giris",
                     json={"eposta": "a@ornek.com", "parola": "yanlis"})

    assert istemci.post("/api/auth/giris",
                        json={"eposta": "a@ornek.com",
                              "parola": "parola1234"}).status_code == 200
    # Sayaç sıfırlandı: yeniden limit kadar hakkı var
    for _ in range(GIRIS_LIMIT):
        assert istemci.post("/api/auth/giris",
                            json={"eposta": "a@ornek.com",
                                  "parola": "yanlis"}).status_code == 401


def test_kayit_spam_frenleniyor(istemci):
    from keepmoney.ayarlar import ayarlar as _a

    KAYIT_LIMIT = _a().kayit_limiti

    for n in range(KAYIT_LIMIT):
        assert istemci.post("/api/auth/kayit", json={
            "eposta": f"k{n}@ornek.com", "parola": "parola1234"}).status_code == 201

    y = istemci.post("/api/auth/kayit",
                     json={"eposta": "fazla@ornek.com", "parola": "parola1234"})
    assert y.status_code == 429


# ─────────────────────── güvenlik: başlıklar ───────────────────────

def test_guvenlik_basliklari_gonderiliyor(istemci):
    """OWASP A05 — clickjacking, MIME sniffing, referrer sızıntısı."""
    b = istemci.get("/saglik").headers
    assert b["X-Content-Type-Options"] == "nosniff"
    assert b["X-Frame-Options"] == "DENY"
    assert "strict-origin" in b["Referrer-Policy"]
    csp = b["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_hsts_yalnizca_uretimde(istemci):
    """Yerelde HSTS tarayıcıda kalıcı kaydolup geliştirmeyi bozar."""
    assert "Strict-Transport-Security" not in istemci.get("/saglik").headers


# ─────────────────────── güvenlik: SSRF ───────────────────────

def test_ic_ag_adresi_izlemeye_alinamaz(istemci):
    """OWASP A10 — bulut metadata ucu IAM anahtarı döndürür."""
    b = kayit_ol(istemci)
    for kotu in ("https://169.254.169.254/latest/meta-data/",
                 "https://127.0.0.1:5432/",
                 "https://10.0.0.5/admin"):
        y = istemci.post("/api/izlemeler", headers=b, json={"url": kotu})
        assert y.status_code == 400, kotu
        assert "izlenemez" in y.json()["detail"]


def test_http_disi_sema_reddedilir(istemci):
    b = kayit_ol(istemci)
    y = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "file:///etc/passwd"})
    assert y.status_code == 422        # pydantic HttpUrl zaten eler


# ─────────────────── kısmi güncelleme (PATCH) semantiği ───────────────────

def test_hedef_fiyat_temizlenebilir(istemci):
    """PATCH'te açık `null` "değeri sil" demektir.

    Eskiden döngü `if deger is not None` ile ilerliyordu; bu yüzden hedef
    fiyat bir kez konduktan sonra API'den ASLA kaldırılamıyordu — kullanıcı
    hedefi silmek isteyince tek çare izlemeyi silip yeniden eklemekti.
    """
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    istemci.patch(f"/api/izlemeler/{i}", headers=b, json={"hedef_fiyat": 42000})

    y = istemci.patch(f"/api/izlemeler/{i}", headers=b,
                      json={"hedef_fiyat": None})
    assert y.status_code == 200
    assert y.json()["hedef_fiyat"] is None


def test_acil_fiyat_ve_set_de_temizlenebilir(istemci):
    b = kayit_ol(istemci)
    set_id = istemci.post("/api/setler", headers=b,
                          json={"ad": "PC"}).json()["id"]
    i = istemci.post("/api/izlemeler", headers=b, json={
        "url": "https://magaza.com/a", "acil_fiyat": 100,
        "set_idler": [set_id]}).json()["id"]

    # Boş liste = "hiçbir sette olmasın" (silme değil, tanım).
    y = istemci.patch(f"/api/izlemeler/{i}", headers=b,
                      json={"acil_fiyat": None, "set_idler": []})
    assert y.json()["acil_fiyat"] is None
    assert y.json()["set_idler"] == []


def test_dokunulmayan_alan_korunur(istemci):
    """`exclude_unset` sayesinde GÖNDERİLMEYEN alan sıfırlanmamalı —
    "null = temizle" kuralının bedeli bu olmamalı."""
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a",
                           "hedef_fiyat": 500}).json()["id"]

    y = istemci.patch(f"/api/izlemeler/{i}", headers=b, json={"aktif": False})
    assert y.json()["hedef_fiyat"] == 500      # dokunulmadı
    assert y.json()["aktif"] is False


def test_bilinmeyen_alan_sessizce_yutulmaz(istemci, db):
    """Toplu atama (mass assignment) savunması.

    Şema bilinmeyen anahtarı zaten düşürüyor; asıl korumayı servis katmanı
    yapıyor — bot da aynı fonksiyonu çağırıyor ve orada Pydantic yok.
    """
    from keepmoney.models import User
    from keepmoney.servisler import izleme as svc

    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]

    k = db.query(User).one()
    with pytest.raises(svc.IzlemeHatasi):
        svc.guncelle(db, k, i, user_id=999)
    with pytest.raises(svc.IzlemeHatasi):
        svc.guncelle(db, k, i, son_bildirim_ts=None)

    assert db.query(Watch).one().user_id == k.id


def test_hedef_degisince_bildirim_gecmisi_sifirlanir(istemci, db):
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    w = db.query(Watch).one()
    w.son_bildirim_fiyat = 999
    w.sustur_bitis = None
    db.commit()

    istemci.patch(f"/api/izlemeler/{i}", headers=b, json={"hedef_fiyat": 100})
    db.expire_all()
    assert db.query(Watch).one().son_bildirim_fiyat is None


def test_ayni_hedef_yeniden_gonderilince_susturma_bozulmaz(istemci, db):
    """Arayüz aynı değeri geri gönderebiliyor; bu bir DEĞİŞİKLİK değildir ve
    kullanıcının kurduğu susturmayı kaldırmamalı."""
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a",
                           "hedef_fiyat": 100}).json()["id"]
    istemci.patch(f"/api/izlemeler/{i}", headers=b, json={"sustur_gun": 7})

    y = istemci.patch(f"/api/izlemeler/{i}", headers=b,
                      json={"hedef_fiyat": 100})
    assert y.json()["sustur_bitis"] is not None


def test_ayni_istekte_hedef_ve_susturma_birlikte_calisir(istemci):
    """Eskiden hedef değişikliği susturmayı SESSİZCE eziyordu: kullanıcı
    "hedefi 100 yap ve 7 gün sustur" dediğinde susturma kayboluyordu."""
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]

    y = istemci.patch(f"/api/izlemeler/{i}", headers=b,
                      json={"hedef_fiyat": 100, "sustur_gun": 7})
    assert y.json()["hedef_fiyat"] == 100
    assert y.json()["sustur_bitis"] is not None


# ─────────────────── sorgu sayısı (N+1) ───────────────────

def test_izleme_listesi_n_arti_bir_sorgu_yapmaz(istemci, db):
    """Liste hem web ana ekranında hem /liste komutunda her açılışta çekilir.

    `selectinload` olmadan her satırın ürünü ayrı SELECT açar; 20 izleme
    21 sorgu eder. Sabit sayı sınırı, gelecekte biri `.options()` satırını
    silerse testin bunu yakalamasını sağlar.
    """
    from sqlalchemy import event

    b = kayit_ol(istemci)
    for n in range(12):
        istemci.post("/api/izlemeler", headers=b,
                     json={"url": f"https://magaza.com/urun-{n}"})

    sorgular: list[str] = []
    motor = db.get_bind()

    def yakala(conn, cursor, ifade, *a, **kw):
        sorgular.append(ifade)

    event.listen(motor, "before_cursor_execute", yakala)
    try:
        y = istemci.get("/api/izlemeler", headers=b)
    finally:
        event.remove(motor, "before_cursor_execute", yakala)

    assert len(y.json()) == 12
    secmeler = [s for s in sorgular if s.lstrip().upper().startswith("SELECT")]
    # kullanıcı + izlemeler + ürünler = 3; N+1 olsaydı 14+ olurdu
    assert len(secmeler) <= 4, f"{len(secmeler)} SELECT: {secmeler}"


# ─────────────────── kıvılcım ucu (BACKLOG A5) ───────────────────

def _gecmis_ekle(db, urun_id, kaynak_id, fiyat_gun_listesi):
    """`[(fiyat, kac_gun_once), ...]` biçiminde okuma ekler."""
    from datetime import timedelta

    from keepmoney.zaman import utc_simdi

    simdi = utc_simdi()
    for fiyat, gun_once in fiyat_gun_listesi:
        db.add(PriceReading(product_id=urun_id, source_id=kaynak_id,
                            fiyat=fiyat, ts=simdi - timedelta(days=gun_once)))
    db.commit()


def test_kivilcimlar_tek_sorgu_aciyor(istemci, db):
    """Kabul ölçütü: uç TEK SQL sorgusu açıyor. Toplam beklenen 2: biri
    kimlik doğrulama (`db.get(User, ...)`, her uçta ödenen sabit maliyet),
    biri kıvılcım JOIN'i — ürün/izleme SAYISINDAN BAĞIMSIZ olmalı."""
    from sqlalchemy import event

    b = kayit_ol(istemci)
    for n in range(8):
        istemci.post("/api/izlemeler", headers=b,
                     json={"url": f"https://magaza.com/urun-{n}"})

    urunler = db.query(Product).all()
    kaynaklar = {k.product_id: k for k in db.query(Source).all()}
    for urun in urunler:
        _gecmis_ekle(db, urun.id, kaynaklar[urun.id].id,
                    [(1000 + g, g) for g in range(5)])

    sorgular: list[str] = []
    motor = db.get_bind()

    def yakala(conn, cursor, ifade, *a, **kw):
        sorgular.append(ifade)

    event.listen(motor, "before_cursor_execute", yakala)
    try:
        y = istemci.get("/api/izlemeler/kivilcimlar", headers=b)
    finally:
        event.remove(motor, "before_cursor_execute", yakala)

    assert y.status_code == 200
    assert len(y.json()) == 8                # 8 izlemenin hepsinde geçmiş var
    secmeler = [s for s in sorgular if s.lstrip().upper().startswith("SELECT")]
    assert len(secmeler) <= 2, f"{len(secmeler)} SELECT: {secmeler}"


def test_kivilcimlar_gecmisi_olmayan_izleme_sozlukte_yok(istemci, db):
    """Kabul ölçütü: geçmişi olmayan izleme BOŞ DİZİ değil, sözlükte hiç
    görünmüyor — "veri yok" ile "sıfır günlük geçmiş" ayrımı."""
    b = kayit_ol(istemci)
    gecmisli = istemci.post("/api/izlemeler", headers=b,
                           json={"url": "https://magaza.com/a"}).json()["id"]
    gecmissiz = istemci.post("/api/izlemeler", headers=b,
                            json={"url": "https://magaza.com/b"}).json()["id"]

    w = db.query(Watch).filter(Watch.id == gecmisli).one()
    kaynak = db.query(Source).filter(Source.product_id == w.product_id).one()
    _gecmis_ekle(db, w.product_id, kaynak.id, [(1000, 0)])

    y = istemci.get("/api/izlemeler/kivilcimlar", headers=b)
    veri = y.json()
    assert str(gecmisli) in veri
    assert str(gecmissiz) not in veri


def test_kivilcimlar_baskasinin_izlemesi_donmuyor(istemci, db):
    """Kabul ölçütü: başkasının izlemesi asla dönmüyor."""
    a = kayit_ol(istemci, eposta="a@ornek.com")
    c = kayit_ol(istemci, eposta="c@ornek.com")

    izleme_a = istemci.post("/api/izlemeler", headers=a,
                           json={"url": "https://magaza.com/a"}).json()["id"]
    izleme_c = istemci.post("/api/izlemeler", headers=c,
                           json={"url": "https://magaza.com/c"}).json()["id"]

    for izleme_id in (izleme_a, izleme_c):
        w = db.query(Watch).filter(Watch.id == izleme_id).one()
        kaynak = db.query(Source).filter(Source.product_id == w.product_id).one()
        _gecmis_ekle(db, w.product_id, kaynak.id, [(1000, 0)])

    y = istemci.get("/api/izlemeler/kivilcimlar", headers=c)
    veri = y.json()
    assert str(izleme_c) in veri
    assert str(izleme_a) not in veri


def test_kivilcimlar_gun_araligi_disinda_422(istemci):
    """Kabul ölçütü: `gun` 7-365 dışında 422."""
    b = kayit_ol(istemci)
    assert istemci.get("/api/izlemeler/kivilcimlar?gun=6",
                       headers=b).status_code == 422
    assert istemci.get("/api/izlemeler/kivilcimlar?gun=366",
                       headers=b).status_code == 422
    assert istemci.get("/api/izlemeler/kivilcimlar?gun=7",
                       headers=b).status_code == 200
    assert istemci.get("/api/izlemeler/kivilcimlar?gun=365",
                       headers=b).status_code == 200


def test_kivilcimlar_gun_basina_en_dusuk_fiyati_verir(istemci, db):
    """Değerler gün başına EN DÜŞÜK okuma, eskiden yeniye sıralı."""
    b = kayit_ol(istemci)
    izleme_id = istemci.post("/api/izlemeler", headers=b,
                            json={"url": "https://magaza.com/a"}).json()["id"]
    w = db.query(Watch).filter(Watch.id == izleme_id).one()
    kaynak = db.query(Source).filter(Source.product_id == w.product_id).one()
    # Aynı güne (2 gün önce) iki okuma: düşük olan kazanmalı.
    _gecmis_ekle(db, w.product_id, kaynak.id,
                [(1200, 2), (1000, 2), (900, 1), (800, 0)])

    y = istemci.get("/api/izlemeler/kivilcimlar", headers=b)
    assert y.json()[str(izleme_id)] == [1000.0, 900.0, 800.0]


# ─────────────────── izleyen sayacı ───────────────────

def test_sayac_negatife_dusmez(istemci, db):
    """Sayaç DB'de tek UPDATE ile değişiyor; taban kontrolü de SQL'de olmalı."""
    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    urun = db.query(Product).one()
    urun.izleyen_sayisi = 0            # tutarsız veri: elle bozuyoruz
    db.commit()

    istemci.delete(f"/api/izlemeler/{i}", headers=b)
    db.expire_all()
    assert db.query(Product).one().izleyen_sayisi == 0


def test_sayac_null_iken_de_artar(istemci, db):
    """Eski satırlarda `izleyen_sayisi` NULL olabilir (sütun nullable).
    SQL'de NULL + 1 = NULL — CASE olmazsa sayaç sessizce kaybolur."""
    b = kayit_ol(istemci)
    istemci.post("/api/izlemeler", headers=b, json={"url": "https://magaza.com/a"})
    urun = db.query(Product).one()
    urun.izleyen_sayisi = None
    db.commit()

    c = kayit_ol(istemci, "c@ornek.com")
    istemci.post("/api/izlemeler", headers=c, json={"url": "https://magaza.com/a"})
    db.expire_all()
    assert db.query(Product).one().izleyen_sayisi == 1


# ─────────────────── ölçümler gerçekten yayınlanıyor mu ───────────────────

def test_api_metrics_kendi_trafigini_bildirir(istemci):
    """`/metrics` ucunun ÇALIŞMASI yetmez, İÇİ DOLU olmalı.

    Bu test bir mimari hatayı kilitliyor: tarama sayaçları AYRI süreçte
    (`tarayici`) artıyor ve API'nin kayıt defterinde asla görünmüyor.
    Bir dönem `/metrics` yalnızca `python_*` varsayılanlarını döndürüyordu —
    uç ayakta, pano boş. API kendi ölçebildiği şeyi ölçmeli.
    """
    b = kayit_ol(istemci)
    istemci.get("/api/izlemeler", headers=b)

    y = istemci.get("/metrics")
    assert "keepmoney_http_istek_toplam" in y.text
    assert 'rota="/api/izlemeler"' in y.text


def test_olcum_etiketi_ham_yol_degil_rota_sablonu(istemci):
    """Kardinalite patlaması koruması: ham yol etiketlenirse her izleme
    kimliği yeni bir zaman serisi doğurur ve Prometheus şişer."""
    b = kayit_ol(istemci)
    for n in range(3):
        i = istemci.post("/api/izlemeler", headers=b,
                         json={"url": f"https://magaza.com/u{n}"}).json()["id"]
        istemci.get(f"/api/izlemeler/{i}", headers=b)

    y = istemci.get("/metrics")
    assert 'rota="/api/izlemeler/{izleme_id}"' in y.text
    for i in (1, 2, 3):
        assert f'rota="/api/izlemeler/{i}"' not in y.text


def test_eslesmeyen_yol_olculmez(istemci):
    """404 üreten rastgele URL'ler etiket üretmemeli — yoksa bir tarayıcı
    tek başına ölçüm deposunu doldurabilir."""
    istemci.get("/boyle-bir-yol-yok-12345")
    y = istemci.get("/metrics")
    assert "boyle-bir-yol-yok" not in y.text


def test_metrics_ucu_kendini_saymaz(istemci):
    istemci.get("/metrics")
    y = istemci.get("/metrics")
    assert 'rota="/metrics"' not in y.text


# ─────────────────── yapılandırma tuzakları ───────────────────

def test_ozel_cerez_adiyla_oturum_calisir(oturum_fabrikasi, monkeypatch):
    """`KEEPMONEY_OTURUM_CEREZI` değiştirilince oturum BOZULUYORDU: çerezi
    kuran taraf ayarı okuyor, okuyan taraf adı sabit yazıyordu. Giriş 200
    dönüyor, çerez kuruluyor, sonraki her istek 401 oluyordu."""
    from keepmoney.ayarlar import ayarlar

    monkeypatch.setenv("KEEPMONEY_OTURUM_CEREZI", "km_ozel")
    ayarlar.cache_clear()
    try:
        app = uygulama_olustur()

        def test_db():
            d = oturum_fabrikasi()
            try:
                yield d
            finally:
                d.close()

        app.dependency_overrides[get_db] = test_db
        with TestClient(app) as c:
            c.post("/api/auth/kayit",
                   json={"eposta": "a@ornek.com", "parola": "parola1234"})
            g = c.post("/api/auth/giris",
                       json={"eposta": "a@ornek.com", "parola": "parola1234"})
            assert g.status_code == 200
            assert "km_ozel" in c.cookies
            assert c.get("/api/auth/ben").status_code == 200
    finally:
        ayarlar.cache_clear()


def test_jwt_algoritmasi_none_olamaz(monkeypatch):
    """`alg=none` JWT'nin klasik açığı: imza doğrulaması tümden kapanır ve
    herkes istediği kullanıcı adına token üretir. Ayar açılışta reddetmeli."""
    import pydantic

    from keepmoney.ayarlar import Ayarlar

    monkeypatch.setenv("KEEPMONEY_JWT_ALGORITMA", "none")
    with pytest.raises(pydantic.ValidationError):
        Ayarlar()


def test_gecerli_hmac_algoritmalari_kabul_edilir(monkeypatch):
    from keepmoney.ayarlar import Ayarlar
    monkeypatch.setenv("KEEPMONEY_JWT_ALGORITMA", "HS512")
    assert Ayarlar().jwt_algoritma == "HS512"


# ─────────────────── set kısmi güncelleme ───────────────────

def test_set_sadece_butce_guncellenebilir(istemci):
    """PATCH ucu oluşturma şemasını yeniden kullanıyordu; `ad` zorunlu
    olduğu için "sadece bütçeyi değiştir" isteği 422 dönüyordu."""
    b = kayit_ol(istemci)
    i = istemci.post("/api/setler", headers=b,
                     json={"ad": "PC Toplama", "hedef_butce": 50000}).json()["id"]

    y = istemci.patch(f"/api/setler/{i}", headers=b, json={"hedef_butce": 42000})
    assert y.status_code == 200
    assert y.json()["hedef_butce"] == 42000
    assert y.json()["ad"] == "PC Toplama"      # dokunulmadı


def test_set_butcesi_temizlenebilir(istemci):
    b = kayit_ol(istemci)
    i = istemci.post("/api/setler", headers=b,
                     json={"ad": "Kombin", "hedef_butce": 5000}).json()["id"]
    y = istemci.patch(f"/api/setler/{i}", headers=b, json={"hedef_butce": None})
    assert y.json()["hedef_butce"] is None
    assert y.json()["hedefte"] is False


def test_set_bilinmeyen_alan_reddedilir(istemci, db):
    """İzleme servisindeki toplu atama düzeltmesinin ikizi — kural iki
    serviste kopyalanmıştı, biri düzeltilip diğeri geride kalmıştı."""
    from keepmoney.models import User
    from keepmoney.servisler import setler as svc

    b = kayit_ol(istemci)
    i = istemci.post("/api/setler", headers=b, json={"ad": "S"}).json()["id"]
    k = db.query(User).one()

    with pytest.raises(svc.SetHatasi):
        svc.guncelle(db, k, i, user_id=999)


def test_set_listesi_n_arti_bir_yapmaz(istemci, db):
    from sqlalchemy import event

    b = kayit_ol(istemci)
    for n in range(4):
        s = istemci.post("/api/setler", headers=b,
                         json={"ad": f"S{n}"}).json()["id"]
        for m in range(3):
            istemci.post("/api/izlemeler", headers=b, json={
                "url": f"https://magaza.com/s{n}-u{m}", "set_idler": [s]})

    sorgular: list[str] = []
    motor = db.get_bind()

    def yakala(conn, cursor, ifade, *a, **kw):
        if ifade.lstrip().upper().startswith("SELECT"):
            sorgular.append(ifade)

    event.listen(motor, "before_cursor_execute", yakala)
    try:
        y = istemci.get("/api/setler", headers=b)
    finally:
        event.remove(motor, "before_cursor_execute", yakala)

    assert len(y.json()) == 4
    # kullanıcı + setler + üyeler + ürünler ≈ 4; N+1 olsaydı 17+ olurdu
    assert len(sorgular) <= 6, f"{len(sorgular)} SELECT"


def test_urun_detayi_gecmisi_tek_kez_okur(istemci, db):
    """`gunluk_seri` ve `baglam` ayrı ayrı tüm fiyat geçmişini çekiyordu."""
    from datetime import timedelta

    from keepmoney.servisler import urun as urun_svc
    from keepmoney.zaman import utc_simdi

    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    p = db.query(Product).one()
    kaynak = db.query(Source).one()
    p.guncel_fiyat = 1000
    for gun in range(10):
        db.add(PriceReading(product_id=p.id, source_id=kaynak.id, fiyat=1000,
                            ts=utc_simdi() - timedelta(days=gun)))
    db.commit()

    cagrilar = []
    gercek = urun_svc.okumalar

    def sayan(dbo, urun_id):
        cagrilar.append(urun_id)
        return gercek(dbo, urun_id)

    urun_svc.okumalar = sayan
    try:
        y = istemci.get(f"/api/izlemeler/{i}", headers=b)
    finally:
        urun_svc.okumalar = gercek

    assert y.status_code == 200
    assert len(cagrilar) == 1, f"{len(cagrilar)} kez okundu"


# ─────────────────── yabancı anahtar silme kuralları ───────────────────

def test_uyarisi_olan_izleme_silinebilir(istemci, db):
    """GERÇEK HATA: kural yokken Postgres'te "takipten çıkar" düğmesi, o
    üründen bir kez bile uyarı almış her kullanıcı için yabancı anahtar
    ihlaliyle 500 dönüyordu. SQLite yabancı anahtarları zorlamadığı için
    testler görmüyordu (artık zorluyor — bkz. db.py)."""
    from keepmoney.models import User

    b = kayit_ol(istemci)
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    k = db.query(User).one()
    db.add(Alert(user_id=k.id, watch_id=i, tur="HEDEF", baslik="b", mesaj="m"))
    db.commit()

    assert istemci.delete(f"/api/izlemeler/{i}", headers=b).status_code == 204

    # Uyarı SİLİNMEZ — olmuş bir olayın kaydıdır; yalnızca bağı kopar.
    db.expire_all()
    uyari = db.query(Alert).one()
    assert uyari.watch_id is None
    assert uyari.baslik == "b"


def test_hesap_silinince_uyarilari_da_gider(istemci, db):
    from keepmoney.models import User
    from keepmoney.servisler import kullanici as k_svc

    b = kayit_ol(istemci)
    istemci.post("/api/izlemeler", headers=b, json={"url": "https://magaza.com/a"})
    k = db.query(User).one()
    db.add(Alert(user_id=k.id, tur="DIP", baslik="b", mesaj="m"))
    db.commit()

    k_svc.hesabi_sil(db, k, "parola1234")
    db.expire_all()
    assert db.query(User).count() == 0
    assert db.query(Alert).count() == 0
    assert db.query(Watch).count() == 0
    # Küresel geçmiş KİŞİSEL VERİ DEĞİL — kalır.
    assert db.query(Product).count() == 1


# ─────────────────── parola sıfırlama ───────────────────

@pytest.fixture
def sahte_posta(monkeypatch):
    """Gönderilen e-postaları yakalar — gerçek SMTP yok."""
    from keepmoney import eposta

    kutu: list[tuple[str, str, str]] = []

    class Sahte:
        def gonder(self, alici, konu, govde):
            kutu.append((alici, konu, govde))
            return True

    monkeypatch.setattr(eposta, "postaci", lambda: Sahte())
    # Rota modülü `postaci`yi kendi ad alanına almış
    from keepmoney.api.rotalar import auth as auth_rota
    monkeypatch.setattr(auth_rota, "postaci", lambda: Sahte())
    return kutu


def _tokeni_al(kutu, yol: str) -> str:
    """Kutudaki SON e-postadan token çıkarır.

    Yol adıyla arıyoruz: kayıt sırasında doğrulama e-postası da gidiyor ve
    ikisi de `?token=` içeriyor — ilk eşleşmeyi almak yanlış token verir.
    """
    for _, _, govde in reversed(kutu):
        if f"/{yol}?token=" in govde:
            return govde.split(f"/{yol}?token=")[1].split()[0]
    raise AssertionError(f"kutuda /{yol} bağlantısı yok: {kutu}")


def test_parola_sifirlama_uctan_uca(istemci, sahte_posta):
    """Bu akış HİÇ YOKTU: parolasını unutan kullanıcı hesabını tamamen
    kaybediyordu. Gerçek bir üründe pazarlık konusu değil."""
    kayit_ol(istemci, "a@ornek.com", "eskiparola123")

    y = istemci.post("/api/auth/parola/sifirlama-iste",
                     json={"eposta": "a@ornek.com"})
    assert y.status_code == 202

    token = _tokeni_al(sahte_posta, "parola-sifirla")
    y = istemci.post("/api/auth/parola/sifirla",
                     json={"token": token, "parola": "yeniparola456"})
    assert y.status_code == 200

    # Yeni parola çalışır, eskisi çalışmaz
    assert istemci.post("/api/auth/giris", json={
        "eposta": "a@ornek.com", "parola": "yeniparola456"}).status_code == 200
    assert istemci.post("/api/auth/giris", json={
        "eposta": "a@ornek.com", "parola": "eskiparola123"}).status_code == 401


def test_sifirlama_tokeni_tek_kullanimlik(istemci, sahte_posta):
    kayit_ol(istemci, "a@ornek.com")
    istemci.post("/api/auth/parola/sifirlama-iste", json={"eposta": "a@ornek.com"})
    token = _tokeni_al(sahte_posta, "parola-sifirla")

    assert istemci.post("/api/auth/parola/sifirla",
                        json={"token": token, "parola": "yeni12345"}).status_code == 200
    # İkinci kullanım reddedilmeli
    assert istemci.post("/api/auth/parola/sifirla",
                        json={"token": token, "parola": "baska12345"}).status_code == 400


def test_suresi_dolmus_sifirlama_tokeni_reddedilir(istemci, sahte_posta, db):
    from datetime import timedelta

    from keepmoney.models import User
    from keepmoney.zaman import utc_simdi

    kayit_ol(istemci, "a@ornek.com")
    istemci.post("/api/auth/parola/sifirlama-iste", json={"eposta": "a@ornek.com"})
    token = _tokeni_al(sahte_posta, "parola-sifirla")

    k = db.query(User).one()
    k.parola_sifirlama_biter = utc_simdi() - timedelta(minutes=1)
    db.commit()

    assert istemci.post("/api/auth/parola/sifirla",
                        json={"token": token, "parola": "yeni12345"}).status_code == 400


def test_olmayan_eposta_ayni_cevabi_verir(istemci, sahte_posta):
    """HESAP SAYIMI SIZMASIN: farklı cevap, hangi adreslerin kayıtlı
    olduğunu söyler ve o liste doğrudan kimlik avı için kullanılır."""
    kayit_ol(istemci, "var@ornek.com")
    sahte_posta.clear()

    a = istemci.post("/api/auth/parola/sifirlama-iste",
                     json={"eposta": "var@ornek.com"})
    b = istemci.post("/api/auth/parola/sifirlama-iste",
                     json={"eposta": "yok@ornek.com"})

    assert a.status_code == b.status_code == 202
    assert a.json() == b.json()
    assert len(sahte_posta) == 1        # yalnızca gerçek adrese gitti


def test_token_veritabaninda_ham_saklanmaz(istemci, sahte_posta, db):
    """Sıfırlama token'ı paroladan farksız yetki taşır. Ham saklanırsa bir
    veritabanı sızıntısı doğrudan hesap devralmadır."""
    from keepmoney.models import User

    kayit_ol(istemci, "a@ornek.com")
    istemci.post("/api/auth/parola/sifirlama-iste", json={"eposta": "a@ornek.com"})
    token = _tokeni_al(sahte_posta, "parola-sifirla")

    db.expire_all()
    k = db.query(User).one()
    assert k.parola_sifirlama_hash != token
    assert len(k.parola_sifirlama_hash) == 64      # sha256 hex


def test_sifirlama_hiz_siniri(istemci, sahte_posta):
    """Sınırsız bırakılırsa birinin posta kutusuna bombardıman yapılabilir."""
    from keepmoney.ayarlar import ayarlar as _ayarlar

    SIFIRLAMA_LIMIT = _ayarlar().sifirlama_limiti

    kayit_ol(istemci, "a@ornek.com")
    for _ in range(SIFIRLAMA_LIMIT):
        istemci.post("/api/auth/parola/sifirlama-iste", json={"eposta": "a@ornek.com"})
    y = istemci.post("/api/auth/parola/sifirlama-iste", json={"eposta": "a@ornek.com"})
    assert y.status_code == 429


def test_sifirlama_sonrasi_oturum_acilir(istemci, sahte_posta):
    kayit_ol(istemci, "a@ornek.com")
    istemci.cookies.clear()
    istemci.post("/api/auth/parola/sifirlama-iste", json={"eposta": "a@ornek.com"})
    token = _tokeni_al(sahte_posta, "parola-sifirla")
    istemci.post("/api/auth/parola/sifirla",
                 json={"token": token, "parola": "yeni12345"})
    assert istemci.get("/api/auth/ben").status_code == 200


# ─────────────────── e-posta doğrulama ───────────────────

def test_kayitta_dogrulama_baglantisi_gider(istemci, sahte_posta):
    kayit_ol(istemci, "a@ornek.com")
    assert any("doğrula" in konu for _, konu, _ in sahte_posta)


def test_eposta_dogrulanir(istemci, sahte_posta):
    b = kayit_ol(istemci, "a@ornek.com")
    assert istemci.get("/api/auth/ben", headers=b).json()["eposta_dogrulandi"] is False

    token = _tokeni_al(sahte_posta, "eposta-dogrula")
    y = istemci.post("/api/auth/eposta/dogrula", json={"token": token})
    assert y.status_code == 200
    assert y.json()["eposta_dogrulandi"] is True


def test_gecersiz_dogrulama_tokeni_reddedilir(istemci):
    y = istemci.post("/api/auth/eposta/dogrula", json={"token": "x" * 40})
    assert y.status_code == 400


def test_dogrulama_yeniden_gonderilebilir(istemci, sahte_posta):
    b = kayit_ol(istemci, "a@ornek.com")
    sahte_posta.clear()
    y = istemci.post("/api/auth/eposta/dogrulama-gonder", headers=b)
    assert y.status_code == 202
    assert len(sahte_posta) == 1


def test_parola_sifirlama_epostayi_da_dogrular(istemci, sahte_posta):
    """Kullanıcı o kutuya erişebildiğini kanıtladı — ayrıca doğrulatmak
    gereksiz sürtünme olurdu."""
    b = kayit_ol(istemci, "a@ornek.com")
    istemci.post("/api/auth/parola/sifirlama-iste", json={"eposta": "a@ornek.com"})
    token = _tokeni_al(sahte_posta, "parola-sifirla")
    y = istemci.post("/api/auth/parola/sifirla",
                     json={"token": token, "parola": "yeni12345"})
    assert y.json()["eposta_dogrulandi"] is True
    _ = b


# ─────────────────── hesap silme (KVKK) ───────────────────

def test_hesap_silinir(istemci, db):
    from keepmoney.models import User

    b = kayit_ol(istemci, "a@ornek.com", "parola1234")
    istemci.post("/api/izlemeler", headers=b, json={"url": "https://magaza.com/a"})

    y = istemci.request("DELETE", "/api/auth/hesap", headers=b,
                        json={"parola": "parola1234"})
    assert y.status_code == 204
    assert db.query(User).count() == 0
    assert db.query(Watch).count() == 0


def test_hesap_silmede_parola_dogrulanir(istemci, db):
    """Oturumu çalınmış birinin hesabı silmesini zorlaştırır."""
    from keepmoney.models import User

    b = kayit_ol(istemci, "a@ornek.com", "parola1234")
    y = istemci.request("DELETE", "/api/auth/hesap", headers=b,
                        json={"parola": "yanlisparola"})
    assert y.status_code == 403
    assert db.query(User).count() == 1


def test_hesap_silinince_kuresel_gecmis_kalir(istemci, db):
    """Fiyat geçmişi KİŞİSEL VERİ DEĞİL — bir ekran kartının dünkü fiyatı
    kimseye ait değildir ve diğer kullanıcıların hafızasıdır."""
    b = kayit_ol(istemci, "a@ornek.com", "parola1234")
    istemci.post("/api/izlemeler", headers=b, json={"url": "https://magaza.com/a"})
    urun = db.query(Product).one()
    kaynak = db.query(Source).one()
    db.add(PriceReading(product_id=urun.id, source_id=kaynak.id, fiyat=1000))
    db.commit()

    istemci.request("DELETE", "/api/auth/hesap", headers=b,
                    json={"parola": "parola1234"})
    db.expire_all()
    assert db.query(PriceReading).count() == 1
    assert db.query(Product).one().izleyen_sayisi == 0


def test_hesap_silmek_kimlik_ister(istemci):
    y = istemci.request("DELETE", "/api/auth/hesap", json={"parola": "x"})
    assert y.status_code == 401


# ─────────────────── bildirim sayfalama ───────────────────

def test_uyarilar_sayfalanir(istemci, db):
    """Liste sabit 50'de kesiliyordu ve daha eskisine ulaşmanın yolu yoktu."""
    from keepmoney.models import User

    b = kayit_ol(istemci)
    k = db.query(User).one()
    for n in range(120):
        db.add(Alert(user_id=k.id, tur="HEDEF", baslik=f"u{n:03d}", mesaj="m"))
    db.commit()

    ilk = istemci.get("/api/uyarilar?limit=50&offset=0", headers=b).json()
    ikinci = istemci.get("/api/uyarilar?limit=50&offset=50", headers=b).json()
    ucuncu = istemci.get("/api/uyarilar?limit=50&offset=100", headers=b).json()

    assert len(ilk) == 50
    assert len(ikinci) == 50
    assert len(ucuncu) == 20            # kalan
    # Sayfalar ÇAKIŞMAMALI
    kimlikler = [u["id"] for u in ilk + ikinci + ucuncu]
    assert len(set(kimlikler)) == 120


def test_uyari_limiti_ust_sinirla_kisitli(istemci):
    """İstemci `limit=100000` diyerek tabloyu belleğe çekememeli."""
    b = kayit_ol(istemci)
    assert istemci.get("/api/uyarilar?limit=100000", headers=b).status_code == 422
    assert istemci.get("/api/uyarilar?limit=0", headers=b).status_code == 422
    assert istemci.get("/api/uyarilar?offset=-5", headers=b).status_code == 422


def test_uyari_sirasi_kararli(istemci, db):
    """Aynı saniyede üretilen bildirimlerde `created_at` tek başına kararlı
    sıralama vermez; sayfalar arasında kayıt tekrarlanır ya da atlanır."""
    from keepmoney.models import User
    from keepmoney.zaman import utc_simdi

    b = kayit_ol(istemci)
    k = db.query(User).one()
    ayni_an = utc_simdi()
    for n in range(10):
        db.add(Alert(user_id=k.id, tur="DIP", baslik=f"a{n}", mesaj="m",
                     created_at=ayni_an))
    db.commit()

    a = [u["id"] for u in istemci.get("/api/uyarilar?limit=5&offset=0",
                                      headers=b).json()]
    c = [u["id"] for u in istemci.get("/api/uyarilar?limit=5&offset=5",
                                      headers=b).json()]
    assert not set(a) & set(c), "sayfalar çakışıyor — sıralama kararsız"


# ─────────────────── istek kimliği ve hata yakalama ───────────────────

def test_istek_kimligi_yanitta_doner(istemci):
    y = istemci.get("/saglik")
    assert y.headers.get("X-Request-ID")


def test_gelen_istek_kimligi_korunur(istemci):
    """Ters vekil ya da çağıran servis kimlik ürettiyse zincir kopmamalı."""
    y = istemci.get("/saglik", headers={"X-Request-ID": "yukaridan-gelen"})
    assert y.headers["X-Request-ID"] == "yukaridan-gelen"


def test_beklenmeyen_hata_iz_kaydi_sizdirmaz():
    """Veritabanı erişilemezken kullanıcı YIĞIN İZİ değil, istek kimliği görür.

    Gerçek bir üretim arızasını taklit ediyor: bağlantı kurulamıyor. Eskiden
    böyle bir hata Starlette'in varsayılan işleyicisine düşüyor, gövdesi düz
    metin oluyor ve iz kaydı yapılandırılmamış biçimde stderr'e gidiyordu.
    """
    app = uygulama_olustur()

    def patlayan_db():
        raise RuntimeError("gizli iç ayrıntı: parola=hunter2 ile bağlanılamadı")

    app.dependency_overrides[get_db] = patlayan_db
    with TestClient(app, raise_server_exceptions=False) as c:
        y = c.get("/api/izlemeler", headers={"Authorization": "Bearer x"})

    assert y.status_code == 500
    assert "hunter2" not in y.text          # sır sızmıyor
    assert "Traceback" not in y.text        # iz kaydı sızmıyor
    govde = y.json()
    assert govde["istek_kimligi"]
    assert y.headers.get("X-Request-ID") == govde["istek_kimligi"]


def test_spa_yakalayicisi_api_uclarini_golgelemiyor(istemci):
    """SPA geri düşüşü EN SONDA bağlanır; ondan sonra eklenen her rota ölü
    kalır. Bu testin varlığı, sıranın kazara bozulmasını yakalar."""
    b = kayit_ol(istemci)
    assert istemci.get("/api/izlemeler", headers=b).status_code == 200
    assert istemci.get("/api/uyarilar", headers=b).status_code == 200
    y = istemci.get("/api/olmayan-uc")
    assert y.status_code == 404
    assert "application/json" in y.headers.get("content-type", "")


# ── Çoklu kaynak: öneri + kullanıcı onaylı ekleme ────────────────
# Bu blokta test edilen asıl şey, sistemin YAPMADIĞI şey: arama sonucu
# hiçbir bağ kurmaz. Otomatik eşleştirme, benzer adlı iki ürünün fiyatını
# karıştırıp grafiğe işleyen ve geri alınamayan bir hata üretirdi.

def _izleme_kur(istemci, url="https://magaza.com/urun-a") -> tuple[dict, int]:
    basliklar = kayit_ol(istemci)
    y = istemci.post("/api/izlemeler", json={"url": url}, headers=basliklar)
    return basliklar, y.json()["id"]


def _ad_okundu(db) -> None:
    """İlk taramanın ürün adını okumuş olduğunu taklit eder.

    Link eklendiği anda `Product.ad` link kimliğidir ("B0BSLHZKB6") ve
    `ad_gecici` doğrudur. Arama bu adla yapılamaz — testlerde `toplayici.ara`
    taklit edildiği için bu koşul GÖRÜNMÜYORDU: 595 test yeşilken gerçek
    kurulumda arama her zaman boş dönüyordu.
    """
    from keepmoney.models import Product

    db.query(Product).update({Product.ad_gecici: False})
    db.commit()


def test_kaynak_onerileri_hicbir_sey_baglamaz(istemci, db, monkeypatch):
    """Arama SONUCU bir öneridir; veritabanına dokunmaz."""
    from keepmoney import toplayici
    monkeypatch.setattr(
        toplayici, "ara",
        lambda cekici, sorgu, limit=3: [
            toplayici.Oneri(ad="Asus RTX 5070 Ti", url="https://akakce.com/x-fiyati,1.html")])

    basliklar, izleme_id = _izleme_kur(istemci)
    _ad_okundu(db)
    once = db.query(Source).count()

    y = istemci.get(f"/api/izlemeler/{izleme_id}/kaynak-onerileri",
                    headers=basliklar)
    assert y.status_code == 200
    assert y.json() == [{"ad": "Asus RTX 5070 Ti",
                         "url": "https://akakce.com/x-fiyati,1.html"}]
    assert db.query(Source).count() == once      # HİÇBİR ŞEY eklenmedi


def test_kaynak_onerileri_baskasinin_izlemesine_kapali(istemci, monkeypatch):
    from keepmoney import toplayici
    monkeypatch.setattr(toplayici, "ara", lambda *a, **k: [])

    _, izleme_id = _izleme_kur(istemci)
    baskasi = kayit_ol(istemci, "b@ornek.com")
    y = istemci.get(f"/api/izlemeler/{izleme_id}/kaynak-onerileri",
                    headers=baskasi)
    assert y.status_code == 404


def test_kullanici_onayiyla_kaynak_eklenir(istemci, db):
    basliklar, izleme_id = _izleme_kur(istemci)
    y = istemci.post(f"/api/izlemeler/{izleme_id}/kaynaklar",
                     json={"url": "https://www.akakce.com/x-fiyati,1.html"},
                     headers=basliklar)
    assert y.status_code == 201

    detay = istemci.get(f"/api/izlemeler/{izleme_id}", headers=basliklar).json()
    hostlar = {k["host"] for k in detay["urun"]["kaynaklar"]}
    assert hostlar == {"magaza.com", "akakce.com"}


def test_eklenen_toplayici_kaynak_isaretlenir(istemci, db):
    basliklar, izleme_id = _izleme_kur(istemci)
    istemci.post(f"/api/izlemeler/{izleme_id}/kaynaklar",
                 json={"url": "https://www.akakce.com/x-fiyati,1.html"},
                 headers=basliklar)
    kaynak = db.query(Source).filter(Source.host == "akakce.com").one()
    assert bool(kaynak.toplayici) is True


def test_ayni_kaynak_iki_kez_eklenince_cogalmaz(istemci, db):
    basliklar, izleme_id = _izleme_kur(istemci)
    url = "https://www.akakce.com/x-fiyati,1.html"
    for _ in range(2):
        istemci.post(f"/api/izlemeler/{izleme_id}/kaynaklar",
                     json={"url": url}, headers=basliklar)
    assert db.query(Source).filter(Source.host == "akakce.com").count() == 1


def test_baskasinin_izlemesine_kaynak_eklenemez(istemci):
    _, izleme_id = _izleme_kur(istemci)
    baskasi = kayit_ol(istemci, "c@ornek.com")
    y = istemci.post(f"/api/izlemeler/{izleme_id}/kaynaklar",
                     json={"url": "https://www.akakce.com/x-fiyati,1.html"},
                     headers=baskasi)
    assert y.status_code == 400


def test_baskasinin_izledigi_urune_ait_adres_reddedilir(istemci):
    """İki ürünü birleştirmek fiyat geçmişlerini karıştırır ve geri alınamaz.
    Başkasının izlediği bir ürünün adresi sessizce taşınmamalı."""
    basliklar_a = kayit_ol(istemci, "d@ornek.com")
    paylasilan = "https://magaza.com/paylasilan"
    istemci.post("/api/izlemeler", json={"url": paylasilan}, headers=basliklar_a)

    basliklar_b = kayit_ol(istemci, "e@ornek.com")
    y = istemci.post("/api/izlemeler", json={"url": "https://magaza.com/baska"},
                     headers=basliklar_b)
    izleme_b = y.json()["id"]

    y = istemci.post(f"/api/izlemeler/{izleme_b}/kaynaklar",
                     json={"url": paylasilan}, headers=basliklar_b)
    assert y.status_code == 400
    assert "başka bir ürüne bağlı" in y.json()["detail"]


def test_kaynak_ekleme_ssrf_kapisindan_gecer(istemci):
    basliklar, izleme_id = _izleme_kur(istemci)
    y = istemci.post(f"/api/izlemeler/{izleme_id}/kaynaklar",
                     json={"url": "http://169.254.169.254/latest/meta-data/"},
                     headers=basliklar)
    assert y.status_code == 400


def test_arama_mesgulse_503_ve_retry_after(istemci, db, monkeypatch):
    """Geçici doluluk KALICI hata gibi görünmemeli: 503 + Retry-After.

    Kuyruğa almak yerine hızlı reddediyoruz — bekleyen istek FastAPI'nin iş
    parçacığı havuzunu tutar ve yeterince birikirse TÜM API durur.
    """
    from keepmoney import toplayici

    def mesgul(*a, **k):
        raise toplayici.MesgulHata("Şu an çok fazla arama yapılıyor.")

    monkeypatch.setattr(toplayici, "ara", mesgul)

    basliklar, izleme_id = _izleme_kur(istemci)
    _ad_okundu(db)
    y = istemci.get(f"/api/izlemeler/{izleme_id}/kaynak-onerileri",
                    headers=basliklar)
    assert y.status_code == 503
    assert y.headers["Retry-After"] == "5"


def test_ad_okunmadan_arama_sebebiyle_reddedilir(istemci, db, monkeypatch):
    """Boş liste yerine SEBEP.

    Gerçek kurulumda yakalandı: link eklenir eklenmez "başka mağazalarda ara"
    denince akakçe'de "B0BSLHZKB6" aranıyordu — ürün adı henüz okunmamıştı ve
    sonuç HER ZAMAN boştu. Arayüz bunu "eşleşme bulunamadı" diye gösteriyordu,
    yani kullanıcı özelliğin bozuk olduğunu sanıyordu. Testlerde
    `toplayici.ara` taklit edildiği için koşul hiç görünmemişti.
    """
    from keepmoney import toplayici

    def cagrilmamali(*a, **k):
        pytest.fail("ad okunmadan toplayıcıya istek GİTMEMELİ")

    monkeypatch.setattr(toplayici, "ara", cagrilmamali)

    basliklar, izleme_id = _izleme_kur(istemci)      # ad_gecici = True
    y = istemci.get(f"/api/izlemeler/{izleme_id}/kaynak-onerileri",
                    headers=basliklar)
    assert y.status_code == 409
    assert "henüz okunmadı" in y.json()["detail"]


def test_toplayiciya_ulasilamazsa_503_doner(istemci, db, monkeypatch):
    """"Ulaşılamadı" ile "sonuç yok" ayrı cevaplar olmalı.

    Boş liste döndüğünde arayüz "bu ürün için eşleşme bulunamadı" diyordu;
    yani bir ağ hatası, ürünün hiçbir yerde satılmadığı gibi görünüyordu ve
    kullanıcı mağaza linkini elle eklemeyi denemiyordu. Gerçek bir denemede
    çekim katmanı 403 aldı, uç 200 + `[]` döndürdü.
    """
    from keepmoney import toplayici

    def erisilemedi(*a, **k):
        raise toplayici.ErisimHatasi("Toplayıcıya şu an ulaşılamıyor.")

    monkeypatch.setattr(toplayici, "ara", erisilemedi)

    basliklar, izleme_id = _izleme_kur(istemci)
    _ad_okundu(db)
    y = istemci.get(f"/api/izlemeler/{izleme_id}/kaynak-onerileri",
                    headers=basliklar)
    assert y.status_code == 503
    assert y.headers["Retry-After"] == "30"


def test_sonuc_yoksa_200_ve_bos_liste(istemci, db, monkeypatch):
    """Karşı test: gerçekten eşleşme yoksa 200 + [] doğru cevaptır."""
    from keepmoney import toplayici
    monkeypatch.setattr(toplayici, "ara", lambda *a, **k: [])

    basliklar, izleme_id = _izleme_kur(istemci)
    _ad_okundu(db)
    y = istemci.get(f"/api/izlemeler/{izleme_id}/kaynak-onerileri",
                    headers=basliklar)
    assert y.status_code == 200
    assert y.json() == []


# ─────────────── sete toplu ürün ekleme (kısmi başarı) ───────────────


def test_sete_toplu_urun_eklenir(istemci):
    """Setin İÇİNDEN çoklu seçimle ekleme — asıl kullanım biçimi.

    Eskiden ürün eklemek için her ürünün detay sayfasına tek tek gidip
    açılır listeden set seçmek gerekiyordu: 8 parçalık bir PC için 8 ayrı
    sayfa. Kullanıcı seti düşünürken "bu sete hangi ürünler girer" diye
    sorar, "bu ürün hangi sete gider" diye değil.
    """
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b, json={"ad": "PC"}).json()
    idler = [
        istemci.post("/api/izlemeler", headers=b,
                     json={"url": f"https://magaza.com/u{n}"}).json()["id"]
        for n in range(3)
    ]

    y = istemci.post(f"/api/setler/{s['id']}/uyeler", headers=b,
                     json={"izleme_idler": idler})

    assert y.status_code == 200
    assert sorted(y.json()["eklendi"]) == sorted(idler)
    assert y.json()["atlandi"] == []
    assert istemci.get(f"/api/setler/{s['id']}",
                       headers=b).json()["uye_sayisi"] == 3


def test_toplu_ekleme_kismi_basariya_izin_verir(istemci):
    """YA HEP YA HİÇ DEĞİL: geçerli olanlar eklenir, atlananlar SEBEBİYLE
    bildirilir. Aksi hâlde sekiz seçimden biri bayat diye sekizi birden
    kaybolurdu."""
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b, json={"ad": "PC"}).json()
    gecerli = istemci.post("/api/izlemeler", headers=b,
                           json={"url": "https://magaza.com/a"}).json()["id"]

    y = istemci.post(f"/api/setler/{s['id']}/uyeler", headers=b,
                     json={"izleme_idler": [gecerli, 999999]})

    assert y.status_code == 200
    assert y.json()["eklendi"] == [gecerli]
    assert y.json()["atlandi"] == [{"id": 999999, "sebep": "bulunamadi"}]


def test_zaten_uye_olan_hata_degil(istemci):
    """Sonuç aynı olduğu için sessizce atlanır ama SEBEBİ bildirilir."""
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b, json={"ad": "PC"}).json()
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    istemci.post(f"/api/setler/{s['id']}/uyeler", headers=b,
                 json={"izleme_idler": [i]})

    y = istemci.post(f"/api/setler/{s['id']}/uyeler", headers=b,
                     json={"izleme_idler": [i]})

    assert y.json()["eklendi"] == []
    assert y.json()["atlandi"] == [{"id": i, "sebep": "zaten_uye"}]
    assert istemci.get(f"/api/setler/{s['id']}",
                       headers=b).json()["uye_sayisi"] == 1


def test_baskasinin_izlemesi_sete_eklenemez(istemci):
    """Var olup olmadığını sızdırmamalı: başkasının kaydı da 'bulunamadi'."""
    a = kayit_ol(istemci, "a@ornek.com")
    c = kayit_ol(istemci, "c@ornek.com")
    s = istemci.post("/api/setler", headers=a, json={"ad": "PC"}).json()
    baskasinin = istemci.post("/api/izlemeler", headers=c,
                              json={"url": "https://magaza.com/x"}).json()["id"]

    y = istemci.post(f"/api/setler/{s['id']}/uyeler", headers=a,
                     json={"izleme_idler": [baskasinin]})

    assert y.json()["eklendi"] == []
    assert y.json()["atlandi"] == [{"id": baskasinin, "sebep": "bulunamadi"}]


def test_baskasinin_setine_toplu_ekleme_kapali(istemci):
    a = kayit_ol(istemci, "a@ornek.com")
    c = kayit_ol(istemci, "c@ornek.com")
    s = istemci.post("/api/setler", headers=a, json={"ad": "Gizli"}).json()
    i = istemci.post("/api/izlemeler", headers=c,
                     json={"url": "https://magaza.com/x"}).json()["id"]

    y = istemci.post(f"/api/setler/{s['id']}/uyeler", headers=c,
                     json={"izleme_idler": [i]})
    assert y.status_code == 404


def test_setten_cikarma_izlemeyi_silmez(istemci, db):
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b, json={"ad": "PC"}).json()
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]
    istemci.post(f"/api/setler/{s['id']}/uyeler", headers=b,
                 json={"izleme_idler": [i]})

    y = istemci.delete(f"/api/setler/{s['id']}/uyeler/{i}", headers=b)

    assert y.status_code == 204
    assert db.query(Watch).count() == 1          # izleme DURUYOR
    assert istemci.get(f"/api/setler/{s['id']}",
                       headers=b).json()["uye_sayisi"] == 0


def test_sette_olmayan_urunu_cikarmak_404(istemci):
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b, json={"ad": "PC"}).json()
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]

    assert istemci.delete(f"/api/setler/{s['id']}/uyeler/{i}",
                          headers=b).status_code == 404


def test_ayni_urun_iki_sette_olabilir(istemci):
    """Asıl kazanım: tek `set_id` sütunu bunu imkânsız kılıyordu."""
    b = kayit_ol(istemci)
    s1 = istemci.post("/api/setler", headers=b, json={"ad": "PC"}).json()
    s2 = istemci.post("/api/setler", headers=b, json={"ad": "Kara Cuma"}).json()
    i = istemci.post("/api/izlemeler", headers=b,
                     json={"url": "https://magaza.com/a"}).json()["id"]

    istemci.post(f"/api/setler/{s1['id']}/uyeler", headers=b,
                 json={"izleme_idler": [i]})
    istemci.post(f"/api/setler/{s2['id']}/uyeler", headers=b,
                 json={"izleme_idler": [i]})

    detay = istemci.get(f"/api/izlemeler/{i}", headers=b).json()
    assert sorted(detay["set_idler"]) == sorted([s1["id"], s2["id"]])


def test_bos_uyelik_listesi_reddedilir(istemci):
    """Anlamsız istek şemada durur — sunucuya iş yaptırmadan."""
    b = kayit_ol(istemci)
    s = istemci.post("/api/setler", headers=b, json={"ad": "PC"}).json()
    y = istemci.post(f"/api/setler/{s['id']}/uyeler", headers=b,
                     json={"izleme_idler": []})
    assert y.status_code == 422

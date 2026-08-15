"""Tarama motoru testleri — uçtan uca, sahte çekiciyle (gerçek ağ yok)."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from keepmoney.cekici import Cekim
from keepmoney.db import Base
from keepmoney.models import Alert, PriceReading, Product, Source, User, Watch, WatchSet
from keepmoney.worker import ARALIK_MAKS_DK, ARALIK_MIN_DK, Tarayici
from keepmoney.zaman import utc_simdi


class SahteCekici:
    """URL → HTML eşlemesi. Testler ağ olmadan tüm zinciri çalıştırır."""

    def __init__(self, sayfalar: dict[str, str] | None = None):
        self.sayfalar = sayfalar or {}
        self.cagrilar: list[str] = []

    def cek(self, url: str, kural: dict | None = None) -> Cekim:
        self.cagrilar.append(url)
        icerik = self.sayfalar.get(url)
        if icerik is None:
            return Cekim(html=None, http_kodu=500, hata="sahte: sayfa yok")
        if icerik == "__403__":
            return Cekim(html="engellendi", http_kodu=403)
        if icerik == "__404__":
            return Cekim(html="<html><head><title>Sayfa bulunamadı</title></head></html>",
                         http_kodu=404)
        return Cekim(html=icerik, http_kodu=200, yontem="requests")


def urun_sayfasi(fiyat: str, puan: str | None = None) -> str:
    agg = f',"aggregateRating":{{"ratingValue":"{puan}","reviewCount":"120"}}' if puan else ""
    return (f'<html><head><title>Ürün</title>'
            f'<script type="application/ld+json">'
            f'{{"@type":"Product","offers":{{"price":"{fiyat}","priceCurrency":"TRY"}}{agg}}}'
            f'</script></head><body>ürün</body></html>')


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def kur(db, fiyat="50000", url="https://magaza.com/urun", hedef=None,
        puan=None, ad="Test Ürün"):
    """Kullanıcı + ürün + kaynak + izleme kurar."""
    u = User(email="a@x.com", password_hash="x")
    db.add(u)
    p = Product(ad=ad, izleyen_sayisi=1)
    db.add(p)
    db.commit()
    s = Source(product_id=p.id, url=url, host="magaza.com")
    db.add(s)
    w = Watch(user_id=u.id, product_id=p.id, hedef_fiyat=hedef)
    db.add(w)
    db.commit()
    cekici = SahteCekici({url: urun_sayfasi(fiyat, puan)})
    return u, p, s, w, Tarayici(db, cekici)


# ---------- temel tarama ----------

def test_tarama_fiyati_yazar_ve_gecmise_ekler(db):
    _, p, s, _, t = kur(db, fiyat="52999.90")
    t.urun_tara(p)

    assert p.guncel_fiyat == 52999.90
    assert s.durum == "OK"
    assert s.son_guven == "json-ld"
    assert db.query(PriceReading).count() == 1


def test_puan_ve_yorum_urune_islenir(db):
    _, p, _, _, t = kur(db, fiyat="1000", puan="4.4")
    t.urun_tara(p)
    assert p.puan == 4.4
    assert p.yorum_sayisi == 120


def test_engelli_kaynak_isaretlenir_ve_ceza_alir(db):
    _, p, s, _, t = kur(db)
    t.cekici.sayfalar[s.url] = "__403__"
    t.urun_tara(p)

    assert s.durum == "ENGELLI"
    assert t.throttle.ceza_durumu("magaza.com") > 0
    assert p.guncel_fiyat is None


def test_olu_kaynak_isaretlenir(db):
    _, p, s, _, t = kur(db)
    t.cekici.sayfalar[s.url] = "__404__"
    t.urun_tara(p)
    assert s.durum == "OLU"


def test_geri_cekilmedeki_host_atlanir(db):
    _, p, _, _, t = kur(db)
    t.throttle.cezalandir("magaza.com")           # 5 dk ceza
    t.urun_tara(p)
    assert t.cekici.cagrilar == []                # hiç istek gitmedi


# ---------- çoklu kaynak ----------

def test_en_ucuz_kaynak_secilir(db):
    u = User(email="a@x.com", password_hash="x")
    p = Product(ad="Ürün", izleyen_sayisi=1)
    db.add_all([u, p])
    db.commit()
    db.add_all([
        Source(product_id=p.id, url="https://a.com/u", host="a.com"),
        Source(product_id=p.id, url="https://b.com/u", host="b.com"),
    ])
    db.add(Watch(user_id=u.id, product_id=p.id))
    db.commit()

    t = Tarayici(db, SahteCekici({
        "https://a.com/u": urun_sayfasi("1200"),
        "https://b.com/u": urun_sayfasi("1100"),
    }))
    t.urun_tara(p)
    assert p.guncel_fiyat == 1100


def test_bir_kaynagin_hatasi_digerini_iptal_etmez(db):
    u = User(email="a@x.com", password_hash="x")
    p = Product(ad="Ürün", izleyen_sayisi=1)
    db.add_all([u, p])
    db.commit()
    db.add_all([
        Source(product_id=p.id, url="https://olu.com/u", host="olu.com"),
        Source(product_id=p.id, url="https://iyi.com/u", host="iyi.com"),
    ])
    db.add(Watch(user_id=u.id, product_id=p.id))
    db.commit()

    t = Tarayici(db, SahteCekici({
        "https://olu.com/u": "__404__",
        "https://iyi.com/u": urun_sayfasi("900"),
    }))
    t.urun_tara(p)
    assert p.guncel_fiyat == 900


# ---------- koruma katmanı entegrasyonu ----------

def test_supheli_fiyat_gecmise_yazilmaz(db):
    """Ani %90 düşüş: ilk okumada kabul edilmez, ikinci okuma bekler."""
    _, p, s, _, t = kur(db, fiyat="50000")
    t.urun_tara(p)
    assert db.query(PriceReading).count() == 1

    t.cekici.sayfalar[s.url] = urun_sayfasi("2000")
    t.urun_tara(p)

    assert db.query(PriceReading).count() == 1     # yazılmadı
    assert s.bekleyen_fiyat == 2000
    assert p.guncel_fiyat == 50000                 # eski fiyat korundu


def test_ikinci_tutarli_okuma_dogrular(db):
    _, p, s, _, t = kur(db, fiyat="50000")
    t.urun_tara(p)
    t.cekici.sayfalar[s.url] = urun_sayfasi("2000")
    t.urun_tara(p)
    t.urun_tara(p)                                 # aynı değer tekrar

    assert p.guncel_fiyat == 2000
    assert s.bekleyen_fiyat is None
    assert db.query(PriceReading).count() == 2


# ---------- uyarılar ----------

def test_hedef_uyarisi_uretilir(db):
    _, p, _, w, t = kur(db, fiyat="45000", hedef=50000)
    t.urun_tara(p)

    uyari = db.query(Alert).filter(Alert.tur == "HEDEF").one()
    assert "45.000,00 TL" in uyari.mesaj
    assert w.son_bildirim_ts is not None


def test_hedef_ustundeyse_uyari_yok(db):
    _, p, _, _, t = kur(db, fiyat="55000", hedef=50000)
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 0


def test_cooldown_mukerrer_uyariyi_engeller(db):
    _, p, _, _, t = kur(db, fiyat="45000", hedef=50000)
    t.urun_tara(p)
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 1


def test_ek_dusus_cooldownu_deler(db):
    """Cooldown içinde olsa da fiyat %3+ daha düşerse yeniden bildir."""
    _, p, s, _, t = kur(db, fiyat="45000", hedef=50000)
    t.urun_tara(p)
    t.cekici.sayfalar[s.url] = urun_sayfasi("43000")
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 2


def test_susturulmus_izleme_uyari_almaz(db):
    _, p, _, w, t = kur(db, fiyat="45000", hedef=50000)
    w.sustur_bitis = utc_simdi() + timedelta(days=7)
    db.commit()
    t.urun_tara(p)
    assert db.query(Alert).count() == 0


def test_pasif_izleme_uyari_almaz(db):
    _, p, _, w, t = kur(db, fiyat="45000", hedef=50000)
    w.aktif = False
    db.commit()
    t.urun_tara(p)
    assert db.query(Alert).count() == 0


def test_iki_kullanici_farkli_hedef_farkli_uyari(db):
    """Aynı fiyat düşüşü kişiye göre alarm ya da sessizlik."""
    a = User(email="a@x.com", password_hash="x")
    b = User(email="b@x.com", password_hash="x")
    p = Product(ad="Ürün", izleyen_sayisi=2)
    db.add_all([a, b, p])
    db.commit()
    db.add(Source(product_id=p.id, url="https://m.com/u", host="m.com"))
    db.add_all([Watch(user_id=a.id, product_id=p.id, hedef_fiyat=50000),
                Watch(user_id=b.id, product_id=p.id, hedef_fiyat=40000)])
    db.commit()

    t = Tarayici(db, SahteCekici({"https://m.com/u": urun_sayfasi("45000")}))
    t.urun_tara(p)

    assert db.query(Alert).filter(Alert.user_id == a.id).count() == 1
    assert db.query(Alert).filter(Alert.user_id == b.id).count() == 0


# ---------- set bütçe uyarısı ----------

def test_set_toplami_butcenin_altina_inince_uyarir(db):
    u = User(email="a@x.com", password_hash="x")
    db.add(u)
    db.commit()
    s = WatchSet(user_id=u.id, ad="PC Toplama", hedef_butce=100000)
    db.add(s)
    db.commit()

    urunler = []
    for ad, fiyat in [("CPU", "30000"), ("GPU", "60000")]:
        p = Product(ad=ad, izleyen_sayisi=1)
        db.add(p)
        db.commit()
        db.add(Source(product_id=p.id, url=f"https://m.com/{ad}", host="m.com"))
        db.add(Watch(user_id=u.id, product_id=p.id, set_id=s.id))
        db.commit()
        urunler.append((p, fiyat))

    t = Tarayici(db, SahteCekici({
        f"https://m.com/{p.ad}": urun_sayfasi(f) for p, f in urunler}))
    for p, _ in urunler:
        t.urun_tara(p)

    uyari = db.query(Alert).filter(Alert.tur == "SET_HEDEF").first()
    assert uyari is not None
    assert "90.000,00 TL" in uyari.mesaj


def test_eksik_uyeli_set_uyari_uretmez(db):
    """Bir üyenin fiyatı bilinmiyorsa toplam güvenilmez — sessiz kal."""
    u = User(email="a@x.com", password_hash="x")
    db.add(u)
    db.commit()
    s = WatchSet(user_id=u.id, ad="Set", hedef_butce=100000)
    db.add(s)
    db.commit()

    p1 = Product(ad="CPU", izleyen_sayisi=1)
    p2 = Product(ad="GPU", izleyen_sayisi=1)     # hiç taranmayacak
    db.add_all([p1, p2])
    db.commit()
    db.add(Source(product_id=p1.id, url="https://m.com/cpu", host="m.com"))
    db.add_all([Watch(user_id=u.id, product_id=p1.id, set_id=s.id),
                Watch(user_id=u.id, product_id=p2.id, set_id=s.id)])
    db.commit()

    t = Tarayici(db, SahteCekici({"https://m.com/cpu": urun_sayfasi("30000")}))
    t.urun_tara(p1)
    assert db.query(Alert).filter(Alert.tur == "SET_HEDEF").count() == 0


# ---------- sıra seçimi ve uyarlanabilir aralık ----------

def test_hic_taranmamis_urun_siraya_girer(db):
    _, p, _, _, t = kur(db)
    assert p in t.taranacak_urunler()


def test_yeni_taranmis_urun_siraya_girmez(db):
    _, p, _, _, t = kur(db)
    p.son_kontrol = utc_simdi()
    p.kontrol_araligi_dk = 180
    db.commit()
    assert t.taranacak_urunler() == []


def test_cok_izlenen_urun_once_taranir(db):
    az = Product(ad="Az izlenen", izleyen_sayisi=1)
    cok = Product(ad="Çok izlenen", izleyen_sayisi=50)
    db.add_all([az, cok])
    db.commit()
    t = Tarayici(db, SahteCekici())
    assert t.taranacak_urunler()[0].ad == "Çok izlenen"


def test_hedefe_yakin_urun_sik_taranir(db):
    _, p, _, _, t = kur(db, fiyat="52000", hedef=50000)   # %4 yakın
    t.urun_tara(p)
    assert p.kontrol_araligi_dk == ARALIK_MIN_DK


def test_hareketsiz_urun_seyrek_taranir(db):
    _, p, s, _, t = kur(db, fiyat="50000", hedef=10000)   # hedef çok uzak
    for gun in range(10, 0, -1):
        db.add(PriceReading(product_id=p.id, source_id=s.id, fiyat=50000,
                            ts=utc_simdi() - timedelta(days=gun)))
    db.commit()
    t.urun_tara(p)
    assert p.kontrol_araligi_dk == ARALIK_MAKS_DK


def test_okunamayan_urun_sik_denenir(db):
    _, p, s, _, t = kur(db)
    t.cekici.sayfalar[s.url] = "__403__"
    t.urun_tara(p)
    assert p.kontrol_araligi_dk == ARALIK_MIN_DK


# ---------- tur ----------

def test_tur_calistir_ozet_dondurur(db):
    _, _p, _, _, t = kur(db, fiyat="1000", hedef=2000)
    sonuc = t.tur_calistir()
    assert sonuc.taranan_urun == 1
    assert sonuc.okunan_kaynak == 1
    assert sonuc.uretilen_uyari == 1


# ---------- gözlemlenebilirlik ----------

def test_basarili_okuma_domain_sagligina_yazilir(db):
    from keepmoney.models import DomainHealth
    _, p, _, _, t = kur(db, fiyat="1000")
    t.urun_tara(p)

    d = db.query(DomainHealth).filter(DomainHealth.domain == "magaza.com").one()
    assert d.basarili == 1
    assert d.basarisiz == 0
    assert d.son_durum == "OK"


def test_engelli_okuma_basarisiz_sayilir(db):
    from keepmoney.models import DomainHealth
    _, p, s, _, t = kur(db)
    t.cekici.sayfalar[s.url] = "__403__"
    t.urun_tara(p)

    d = db.query(DomainHealth).filter(DomainHealth.domain == "magaza.com").one()
    assert d.basarisiz == 1
    assert d.son_durum == "ENGELLI"


def test_olu_kaynak_domain_sagligina_yansir(db):
    from keepmoney.models import DomainHealth
    _, p, s, _, t = kur(db)
    t.cekici.sayfalar[s.url] = "__404__"
    t.urun_tara(p)
    assert db.query(DomainHealth).one().son_durum == "OLU"

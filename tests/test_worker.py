"""Tarama motoru testleri — uçtan uca, sahte çekiciyle (gerçek ağ yok)."""
import time
from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from keepmoney.cekici import Cekim
from keepmoney.models import Alert, PriceReading, Product, Source, User, Watch, WatchSet
from keepmoney.throttle import HostThrottle
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
def db(motor):
    s = sessionmaker(bind=motor)()
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
    return u, p, s, w, Tarayici(db, cekici, HostThrottle(min_gap=0))


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
    }), HostThrottle(min_gap=0))
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
    }), HostThrottle(min_gap=0))
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

    t = Tarayici(db, SahteCekici({"https://m.com/u": urun_sayfasi("45000")}), HostThrottle(min_gap=0))
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
        f"https://m.com/{p.ad}": urun_sayfasi(f) for p, f in urunler}), HostThrottle(min_gap=0))
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

    t = Tarayici(db, SahteCekici({"https://m.com/cpu": urun_sayfasi("30000")}), HostThrottle(min_gap=0))
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
    p.sonraki_kontrol = utc_simdi() + timedelta(minutes=180)
    db.commit()
    assert t.taranacak_urunler() == []


def test_vakti_gelen_urun_siraya_girer(db):
    _, p, _, _, t = kur(db)
    p.sonraki_kontrol = utc_simdi() - timedelta(minutes=1)
    db.commit()
    assert p in t.taranacak_urunler()


def test_tarama_sonrasi_sira_zamani_yazilir(db):
    """Kuyruğun ilerlemesi buna bağlı: yazılmazsa ürün her turda yeniden
    taranır ve tarayıcı tek ürüne kilitlenir."""
    _, p, _, _, t = kur(db)
    t.urun_tara(p)
    assert p.sonraki_kontrol is not None
    beklenen = utc_simdi() + timedelta(minutes=p.kontrol_araligi_dk)
    assert abs((p.sonraki_kontrol - beklenen).total_seconds()) < 60
    assert t.taranacak_urunler() == []


def test_secim_tum_tabloyu_belege_cekmez(db):
    """Süzme SQL'de olmalı. Python'da süzülürse limit'in bir anlamı kalmaz
    ve her tur tam tablo taraması olur."""
    for n in range(30):
        db.add(Product(ad=f"U{n}", izleyen_sayisi=1))
    db.commit()
    t = Tarayici(db, SahteCekici(), HostThrottle(min_gap=0))

    sorgular = []
    from sqlalchemy import event
    motor = db.get_bind()

    def yakala(conn, cursor, ifade, params, *a, **kw):
        sorgular.append((ifade, params))

    event.listen(motor, "before_cursor_execute", yakala)
    try:
        secilen = t.taranacak_urunler(limit=5)
    finally:
        event.remove(motor, "before_cursor_execute", yakala)

    assert len(secilen) == 5
    assert any("LIMIT" in i.upper() for i, _ in sorgular), sorgular


def test_cok_izlenen_urun_once_taranir(db):
    az = Product(ad="Az izlenen", izleyen_sayisi=1)
    cok = Product(ad="Çok izlenen", izleyen_sayisi=50)
    db.add_all([az, cok])
    db.commit()
    t = Tarayici(db, SahteCekici(), HostThrottle(min_gap=0))
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


# ---------- bozuk kaynak bildirimi (KAYNAK_BOZUK) ----------

def test_ust_uste_hata_kullaniciya_bildirilir(db):
    """Bir dönem bu uyarı HİÇ üretilmiyordu: `karar.dogrula` "bozuk" diyor,
    `hata_serisi` artıyor, arayüzde etiketi bile hazır — ama Alert satırı
    hiç yazılmıyordu. Kaynak sessizce ölünce kullanıcı bayat fiyata bakıyordu.
    """
    _, p, _s, _, t = kur(db)
    t.cekici.sayfalar.clear()            # her tur "sayfa yok" → hata

    from keepmoney.worker import BOZUK_HATA_ESIGI
    for _ in range(BOZUK_HATA_ESIGI):
        t.urun_tara(p)

    uyari = db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").all()
    assert len(uyari) == 1
    assert "okunamıyor" in uyari[0].baslik
    assert db.query(Source).one().bozuk_uyarildi is True


def test_esik_altinda_bildirim_gitmez(db):
    """Tek turluk arıza gürültüdür — site bakımda olabilir."""
    _, p, _s, _, t = kur(db)
    t.cekici.sayfalar.clear()
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").count() == 0


def test_ayni_ariza_icin_tek_bildirim(db):
    """Kaynak günlerce bozuk kalabilir; her turda bildirim spam olur."""
    _, p, _s, _, t = kur(db)
    t.cekici.sayfalar.clear()
    from keepmoney.worker import BOZUK_HATA_ESIGI
    for _ in range(BOZUK_HATA_ESIGI + 4):
        t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").count() == 1


def test_kaynak_duzelince_bayrak_dusr(db):
    """Düzelip yeniden bozulan kaynak için tekrar haber verilebilmeli."""
    url = "https://magaza.com/urun"
    _, p, _s, _, t = kur(db, url=url)
    t.cekici.sayfalar.clear()
    from keepmoney.worker import BOZUK_HATA_ESIGI
    for _ in range(BOZUK_HATA_ESIGI):
        t.urun_tara(p)
    assert db.query(Source).one().bozuk_uyarildi is True

    t.cekici.sayfalar[url] = urun_sayfasi("50000")
    t.urun_tara(p)
    kaynak = db.query(Source).one()
    assert kaynak.bozuk_uyarildi is False
    assert kaynak.hata_serisi == 0


def test_calisan_kaynak_varsa_bildirim_gitmez(db):
    """Ürünün başka kaynağı fiyat veriyorsa kullanıcının umurunda değil —
    doğru fiyatı görmeye devam ediyor. Gürültü üretme."""
    iyi = "https://iyi.com/urun"
    kotu = "https://kotu.com/urun"
    _, p, _s, _, t = kur(db, url=kotu)
    db.add(Source(product_id=p.id, url=iyi, host="iyi.com"))
    db.commit()
    t.cekici.sayfalar = {iyi: urun_sayfasi("50000")}   # kotu.com hep hata

    from keepmoney.worker import BOZUK_HATA_ESIGI
    for _ in range(BOZUK_HATA_ESIGI + 2):
        t.urun_tara(p)

    assert db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").count() == 0
    assert db.query(Product).one().guncel_fiyat == 50000


def test_olu_sayfa_hemen_bildirilir(db):
    """404 kalıcıdır — eşik beklemeye gerek yok."""
    url = "https://magaza.com/urun"
    _, p, _s, _, t = kur(db, url=url)
    t.cekici.sayfalar[url] = "__404__"
    t.urun_tara(p)

    uyari = db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").one()
    assert "kaldırılmış" in uyari.mesaj


def test_bozuk_bildirimi_tum_izleyenlere_gider(db):
    _, p, _s, _, t = kur(db)
    ikinci = User(email="b@x.com", password_hash="x")
    db.add(ikinci)
    db.commit()
    db.add(Watch(user_id=ikinci.id, product_id=p.id))
    db.commit()

    t.cekici.sayfalar.clear()
    from keepmoney.worker import BOZUK_HATA_ESIGI
    for _ in range(BOZUK_HATA_ESIGI):
        t.urun_tara(p)

    assert db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").count() == 2


def test_gecmis_urun_basina_tek_kez_okunur(db):
    """`uyari_uret` ve `_sonraki_aralik` ayrı ayrı tüm fiyat geçmişini
    çekiyordu — ürün başına iki tam tablo taraması."""
    _, p, s, _, t = kur(db)
    for gun in range(5):
        db.add(PriceReading(source_id=s.id, product_id=p.id, fiyat=50000,
                            ts=utc_simdi() - timedelta(days=gun)))
    db.commit()

    cagrilar = []
    gercek = t._okuma_gecmisi
    t._okuma_gecmisi = lambda pid: (cagrilar.append(pid), gercek(pid))[1]

    t.urun_tara(p)
    assert len(cagrilar) == 1, f"{len(cagrilar)} kez okundu"


def test_tarama_ayni_hosta_aralik_birakir(db):
    """Throttle çağrılıyor mu? Bir dönem hiç çağrılmıyordu: tarayıcı bir
    turda aynı siteye tüm istekleri arka arkaya atıp IP'yi yaktırırdı."""
    u = User(email="a@x.com", password_hash="x")
    db.add(u)
    p = Product(ad="Ürün", izleyen_sayisi=1)
    db.add(p)
    db.commit()
    sayfalar = {}
    for n in range(3):
        url = f"https://magaza.com/u{n}"
        db.add(Source(product_id=p.id, url=url, host="magaza.com"))
        sayfalar[url] = urun_sayfasi("1000")
    db.commit()

    throttle = HostThrottle(min_gap=0)
    beklenenler = []
    gercek = throttle.bekle
    throttle.bekle = lambda h: (beklenenler.append(h), gercek(h))[1]

    Tarayici(db, SahteCekici(sayfalar), throttle).urun_tara(p)
    assert beklenenler == ["magaza.com"] * 3


def test_geri_cekilmedeki_host_bekletilmez(db):
    """Cezalı host atlanmalı, sırasını BEKLEMEMELİ — beklerse worker
    slotu dakikalarca işgal edilir ve tüm tarama kilitlenir."""
    _, p, _s, _, t = kur(db)
    t.throttle.cezalandir("magaza.com")

    basla = time.monotonic()
    t.urun_tara(p)
    assert time.monotonic() - basla < 1.0
    assert t.cekici.cagrilar == []

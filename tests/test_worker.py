"""Tarama motoru testleri — uçtan uca, sahte çekiciyle (gerçek ağ yok)."""
import time
from datetime import datetime, timedelta

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


# Sessiz saatler (00:00-08:00 TR) NORMAL alarmı erteliyor — gerçek ve istenen
# bir davranış. Ama uyarı testleri saati sabitlemiyordu: paket her gece
# 00:00-08:00 arasında KIRMIZIYA dönüyordu ve bu, gerçek koşuda yakalandı
# (yerel saat 00:04'te altı test birden düştü). CI için de geçerli — 21:00-05:00
# UTC arasında tetiklenen her koşu rastgele kırılırdı.
#
# Çözüm saatin SABİTLENMESİ, kuralın kapatılması değil: gerçek `sessiz_saat_mi`
# çağrılmaya devam ediyor, yalnızca "şimdi"nin yerine sabit bir öğle vakti
# konuyor. Kuralın kendisi aşağıda ayrıca test ediliyor.
OGLE_UTC = datetime(2026, 8, 15, 11, 0)      # naive UTC → 14:00 Türkiye
GECE_UTC = datetime(2026, 8, 15, 0, 30)      # naive UTC → 03:30 Türkiye


def _saati_sabitle(monkeypatch, an):
    from keepmoney import worker as w
    from keepmoney.zaman import sessiz_saat_mi as gercek

    monkeypatch.setattr(
        w, "sessiz_saat_mi",
        lambda baslangic, bitis, dt=None: gercek(baslangic, bitis, dt or an))


@pytest.fixture(autouse=True)
def _gunduz(monkeypatch):
    _saati_sabitle(monkeypatch, OGLE_UTC)


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


# ---------- bağlam sütunları: sinyal artık atılmıyor (BACKLOG A2) ----------

def _gecmis_ekle(db, p, s, gun_sayisi, guncel_fiyat=1000):
    """`gun_sayisi` FARKLI güne yayılan okuma ekler (bugün HARİÇ — bugünkü
    okuma taramanın kendisinden gelecek). MIN_GUN=5 eşiğini geçmek/geçmemek
    için testler bu sayıyı seçiyor."""
    simdi = utc_simdi()
    for gun in range(gun_sayisi, 0, -1):
        db.add(PriceReading(source_id=s.id, product_id=p.id,
                            fiyat=guncel_fiyat + gun, ts=simdi - timedelta(days=gun)))
    db.commit()


def test_yeterli_gecmiste_bir_tur_sonrasi_baglam_doluyor(db):
    """MIN_GUN (5) eşiğini geçen ürün: bir taramadan sonra sinyal VE
    baglam_ts dolu olmalı — artık hesaplanıp atılmıyor."""
    _, p, s, _, t = kur(db, fiyat="1000")
    _gecmis_ekle(db, p, s, gun_sayisi=6)          # + bugünkü okuma = 7 gün

    t.urun_tara(p)

    assert p.sinyal in ("dip", "ucuz", "pahali")
    assert p.dip90 is not None
    assert p.medyan90 is not None
    assert p.yuzdelik is not None
    assert p.baglam_ts is not None
    assert p.gecmis_gun == 7


def test_yetersiz_gecmiste_sinyal_bos_ama_gecmis_gun_ilerliyor(db):
    """3 günlük geçmiş MIN_GUN (5) altında — `analiz.fiyat_baglami` None
    döner, sinyal boş kalmalı. Ama `gecmis_gun` yine de yazılmalı: A7'nin
    "3/7 gün — geçmiş biriktiriliyor" göstergesi tam bu sayıya dayanıyor,
    sinyal daha hesaplanamıyor olsa bile ilerleme gösterilebilmeli."""
    _, p, s, _, t = kur(db, fiyat="1000")
    _gecmis_ekle(db, p, s, gun_sayisi=2)          # + bugünkü okuma = 3 gün

    t.urun_tara(p)

    assert p.sinyal is None
    assert p.dip90 is None
    assert p.gecmis_gun == 3
    assert p.baglam_ts is not None                # bu tur gerçekten okundu


def test_okunamayan_turda_eski_baglam_korunur(db):
    """İkinci turda kaynak tamamen okunamazsa (`en_iyi is None`, taze fiyat
    yok) altı bağlam sütununa da DOKUNULMAMALI. `uyari_uret` yine de
    `urun.guncel_fiyat` (bayat, önceki tur) ile çağrılır ve teorik olarak
    aynı baglam'ı yeniden üretebilirdi — ama bunu Product'a yazmak "az önce
    doğrulandı" yanılsaması verirdi. Ölçüt: değerler birebir AYNI kalmalı."""
    _, p, s, _, t = kur(db, fiyat="1000")
    _gecmis_ekle(db, p, s, gun_sayisi=6)

    t.urun_tara(p)
    assert p.sinyal is not None                   # önkoşul: ilk tur doldurdu
    eski = (p.sinyal, p.dip90, p.medyan90, p.yuzdelik, p.gecmis_gun, p.baglam_ts)

    t.cekici.sayfalar.pop(s.url)                  # ikinci turda kaynak "yok"
    t.urun_tara(p)

    assert (p.sinyal, p.dip90, p.medyan90, p.yuzdelik,
            p.gecmis_gun, p.baglam_ts) == eski


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


# ---------- yüzde uyarısı (BACKLOG E2) ----------

def _sabit_medyan_gecmisi(db, p, s, gun_sayisi=6, taban_fiyat=1000.0):
    """`gun_sayisi` FARKLI günde AYNI `taban_fiyat` okuması ekler (bugün
    HARİÇ — o taramanın kendisinden gelecek). `_gecmis_ekle`'nin aksine
    (orada her gün FARKLI bir fiyat, `+gun` kayması) burada TÜM geçmiş
    SABİT — medyan90'ı bugünkü taranan fiyattan BAĞIMSIZ, kontrollü bir
    sayıya (`taban_fiyat`) sabitlemek için: 6 sabit okuma + 1 (düşük)
    bugünkü okuma sıralandığında medyan (7 değerin 4.'sü) hep
    `taban_fiyat` kalır — yüzde eşiği sınır testleri (%14,9 / %15,1) tam
    sayı üzerinden yürüsün diye."""
    simdi = utc_simdi()
    for gun in range(gun_sayisi, 0, -1):
        db.add(PriceReading(source_id=s.id, product_id=p.id,
                            fiyat=taban_fiyat, ts=simdi - timedelta(days=gun)))
    db.commit()


def test_yuzde_esik_altinda_uyari_uretmez(db):
    """Kabul ölçütü: %15 eşiğinde %14,9 düşüş uyarı üretmiyor.

    Medyan 1.000 (sabitlendi), %14,9 düşüş = 851,00 — eşik fiyatı (850,00)
    henüz GEÇMEDİ (851 > 850)."""
    _, p, s, w, t = kur(db, fiyat="851.00")
    w.dusus_yuzdesi = 15
    db.commit()
    _sabit_medyan_gecmisi(db, p, s)

    t.urun_tara(p)

    assert db.query(Alert).filter(Alert.tur == "YUZDE").count() == 0


def test_yuzde_esik_ustunde_uyari_uretir(db):
    """Kabul ölçütü: %15 eşiğinde %15,1 düşüş uyarı üretiyor.

    Medyan 1.000 (sabitlendi), %15,1 düşüş = 849,00 — eşik fiyatını
    (850,00) GEÇTİ (849 <= 850)."""
    _, p, s, w, t = kur(db, fiyat="849.00")
    w.dusus_yuzdesi = 15
    db.commit()
    _sabit_medyan_gecmisi(db, p, s)

    t.urun_tara(p)

    uyari = db.query(Alert).filter(Alert.tur == "YUZDE").one()
    assert "849,00 TL" in uyari.mesaj
    assert w.son_bildirim_ts is not None


def test_hem_hedef_hem_yuzde_saglaninca_yalniz_hedef_cikar(db):
    """Kabul ölçütü: hem hedef hem yüzde sağlanınca yalnızca hedef uyarısı
    çıkıyor — sıra acil → hedef → yüzde → dip, `elif` zinciri ikinci
    uyarıyı BASTIRIR."""
    _, p, s, w, t = kur(db, fiyat="849.00", hedef=900)
    w.dusus_yuzdesi = 15                      # %15,1 düşüş de sağlanıyor
    db.commit()
    _sabit_medyan_gecmisi(db, p, s)

    t.urun_tara(p)

    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 1
    assert db.query(Alert).filter(Alert.tur == "YUZDE").count() == 0


def test_yuzde_yedi_gunden_az_gecmiste_hic_uretilmez(db):
    """Kabul ölçütü: 7 günden az geçmişte hiç çıkmıyor — medyan az veriyle
    güvenilmez. 5 geçmiş gün + bugün = 6 gün (< 7); fiyat eşiğin ÇOK
    altına (medyanın yarısına) düşse bile YUZDE hiç üretilmemeli."""
    _, p, s, w, t = kur(db, fiyat="500.00")
    w.dusus_yuzdesi = 15
    db.commit()
    _sabit_medyan_gecmisi(db, p, s, gun_sayisi=5)   # 5 + bugün = 6 gün

    t.urun_tara(p)

    assert db.query(Alert).filter(Alert.tur == "YUZDE").count() == 0


def test_yuzde_sessiz_saatte_ertelenir(db, monkeypatch):
    """Sessiz saat kuralı yüzde uyarısı için de AYNEN geçerli (BACKLOG E2)
    — ertelenir, iptal edilmez: `son_bildirim_ts` güncellenmediği için
    sabah kendiliğinden tetiklenir (HEDEF'teki aynı davranış,
    `test_sessiz_saatte_normal_alarm_ertelenir`)."""
    _saati_sabitle(monkeypatch, GECE_UTC)
    _, p, s, w, t = kur(db, fiyat="849.00")
    w.dusus_yuzdesi = 15
    db.commit()
    _sabit_medyan_gecmisi(db, p, s)

    t.urun_tara(p)

    assert db.query(Alert).filter(Alert.tur == "YUZDE").count() == 0
    assert w.son_bildirim_ts is None


def test_yuzde_ve_dip_ayni_anda_saglaninca_yalniz_yuzde_cikar(db):
    """Sıra yüzde → dip: ikisi de aynı taramada sağlanabilir (aşırı bir
    düşüş hem yüzde eşiğini geçer hem tüm zamanların dibini kırar) ama
    `elif` zinciri yalnızca YUZDE'yi üretmeli."""
    _, p, s, w, t = kur(db, fiyat="500.00")       # medyanın YARISI — hem
    w.dusus_yuzdesi = 15                          # %15 eşiğini aşıyor hem
    db.commit()                                   # tüm zamanların dibini kırıyor
    _sabit_medyan_gecmisi(db, p, s)

    t.urun_tara(p)

    assert db.query(Alert).filter(Alert.tur == "YUZDE").count() == 1
    assert db.query(Alert).filter(Alert.tur == "DIP").count() == 0


# ---------- yeniden kurma / rearm (BACKLOG E4) ----------
# `utc_simdi()` GERÇEK saati döner (bu dosyada yalnızca `sessiz_saat_mi`
# sabitleniyor, bkz. `_gunduz`) — bu yüzden "N gün geçti" GERÇEK zamanı
# ileri sarmak yerine `son_bildirim_ts`i GEÇMİŞE elle çekerek simüle
# ediliyor. Aynı tekniğin `test_ek_dusus_cooldownu_deler` ile ortak
# noktası: ikisi de gerçek "şimdi" ile geçmiş bir zaman damgası
# arasındaki FARKI test ediyor, zamanın kendisini değil.

def test_yeniden_kur_suresi_dolunca_tekrar_uyari_cikar(db):
    """Kabul ölçütü: süre dolunca aynı ürün için tekrar uyarı çıkıyor."""
    _, p, _, w, t = kur(db, fiyat="45000", hedef=50000)
    w.yeniden_kur_gun = 3
    db.commit()
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 1

    w.son_bildirim_ts = utc_simdi() - timedelta(days=4)   # 3 günlük eşiği aştı
    db.commit()
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 2


def test_yeniden_kur_suresi_dolmadan_tekrar_uyari_cikmaz(db):
    _, p, _, w, t = kur(db, fiyat="45000", hedef=50000)
    w.yeniden_kur_gun = 7
    db.commit()
    t.urun_tara(p)

    w.son_bildirim_ts = utc_simdi() - timedelta(days=2)   # 7 günlük eşiğin İÇİNDE
    db.commit()
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 1


def test_yeniden_kur_gun_bos_ise_varsayilan_yedi_gun_kullanilir(db):
    """`yeniden_kur_gun` hiç seçilmediyse (`None`) E1'in şema yorumunda
    yazılı varsayılan (7 gün) uygulanır."""
    _, p, _, w, t = kur(db, fiyat="45000", hedef=50000)
    t.urun_tara(p)

    w.son_bildirim_ts = utc_simdi() - timedelta(days=6)
    db.commit()
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 1  # 6 < 7, henüz değil

    w.son_bildirim_ts = utc_simdi() - timedelta(days=8)
    db.commit()
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 2  # 8 > 7


def test_yeniden_kur_gun_hic_secilirse_bir_daha_uyari_cikmaz(db):
    """Kabul ölçütü: 'hiç' (0) seçilirse bir daha çıkmıyor — EK DÜŞÜŞ
    İSTİSNASI DAHİL (kullanıcı açıkça "rahatsız etme" dedi), süre ne kadar
    geçerse geçsin ve fiyat ne kadar düşerse düşsün."""
    _, p, s, w, t = kur(db, fiyat="45000", hedef=50000)
    w.yeniden_kur_gun = 0
    db.commit()
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 1

    w.son_bildirim_ts = utc_simdi() - timedelta(days=365)
    db.commit()
    t.cekici.sayfalar[s.url] = urun_sayfasi("10000")      # büyük ek düşüş
    t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 1  # hâlâ 1


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
        db.add(Watch(user_id=u.id, product_id=p.id, setler=[s]))
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
    # Üyelik ÖNCE değil SONRA kuruluyor: `setler=[s]` iki nesneyi birden
    # `add_all` ederken, ikincisi işlenirken `s.watches` tembel yüklemesi
    # autoflush tetikliyor ve SQLAlchemy "add operation won't proceed" diye
    # uyarıyordu. Ölçüldü — üyelikler yine de yazılıyor, yani uyarı yanlış
    # alarm; ama gürültü gerçek bir uyarıyı gizler.
    w1 = Watch(user_id=u.id, product_id=p1.id)
    w2 = Watch(user_id=u.id, product_id=p2.id)
    db.add_all([w1, w2])
    db.commit()
    s.watches.extend([w1, w2])
    db.commit()
    # TESTİN KENDİ ÖNKOŞULU: set boş kalsaydı uyarı yine çıkmazdı (boş set
    # hedefte sayılmaz) ve test doğru sebepten değil, yanlış sebepten geçerdi.
    assert len(s.watches) == 2

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


def test_robots_yasakliysa_taranmaz(db):
    """Site sahibinin iradesi. Yok saymak IP'nin kalıcı engellenmesine ve
    savunulabilir bir konumun kaybına mal olur."""
    _, p, _s, _, t = kur(db)

    class YasakKapi:
        def izin_var_mi(self, url):
            return False

    t.robots = YasakKapi()
    t.urun_tara(p)

    assert t.cekici.cagrilar == []            # sayfaya HİÇ gidilmedi
    assert db.query(Source).one().durum == "ENGELLI"


def test_robots_izin_verince_taranir(db):
    _, p, _s, _, t = kur(db)
    t.urun_tara(p)
    assert len(t.cekici.cagrilar) == 1
    assert db.query(Product).one().guncel_fiyat == 50000


# ── Stokta yok: arıza değil, olgu ────────────────────────────────
# Gerçek denemede 13 linkin 2'si stoktan düşmüştü. Fiyatın okunamaması iki
# apayrı şey olabilir: ayıklayıcı bozulmuş olabilir ya da ürünün o an fiyatı
# yoktur. Birincisi düzeltilecek arıza, ikincisi kullanıcıya söylenecek olgu.

STOK_YOK_SAYFASI = (
    '<html><head><title>Ürün</title>'
    '<script type="application/ld+json">'
    '{"@type":"Product","offers":'
    '{"availability":"https://schema.org/OutOfStock"}}'
    '</script></head><body>ürün</body></html>')


def _stok_yok_kur(db):
    u = User(email="s@x.com", password_hash="x")
    db.add(u)
    prd = Product(ad="Tükenen Ürün", izleyen_sayisi=1)
    db.add(prd)
    db.commit()
    s = Source(product_id=prd.id, url="https://magaza.com/tukendi",
               host="magaza.com")
    db.add(s)
    db.add(Watch(user_id=u.id, product_id=prd.id))
    db.commit()
    cekici = SahteCekici({"https://magaza.com/tukendi": STOK_YOK_SAYFASI})
    return s, Tarayici(db, cekici, HostThrottle(min_gap=0))


def test_stok_yok_ayri_durum_olarak_kaydedilir(db):
    kaynak, t = _stok_yok_kur(db)
    t.kaynak_oku(kaynak)
    assert kaynak.durum == "STOKTA_YOK"
    assert kaynak.son_kontrol is not None


def test_stok_yok_hata_sayacini_sifirlar(db):
    """Haftalarca stokta olmayan bir ürün yüzünden 'fiyatını okuyamıyorum'
    uyarısı gitmemeli."""
    kaynak, t = _stok_yok_kur(db)
    kaynak.hata_serisi = 2
    t.kaynak_oku(kaynak)
    assert kaynak.hata_serisi == 0
    assert Tarayici._kaynak_bozuk_mu(kaynak) is False


def test_stok_yok_fiyatsiz_ama_isaretli_satir_yazar(db):
    """BACKLOG B4 — eskiden STOKTA_YOK hiç satır yazmazdı: "tarandı, stokta
    yoktu" ile "hiç taranmadı" grafikte AYNI görünüyordu (ikisi de boşluk).
    Şimdi `fiyat=None, stokta_var=False` ile İŞARETLİ bir satır yazılır —
    uydurma bir FİYAT değeri hâlâ YOK (`okumalar()`in `if f` süzgeci bu
    satırı istatistikten dışlar), ama grafiğin çizgiyi KESEBİLMESİ için
    gereken sinyal artık var."""
    kaynak, t = _stok_yok_kur(db)
    okuma = t.kaynak_oku(kaynak)
    assert okuma.fiyat is None
    assert okuma.ekstra["stok_yok"] is True

    satir = db.query(PriceReading).one()
    assert satir.fiyat is None
    assert satir.stokta_var is False
    assert satir.source_id == kaynak.id


# ---------- sessiz saatler ----------

def test_sessiz_saatte_normal_alarm_ertelenir(db, monkeypatch):
    """00:00-08:00 arası normal alarm gitmez.

    Kritik ayrıntı: uyarı ERTELENİR, iptal edilmez — `son_bildirim_ts`
    güncellenmediği için sabah ilk turda kendiliğinden tetiklenir. Bu satır
    hiç doğrudan test edilmemişti; uyarı testleri gündüz koştuğu için
    tesadüfen geçiyordu.
    """
    _saati_sabitle(monkeypatch, GECE_UTC)
    _, p, _, w, t = kur(db, fiyat="45000", hedef=50000)

    t.urun_tara(p)

    assert db.query(Alert).filter(Alert.tur == "HEDEF").count() == 0
    assert w.son_bildirim_ts is None          # sabah tetiklenebilsin


def test_sessiz_saatte_acil_esigi_deler(db, monkeypatch):
    """ACİL fiyat, sessiz saati DELER — kullanıcı bu eşiği tam da bunun için
    koyuyor. Uyarı yine HEDEF türünde çıkar; aciliyet başlıkta belirtilir."""
    _saati_sabitle(monkeypatch, GECE_UTC)
    _, p, _, w, t = kur(db, fiyat="45000", hedef=50000)
    w.acil_fiyat = 46000
    db.commit()

    t.urun_tara(p)

    uyari = db.query(Alert).filter(Alert.tur == "HEDEF").one()
    assert "ACİL" in uyari.baslik


# ---------- çoklu set üyeliği ----------


def test_ayni_urun_iki_sette_iki_ayri_uyari_uretir(db):
    """Bir ürün birden çok sette olabilir ve HER SET kendi bütçesini ayrı
    takip eder.

    Eskiden `Watch.set_id` tek sütundu: kullanıcı aynı ekran kartını hem
    "PC Toplama" hem "Kara Cuma" listesine koyamıyordu. İkisi de bütçe altına
    inerse İKİ uyarı gitmeli — farklı bütçelerin tutması ayrı bilgidir.
    """
    from keepmoney.models import WatchSet

    u = db.query(User).first()
    if u is None:
        u = User(email="a@x.com", password_hash="x")
        db.add(u)
        db.commit()

    s1 = WatchSet(user_id=u.id, ad="PC Toplama", hedef_butce=50000)
    s2 = WatchSet(user_id=u.id, ad="Kara Cuma", hedef_butce=60000)
    db.add_all([s1, s2])
    db.commit()

    p = Product(ad="Ekran Kartı", izleyen_sayisi=1)
    db.add(p)
    db.commit()
    db.add(Source(product_id=p.id, url="https://m.com/gpu", host="m.com"))
    db.add(Watch(user_id=u.id, product_id=p.id, setler=[s1, s2]))
    db.commit()

    t = Tarayici(db, SahteCekici({"https://m.com/gpu": urun_sayfasi("45000")}),
                 HostThrottle(min_gap=0))
    t.urun_tara(p)

    uyarilar = db.query(Alert).filter(Alert.tur == "SET_HEDEF").all()
    basliklar = " | ".join(a.baslik for a in uyarilar)
    assert len(uyarilar) == 2, f"iki set için iki uyarı bekleniyordu: {basliklar}"
    assert "PC Toplama" in basliklar
    assert "Kara Cuma" in basliklar


def test_butcesi_asan_set_icin_uyari_gitmez(db):
    """Ürün iki sette ama biri bütçeyi aşıyorsa YALNIZCA diğeri uyarır."""
    from keepmoney.models import WatchSet

    u = db.query(User).first()
    if u is None:
        u = User(email="a@x.com", password_hash="x")
        db.add(u)
        db.commit()

    ucuz = WatchSet(user_id=u.id, ad="Bol bütçe", hedef_butce=50000)
    dar = WatchSet(user_id=u.id, ad="Dar bütçe", hedef_butce=10000)
    db.add_all([ucuz, dar])
    db.commit()

    p = Product(ad="Ekran Kartı", izleyen_sayisi=1)
    db.add(p)
    db.commit()
    db.add(Source(product_id=p.id, url="https://m.com/gpu2", host="m.com"))
    db.add(Watch(user_id=u.id, product_id=p.id, setler=[ucuz, dar]))
    db.commit()

    t = Tarayici(db, SahteCekici({"https://m.com/gpu2": urun_sayfasi("45000")}),
                 HostThrottle(min_gap=0))
    t.urun_tara(p)

    uyarilar = db.query(Alert).filter(Alert.tur == "SET_HEDEF").all()
    assert len(uyarilar) == 1
    assert "Bol bütçe" in uyarilar[0].baslik


def test_setten_cikarilan_urun_digerinde_kalir(db):
    """Bir setten çıkarmak diğer üyelikleri etkilememeli."""
    from keepmoney.models import WatchSet
    from keepmoney.servisler import setler as set_svc

    u = db.query(User).first()
    if u is None:
        u = User(email="a@x.com", password_hash="x")
        db.add(u)
        db.commit()

    s1 = WatchSet(user_id=u.id, ad="Bir")
    s2 = WatchSet(user_id=u.id, ad="İki")
    db.add_all([s1, s2])
    db.commit()

    p = Product(ad="Ürün", izleyen_sayisi=1)
    db.add(p)
    db.commit()
    w = Watch(user_id=u.id, product_id=p.id, setler=[s1, s2])
    db.add(w)
    db.commit()

    assert set_svc.uye_cikar(db, u, s1.id, w.id) is True
    db.refresh(w)
    assert [s.id for s in w.setler] == [s2.id]


# ── Sessiz bozulma: sayfa açılıyor ama fiyat okunamıyor ──────────
#
# ÜRÜNÜN EN OLASI ÜRETİM ARIZASI BUDUR: mağaza HTML'ini haber vermeden
# değiştirir, seçici tutmaz, fiyat çıkmaz. Sayfa 200 döner, "ölü" değildir,
# "stokta yok" değildir, bot koruması da yoktur.
#
# ÖLÇÜLDÜ (düzeltmeden önce): 5 tur üst üste böyle bir sayfa okundu ve
#   • `hata_serisi` 0'da kaldı (artıran tek yer "sayfa hiç inmedi" dalıydı),
#   • `durum` BEKLEMEDE'ye düştü — arayüzde "bekliyor" diye görünür,
#   • `_kaynak_bozuk_mu` hiç tetiklenmedi, KAYNAK_BOZUK uyarısı ÜRETİLMEDİ,
#   • `son_kontrol` her turda tazelendi.
# Yani kullanıcı haftalarca eski bir fiyata, "az önce kontrol edildi"
# etiketiyle bakmaya devam ediyordu. Bu üründe güven tam da o etikete
# dayanıyor.
#
# Kök sebep: `karar.dogrula` bu durumda "fiyat-yok" diyor ama worker onu
# "beklemede" ile aynı kefeye koyuyordu — oysa "beklemede" fiyatın OKUNDUĞU
# (ikinci teyit beklenen) hâldir ve sayaç orada artmamalıdır.

FIYATSIZ_SAYFA = ('<html><head><title>Ürün</title></head><body>'
                  '<h1>Ürün</h1><div id="app">Yükleniyor…</div>'
                  '<p>Stoklarımızda! Hemen sepete ekleyin.</p></body></html>')


def _fiyatsiz_kurulum(db):
    u = User(email="a@x.com", password_hash="x")
    p = Product(ad="Ürün", izleyen_sayisi=1)
    db.add_all([u, p])
    db.commit()
    url = "https://magaza.com/u"
    s = Source(product_id=p.id, url=url, host="magaza.com")
    db.add(s)
    db.add(Watch(user_id=u.id, product_id=p.id, hedef_fiyat=1.0))
    db.commit()
    cekici = SahteCekici({url: FIYATSIZ_SAYFA})
    return p, s, Tarayici(db, cekici, HostThrottle(min_gap=0))


def test_fiyat_okunamayinca_hata_serisi_artiyor(db):
    """Asıl regresyon. `BEKLEMEDE` bırakılırsa sayaç hiç artmaz ve kaynak
    sonsuza kadar "bekliyor" görünür."""
    p, s, t = _fiyatsiz_kurulum(db)

    t.urun_tara(p)
    assert s.durum == "HATA", "sayfa indi ama fiyat yok — bu bir okuma hatasıdır"
    assert s.hata_serisi == 1

    t.urun_tara(p)
    assert s.hata_serisi == 2


def test_ucuncu_basarisiz_okumada_kullanici_haber_aliyor(db):
    """Kabul ölçütü: sessiz kalmasın. `BOZUK_HATA_ESIGI` (3) turda
    KAYNAK_BOZUK uyarısı üretilmeli."""
    p, _, t = _fiyatsiz_kurulum(db)

    for _ in range(2):
        t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").count() == 0

    t.urun_tara(p)                       # 3. başarısız okuma → eşik
    uyarilar = db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").all()
    assert len(uyarilar) == 1
    assert "fiyat okunamıyor" in uyarilar[0].baslik


def test_bozuk_kaynak_uyarisi_her_turda_TEKRARLANMIYOR(db):
    """Bildirim yorgunluğu: aynı arıza için tek uyarı yeter. `bozuk_uyarildi`
    bayrağı bunu sağlıyor — beş tur daha koşuyoruz."""
    p, _, t = _fiyatsiz_kurulum(db)
    for _ in range(8):
        t.urun_tara(p)
    assert db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").count() == 1


def test_fiyat_okunamayinca_ESKI_FIYAT_ve_gecmis_korunuyor(db):
    """Okunamayan tarama geçmişi BOZMAMALI: ne satır yazılmalı ne de
    ekrandaki fiyat sıfırlanmalı."""
    p, _, t = _fiyatsiz_kurulum(db)
    p.guncel_fiyat = 45999.90
    db.commit()

    for _ in range(4):
        t.urun_tara(p)

    assert p.guncel_fiyat == 45999.90
    assert db.query(PriceReading).count() == 0


def test_kaynak_duzelince_sayac_sifirlaniyor(db):
    """Geçici arıza kalıcı sayılmamalı: fiyat yeniden okunduğunda sayaç
    sıfırlanır ve bir dahaki bozulmada kullanıcı YENİDEN uyarılabilir."""
    p, s, t = _fiyatsiz_kurulum(db)
    for _ in range(3):
        t.urun_tara(p)
    assert s.hata_serisi >= 3
    assert s.bozuk_uyarildi is True

    t.cekici.sayfalar["https://magaza.com/u"] = urun_sayfasi("42000")
    t.urun_tara(p)

    assert s.durum == "OK"
    assert s.hata_serisi == 0
    assert s.bozuk_uyarildi is False
    assert p.guncel_fiyat == 42000.0


def test_beklemede_hali_sayaci_ARTIRMIYOR(db):
    """Ayrımın diğer yarısı. "beklemede" fiyatın OKUNDUĞU ama ikinci teyidin
    beklendiği hâldir; orada sayaç artsaydı sağlam bir kaynak üç turda
    "bozuk" ilan edilirdi. `%60 düşüş` şüpheli sayılıp teyit bekletir."""
    u = User(email="b@x.com", password_hash="x")
    p = Product(ad="Ürün", izleyen_sayisi=1, guncel_fiyat=50000.0)
    db.add_all([u, p])
    db.commit()
    url = "https://magaza.com/v"
    s = Source(product_id=p.id, url=url, host="magaza.com", son_fiyat=50000.0,
               durum="OK")
    db.add(s)
    db.add(Watch(user_id=u.id, product_id=p.id, hedef_fiyat=1.0))
    db.commit()

    t = Tarayici(db, SahteCekici({url: urun_sayfasi("20000")}),
                 HostThrottle(min_gap=0))
    t.urun_tara(p)

    assert s.durum == "BEKLEMEDE", "şüpheli fiyat teyit bekliyor"
    assert s.hata_serisi == 0, "teyit bekleyen okuma HATA sayılmamalı"


def test_bozuk_sebebi_erisim_ile_ayristirma_hatasini_AYIRIYOR(db):
    """Kullanıcıya doğru yeri göstermek: "sayfaya erişilemiyor" mesajı,
    sayfa açılıyorken yanlış yönlendirir."""
    p, _, t = _fiyatsiz_kurulum(db)
    for _ in range(3):
        t.urun_tara(p)

    uyari = db.query(Alert).filter(Alert.tur == "KAYNAK_BOZUK").one()
    assert "fiyat bulunamıyor" in uyari.mesaj
    assert "sayfaya erişilemiyor" not in uyari.mesaj

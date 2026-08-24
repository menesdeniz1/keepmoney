"""Tarama motoru — sistemin ana döngüsü.

    sırası gelen ürünleri seç
      → her kaynağı çek + çıkar
        → koruma katmanından geçir (karar.dogrula)
          → temiz okumaları geçmişe yaz
            → en ucuz kaynağı ürüne işle
              → izleyicilere uyarı üret
                → bir sonraki tarama zamanını ayarla

Bağımlılıklar DIŞARIDAN verilir (çekici, throttle, saat) — worker gerçek ağa
çıkmadan uçtan uca test edilebilsin diye. Testlerde sahte bir çekici veriliyor.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import analiz, ayikla, karar, olcumler, siteler
from .cekici import Cekici
from .fiyat import kisa_tl, tl
from .models import Alert, DomainHealth, PriceReading, Product, Source, Watch
from .robots import RobotsKapisi
from .throttle import HostThrottle
from .zaman import sessiz_saat_mi, tr_bugun, utc_simdi

log = logging.getLogger("keepmoney.worker")

# ── Bildirim politikası ──────────────────────────────────────────
# Aynı uyarı bu süre geçmeden tekrarlanmaz. Hedefin ALTINDA kalındığı sürece
# bu aralıkla hatırlatılır — kullanıcı "düştü, hâlâ düşük mü?" diye merak
# etmesin diye. Susturma ya da izlemeyi bırakma dışında durmaz.
HATIRLATMA_DK = 240                  # 4 saat

# Cooldown içinde olsa bile fiyat bu kadar daha düşerse yeniden bildir.
EK_DUSUS_YUZDE = 3.0

# Sessiz saatler (Türkiye saati). ACİL eşiği bunu deler.
SESSIZ_BASLANGIC, SESSIZ_BITIS = 0, 8

# ── Uyarlanabilir tarama sıklığı ─────────────────────────────────
# Ölçeklenmenin anahtarı: her ürünü saatte bir taramak 500 kullanıcıda
# imkânsız. Hedefe yakın / oynak ürün sık, aylardır kıpırdamayan seyrek taranır.
ARALIK_MIN_DK = 30
ARALIK_MAKS_DK = 1440                # 24 saat
HEDEFE_YAKIN_YUZDE = 10.0            # hedefin %10 yakınındaki ürün "sıcak"

# ── Bozuk kaynak eşikleri ────────────────────────────────────────
# Kullanıcıya "bu ürünün fiyatını artık okuyamıyorum" demeden önce kaç tur
# beklenir. Tek turluk arıza gürültüdür (site bakımda olabilir); ÜST ÜSTE
# tekrarlayan arıza haberdir.
BOZUK_HATA_ESIGI = 3                 # üst üste indirilemeyen sayfa
BOZUK_SUPHE_ESIGI = 2                # üst üste yapısal olarak saçma fiyat


@dataclass
class TaramaSonucu:
    taranan_urun: int = 0
    okunan_kaynak: int = 0
    basarisiz_kaynak: int = 0
    ertelenen_kaynak: int = 0
    fiyat_degisen: int = 0
    uretilen_uyari: int = 0
    hatalar: list[str] = field(default_factory=list)


class Tarayici:
    def __init__(self, db: Session, cekici: Cekici,
                 throttle: HostThrottle | None = None,
                 robots: RobotsKapisi | None = None):
        self.db = db
        self.cekici = cekici
        self.throttle = throttle or HostThrottle()
        self.robots = robots or RobotsKapisi()

    # ── seçim ────────────────────────────────────────────────────

    def taranacak_urunler(self, limit: int = 100,
                          simdi: datetime | None = None) -> list[Product]:
        """Sırası gelen ürünler: hiç taranmamışlar önce, sonra vakti gelenler.

        Süzme VERİTABANINDA yapılır. Eskiden tüm ürün tablosu belleğe çekilip
        Python'da süzülüyordu: her turda (dakikada bir) tam tablo taraması ve
        tüm satırların ORM nesnesine dönüştürülmesi. 50 üründe fark edilmez,
        50.000 üründe tarayıcıyı tek başına dize getirir.

        Sıralama `izleyen_sayisi`'na göre: çok izlenen ürün önce taranır.
        Bütçe yetmediğinde en çok kişiyi etkileyen ürün güncel kalır.
        """
        simdi = simdi or utc_simdi()
        return (self.db.query(Product)
                .filter((Product.sonraki_kontrol.is_(None))
                        | (Product.sonraki_kontrol <= simdi))
                .order_by(Product.izleyen_sayisi.desc(), Product.id)
                .limit(limit)
                .all())

    # ── gözlemlenebilirlik ───────────────────────────────────────

    def _sonucu_kaydet(self, host: str, sonuc: str) -> None:
        """Domain sağlığını DB'ye, sayacı Prometheus'a yazar.

        İkisi de gerekli: Prometheus anlık/kısa vadeli uyarı için, DB satırı
        kullanıcıya gösterilen "hangi mağaza sorunlu" paneli için (Prometheus
        tarihçesi bu ürün için tutulmuyor).
        """
        olcumler.kaynak_okuma.labels(domain=host, sonuc=sonuc).inc()

        kayit = (self.db.query(DomainHealth)
                 .filter(DomainHealth.domain == host).one_or_none())
        if kayit is None:
            kayit = DomainHealth(domain=host, basarili=0, basarisiz=0)
            self.db.add(kayit)
        if sonuc == "ok":
            kayit.basarili = (kayit.basarili or 0) + 1
            kayit.son_durum = "OK"
        else:
            kayit.basarisiz = (kayit.basarisiz or 0) + 1
            kayit.son_durum = sonuc.upper()
        kayit.son_kontrol = utc_simdi()

    # ── tek kaynak okuma ─────────────────────────────────────────

    def kaynak_oku(self, kaynak: Source) -> karar.KaynakOkumasi | None:
        """Bir kaynağı çeker, çıkarır, koruma katmanından geçirir.

        None döner = bu tur atlandı (host geri çekilmede). Bu bir HATA DEĞİL:
        kaynağın durumuna dokunulmaz, bir sonraki turda tekrar denenir.
        """
        if self.throttle.ertelenmeli_mi(kaynak.host):
            log.info("%s geri çekilmede, bu tur atlandı", kaynak.host)
            return None

        # Site sahibinin iradesi. Teknik bir zorunluluk değil ama yok saymak
        # IP'nin kalıcı engellenmesine ve savunulabilir bir konumun kaybına
        # mal olur (bkz. robots.py). ENGELLİ sayılır, hata değil: durum
        # kaydedilir ki kullanıcı "neden okunmuyor" sorusunun cevabını görsün.
        if not self.robots.izin_var_mi(kaynak.url):
            log.info("robots.txt izin vermiyor: %s", kaynak.url)
            kaynak.durum = "ENGELLI"
            kaynak.son_kontrol = utc_simdi()
            self._sonucu_kaydet(kaynak.host, "robots")
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host,
                                       engelli=True)

        # Aynı hosta asgari aralık. Bu çağrı olmadan tarayıcı bir turda aynı
        # siteye 50 isteği arka arkaya atar ve IP'yi yaktırır — throttle'ın
        # var oluş sebebi buydu ama çağıran yoktu (bkz. throttle.py).
        bekleme = self.throttle.bekle(kaynak.host)
        if bekleme > 0:
            log.debug("%s için %.1f sn beklendi", kaynak.host, bekleme)

        kural = siteler.kural(kaynak.url)
        cekim = self.cekici.cek(kaynak.url, kural)

        if cekim.engellendi:
            ceza = self.throttle.cezalandir(kaynak.host)
            log.warning("%s bot koruması — %.0f dk geri çekilme",
                        kaynak.host, ceza / 60)
            kaynak.durum = "ENGELLI"
            kaynak.son_kontrol = utc_simdi()
            self._sonucu_kaydet(kaynak.host, "engelli")
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host,
                                       engelli=True)

        if not cekim.html:
            kaynak.durum = "HATA"
            kaynak.hata_serisi = (kaynak.hata_serisi or 0) + 1
            kaynak.son_kontrol = utc_simdi()
            self._sonucu_kaydet(kaynak.host, "hata")
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host)

        c = ayikla.cikar(cekim.html, kural, cekim.http_kodu)

        if c.engelli:
            self.throttle.cezalandir(kaynak.host)
            kaynak.durum = "ENGELLI"
            kaynak.son_kontrol = utc_simdi()
            self._sonucu_kaydet(kaynak.host, "engelli")
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host,
                                       engelli=True)

        if c.olu:
            kaynak.durum = "OLU"
            kaynak.son_kontrol = utc_simdi()
            self._sonucu_kaydet(kaynak.host, "olu")
            log.warning("Ölü kaynak: %s", kaynak.url)
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host, olu=True)

        if c.stok_yok:
            # BAŞARILI bir okumadır: sayfa sağlam, ürünün o an fiyatı yok.
            # Hata sayacı SIFIRLANIR — tükenmiş ürün bozuk kaynak değildir;
            # haftalarca stokta olmayan bir ürün yüzünden "fiyatını okuyamıyorum"
            # uyarısı gitmemeli. Host da ödüllendirilir: site bizi engellemedi.
            self.throttle.odullendir(kaynak.host)
            kaynak.durum = "STOKTA_YOK"
            kaynak.hata_serisi = 0
            kaynak.son_kontrol = utc_simdi()
            self._sonucu_kaydet(kaynak.host, "stok_yok")
            log.info("Stokta yok: %s", kaynak.url)
            return karar.KaynakOkumasi(
                url=kaynak.url, host=kaynak.host,
                ekstra={"stok_yok": True, "baslik": c.baslik})

        self.throttle.odullendir(kaynak.host)

        okuma = karar.KaynakOkumasi(
            url=kaynak.url, host=kaynak.host, fiyat=c.fiyat, guven=c.guven,
            # Toplayıcıda gerçek satıcı, sayfanın sahibi değil o listedeki
            # en ucuz mağazadır: "Akakçe" demek kullanıcıya bilgi vermez.
            satici=c.satici_adi or kural.get("satici") or kaynak.satici,
            satici_sayisi=c.satici_sayisi, ikinci_fiyat=c.ikinci_fiyat,
            ekstra={"puan": c.puan, "yorum": c.yorum_sayisi, "baslik": c.baslik,
                    "satici_sayisi": c.satici_sayisi,
                    "ikinci_fiyat": c.ikinci_fiyat},
        )

        # Koruma katmanı — durum kaynakta saklanır, kullanıcıda değil
        durum = karar.IzlemeDurumu(
            son_iyi_fiyat=kaynak.son_fiyat,
            bekleyen_fiyat=kaynak.bekleyen_fiyat,
            asiri_supheli_seri=kaynak.asiri_supheli_seri or 0,
            asiri_supheli_uyarildi=bool(kaynak.bozuk_uyarildi),
        )
        hedef = self._en_dusuk_hedef(kaynak.product_id)
        guvenilir, sebep = karar.dogrula(okuma, durum, hedef)

        kaynak.bekleyen_fiyat = durum.bekleyen_fiyat
        kaynak.asiri_supheli_seri = durum.asiri_supheli_seri
        kaynak.bozuk_uyarildi = durum.asiri_supheli_uyarildi
        kaynak.son_kontrol = utc_simdi()
        kaynak.son_guven = c.guven
        # Pazar derinliği okuma REDDEDİLSE BİLE saklanır: kullanıcıya "neden
        # bu fiyata güvenmedik" sorusunun cevabını veren şey tam da bu tablo.
        if c.satici_sayisi is not None:
            kaynak.satici_sayisi = c.satici_sayisi
            kaynak.ikinci_fiyat = c.ikinci_fiyat
            kaynak.satici = c.satici_adi or kaynak.satici

        olcumler.fiyat_guveni.labels(guven=c.guven).inc()

        if not guvenilir:
            kaynak.durum = "HATA" if sebep == "bozuk" else "BEKLEMEDE"
            self._sonucu_kaydet(kaynak.host, "reddedildi")
            log.info("%s okuması kullanılmadı (%s): %s",
                     kaynak.host, sebep, tl(c.fiyat))
            okuma.ekstra["reddedildi"] = sebep
            return okuma

        kaynak.durum = "OK"
        kaynak.hata_serisi = 0
        # Kaynak düzeldi: bir dahaki bozulmada kullanıcı yeniden uyarılabilsin.
        kaynak.bozuk_uyarildi = False
        kaynak.son_fiyat = c.fiyat
        self._sonucu_kaydet(kaynak.host, "ok")
        if c.fiyat is not None:
            self.db.add(PriceReading(source_id=kaynak.id,
                                     product_id=kaynak.product_id,
                                     fiyat=c.fiyat, ts=utc_simdi()))
        return okuma

    def _en_dusuk_hedef(self, product_id: int) -> float | None:
        """Bu ürünü izleyenlerin EN DÜŞÜK hedefi. Koruma katmanı "hedefin
        yarısından ucuz" kontrolünü buna göre yapar; en düşük hedef en
        muhafazakâr eşiği verir."""
        hedefler = [w.hedef_fiyat for w in
                    self.db.query(Watch).filter(Watch.product_id == product_id).all()
                    if w.hedef_fiyat]
        return min(hedefler) if hedefler else None

    # ── ürün tarama ──────────────────────────────────────────────

    def urun_tara(self, urun: Product, sonuc: TaramaSonucu | None = None) -> None:
        sonuc = sonuc or TaramaSonucu()
        eski_fiyat = urun.guncel_fiyat
        okumalar: list[karar.KaynakOkumasi] = []

        # Toplayıcı kaynaklar önce: tek sayfada N satıcının en ucuzu var,
        # bütçe biterse en değerli okuma elde kalmış olur.
        kaynaklar = sorted(urun.sources,
                           key=lambda k: (not siteler.toplayici_mi(k.url), k.id))

        for kaynak in kaynaklar:
            try:
                okuma = self.kaynak_oku(kaynak)
            except Exception as e:                   # bir kaynak diğerlerini iptal etmesin
                log.error("%s okunamadı: %s", kaynak.url, e)
                sonuc.hatalar.append(f"{kaynak.host}: {type(e).__name__}")
                sonuc.basarisiz_kaynak += 1
                continue
            if okuma is None:
                sonuc.ertelenen_kaynak += 1
                continue
            sonuc.okunan_kaynak += 1
            if okuma.fiyat is None or okuma.ekstra.get("reddedildi"):
                sonuc.basarisiz_kaynak += 1
            else:
                okumalar.append(okuma)
            # Puan/yorum hangi kaynaktan gelirse gelsin ürüne işlenir
            if okuma.ekstra.get("puan") is not None:
                urun.puan = okuma.ekstra["puan"]
            if okuma.ekstra.get("yorum") is not None:
                urun.yorum_sayisi = okuma.ekstra["yorum"]

            # Ürün eklenirken ad URL'den türetilmişti (istek içinde ağa
            # çıkmamak için). İlk gerçek başlıkla değiştir — ama SADECE bir
            # kez: kullanıcı adı düzelttiyse sonraki taramalar ezmesin.
            if urun.ad_gecici and okuma.ekstra.get("baslik"):
                urun.ad = okuma.ekstra["baslik"]
                urun.ad_gecici = False

        urun.son_kontrol = utc_simdi()
        sonuc.taranan_urun += 1

        en_iyi = karar.en_iyi_kaynak(okumalar)
        fiyat_okundu_bu_tur = en_iyi is not None and en_iyi.fiyat is not None
        if fiyat_okundu_bu_tur:
            urun.guncel_fiyat = en_iyi.fiyat
            urun.guncel_satici = en_iyi.satici or en_iyi.host
            kaynak_kaydi = next((k for k in urun.sources if k.url == en_iyi.url), None)
            urun.guncel_kaynak_id = kaynak_kaydi.id if kaynak_kaydi else None
            if eski_fiyat != en_iyi.fiyat:
                sonuc.fiyat_degisen += 1

        self.db.flush()

        gecmis = self._okuma_gecmisi(urun.id)
        baglam = (analiz.fiyat_baglami(gecmis, urun.guncel_fiyat)
                  if urun.guncel_fiyat else None)

        # BACKLOG A2: bağlam artık saklanıyor, atılmıyor — ama YALNIZCA bu
        # tur gerçekten taze bir fiyat okunduysa. Okuma başarısız olduğunda
        # `urun.guncel_fiyat` eski (bayat) değerinde kalır; `baglam` o bayat
        # fiyattan yine hesaplanabilir ama bunu yazmak "az önce doğrulandı"
        # yanılsaması verir. Bu yüzden okunamayan turda ALTI SÜTUNA DA
        # dokunulmaz — eski değer olduğu gibi durur.
        #
        # `gecmis_gun`, baglam'ın MIN_GUN (5) eşiğinden BAĞIMSIZ yazılır:
        # A7'nin "3/7 gün — geçmiş biriktiriliyor" göstergesi tam da bu ham
        # gün sayısına ihtiyaç duyuyor; sinyal daha hesaplanamıyor olsa bile
        # ilerlemeyi göstermek gerekiyor.
        if fiyat_okundu_bu_tur:
            urun.gecmis_gun = len(analiz.gunluk_minimumlar(gecmis))
            urun.baglam_ts = utc_simdi()
            if baglam is not None:
                urun.sinyal = baglam.sinyal
                urun.dip90 = baglam.dip90
                urun.medyan90 = baglam.medyan90
                urun.yuzdelik = baglam.yuzdelik

        sonuc.uretilen_uyari += self.uyari_uret(
            urun, eski_fiyat, gecmis, baglam=baglam)
        if en_iyi is None or en_iyi.fiyat is None:
            sonuc.uretilen_uyari += self._bozuk_kaynak_uyar(urun)
        urun.kontrol_araligi_dk = self._sonraki_aralik(urun, gecmis)
        urun.sonraki_kontrol = utc_simdi() + timedelta(
            minutes=urun.kontrol_araligi_dk)
        self.db.commit()

    # ── bozuk kaynak bildirimi ───────────────────────────────────

    def _bozuk_kaynak_uyar(self, urun: Product) -> int:
        """"Bu ürünün fiyatını artık okuyamıyorum" bildirimi.

        NEDEN ÜRÜN SEVİYESİNDE: bir kaynak bozulsa da ürünün başka çalışan
        kaynağı varsa kullanıcının umurunda değildir — doğru fiyatı görmeye
        devam eder. Haber değeri, ürünün HİÇBİR kaynağından fiyat
        gelmemesindedir; ekranda duran fiyat o andan itibaren bayattır ve
        kullanıcı bunu bilmeden eski fiyata güvenir.

        `karar.dogrula` "bozuk" dediğinde durumu zaten işaretliyordu ama bu
        bildirim hiç üretilmiyordu: durum makinesi vardı, çıktısı yoktu.
        """
        bozuklar = [k for k in urun.sources if self._kaynak_bozuk_mu(k)]
        if not bozuklar:
            return 0
        if all(k.bozuk_uyarildi for k in bozuklar):
            return 0                      # bu arıza için zaten haber verildi

        izleyenler = self.db.query(Watch).filter(
            Watch.product_id == urun.id, Watch.aktif.is_(True)).all()

        sebepler = ", ".join(sorted({self._bozuk_sebebi(k) for k in bozuklar}))
        for w in izleyenler:
            self._uyari_ekle(
                w, "KAYNAK_BOZUK", f"⚠️ {urun.ad} — fiyat okunamıyor",
                f"Bu ürünün fiyatı {len(bozuklar)} kaynakta okunamıyor "
                f"({sebepler}). Ekranda görünen fiyat güncel olmayabilir; "
                "mağaza sayfasını kendin kontrol et.")

        # Bayrak, izleyeni olmasa bile düşer: kaynak durumu kullanıcıdan
        # bağımsız bir olgudur.
        for k in bozuklar:
            k.bozuk_uyarildi = True
        return len(izleyenler)

    @staticmethod
    def _kaynak_bozuk_mu(kaynak: Source) -> bool:
        """Geçici arıza mı, kalıcı bozukluk mu?

        `hata_serisi` bu kontrol için tutuluyordu ama HİÇ OKUNMUYORDU —
        artırılıp sıfırlanan, hiçbir karara girmeyen bir sayaçtı.
        """
        return (kaynak.durum == "OLU"
                or (kaynak.hata_serisi or 0) >= BOZUK_HATA_ESIGI
                or (kaynak.asiri_supheli_seri or 0) >= BOZUK_SUPHE_ESIGI)

    @staticmethod
    def _bozuk_sebebi(kaynak: Source) -> str:
        if kaynak.durum == "OLU":
            return "sayfa kaldırılmış"
        if (kaynak.asiri_supheli_seri or 0) >= BOZUK_SUPHE_ESIGI:
            return "okunan fiyat gerçekçi değil"
        return "sayfaya erişilemiyor"

    def tur_calistir(self, limit: int = 100) -> TaramaSonucu:
        """Bir tarama turu. Zamanlayıcı bunu periyodik çağırır."""
        sonuc = TaramaSonucu()
        for urun in self.taranacak_urunler(limit):
            try:
                self.urun_tara(urun, sonuc)
            except Exception as e:
                log.exception("Ürün taranamadı: %s", urun.ad)
                sonuc.hatalar.append(f"{urun.ad}: {type(e).__name__}: {e}")
                self.db.rollback()
        return sonuc

    # ── uyarı üretimi ────────────────────────────────────────────

    def uyari_uret(self, urun: Product, eski_fiyat: float | None,
                   gecmis: list[analiz.Okuma] | None = None,
                   baglam: analiz.Baglam | None = None) -> int:
        """Ürünün fiyatı güncellendikten sonra izleyicilere uyarı üretir.

        Uyarı KİŞİSELDİR: aynı fiyat düşüşü, hedefi 50.000 olan kullanıcı için
        alarm, hedefi 40.000 olan için değildir. Bu yüzden döngü Watch üstünde.

        `gecmis` ve `baglam` dışarıdan verilebilir: `urun_tara` ikisini de
        bir kez hesaplayıp buraya, `_sonraki_aralik`e ve (BACKLOG A2)
        `Product` sütunlarına geçirir. Burada `baglam=None` verilirse (örn.
        bu metot tek başına çağrılırsa) kendi hesabını yapar — eski davranış
        korunur.
        """
        fiyat = urun.guncel_fiyat
        if fiyat is None:
            return 0

        okumalar = self._okuma_gecmisi(urun.id) if gecmis is None else gecmis
        if baglam is None:
            baglam = analiz.fiyat_baglami(okumalar, fiyat)
        dip_kirildi, onceki_dip, _ = analiz.dip_kirildi_mi(okumalar, fiyat)

        uretilen = 0
        for w in self.db.query(Watch).filter(
                Watch.product_id == urun.id, Watch.aktif.is_(True)).all():
            uretilen += self._watch_uyarilari(
                w, urun, fiyat, eski_fiyat, baglam, dip_kirildi, onceki_dip)
        return uretilen

    def _watch_uyarilari(self, w: Watch, urun: Product, fiyat: float,
                         eski_fiyat: float | None, baglam, dip_kirildi: bool,
                         onceki_dip: float | None) -> int:
        simdi = utc_simdi()

        if w.sustur_bitis and w.sustur_bitis > simdi:
            return 0

        acil = bool(w.acil_fiyat and fiyat <= w.acil_fiyat)
        hedefte = bool(w.hedef_fiyat and fiyat <= w.hedef_fiyat)

        # Sessiz saatte normal alarm ERTELENİR (durum güncellenmediği için
        # sabah kendiliğinden tetiklenir); ACİL geçer.
        if not acil and sessiz_saat_mi(SESSIZ_BASLANGIC, SESSIZ_BITIS):
            return 0

        uretilen = 0

        # Bildirim metni TEK YERDEN üretilir (analiz.yorum) — aynı cümle
        # web kartında, bot mesajında ve e-postada birebir aynı çıksın.
        aciklama = analiz.yorum(baglam, fiyat)

        if hedefte and self._hatirlatma_zamani(w, fiyat, simdi, acil):
            onek = "🚨 ACİL — " if acil else "🎯 "
            self._uyari_ekle(
                w, "HEDEF", f"{onek}{urun.ad}",
                f"{tl(fiyat)} (hedef {tl(w.hedef_fiyat)}) · "
                f"{urun.guncel_satici}\n{aciklama}")
            w.son_bildirim_ts = simdi
            w.son_bildirim_fiyat = fiyat
            uretilen += 1

        # Hedefe inmese bile haber değeri olan olay — ürünün ana vaadi bu.
        elif dip_kirildi and onceki_dip and baglam and baglam.gun_sayisi >= 7:
            sure = baglam.en_dusuk_gun
            baslik = (f"📉 {urun.ad} son {sure} günün en düşüğünde"
                      if sure >= 7 else f"📉 {urun.ad} dip kırdı")
            self._uyari_ekle(
                w, "DIP", baslik,
                f"{tl(fiyat)} — önceki dip {tl(onceki_dip)} · "
                f"{urun.guncel_satici}\n{aciklama}")
            uretilen += 1

        if baglam and baglam.sahte_indirim and eski_fiyat and fiyat < eski_fiyat:
            self._uyari_ekle(
                w, "SAHTE_INDIRIM", f"🎭 {urun.ad} — sahte indirim",
                f"Fiyat {tl(eski_fiyat)} → {tl(fiyat)} düştü ama 90 günün "
                f"medyanı {tl(baglam.medyan90)}. Önce şişirilmiş olabilir.")
            uretilen += 1

        uretilen += self._set_uyarisi(w, simdi)
        return uretilen

    def _hatirlatma_zamani(self, w: Watch, fiyat: float, simdi: datetime,
                           acil: bool) -> bool:
        """Mükerrer bildirim freni. ACİL cooldown beklemez ama kendi 3 saatlik
        freni vardır."""
        if w.son_bildirim_ts is None:
            return True
        gecen = simdi - w.son_bildirim_ts
        if acil:
            return gecen > timedelta(hours=3)
        if gecen > timedelta(minutes=HATIRLATMA_DK):
            return True
        # Cooldown içinde olsa da fiyat belirgin şekilde daha düştüyse bildir
        if w.son_bildirim_fiyat:
            return fiyat <= w.son_bildirim_fiyat * (1 - EK_DUSUS_YUZDE / 100)
        return False

    def _set_uyarisi(self, w: Watch, simdi: datetime) -> int:
        """İzlemenin ÜYESİ OLDUĞU setlerin toplamı bütçenin altına indi mi?

        Bir izleme BİRDEN ÇOK sette olabilir (bkz. models.set_uyeleri) ve her
        set kendi bütçesini ayrı takip eder — "PC Toplama" 150.000'in altına
        inerken "Kara Cuma" 200.000'i aşıyor olabilir. Bu yüzden setler tek
        tek değerlendiriliyor ve ikisi de hedefteyse İKİ uyarı gider: farklı
        bütçelerin tutması ayrı bilgidir.

        Bekleme sayacı (`son_bildirim_ts`) SETİN üstünde duruyor, izlemenin
        değil — yani aynı set, farklı ürünleri üzerinden tekrar tekrar
        bildirim yollamıyor.
        """
        return sum(self._tek_set_uyarisi(w, s, simdi) for s in w.setler)

    def _tek_set_uyarisi(self, w: Watch, s, simdi: datetime) -> int:
        """Tek bir set için: toplam bütçenin altında mı, uyarı gitmeli mi?

        Tüm üyelerin fiyatı bilinmiyorsa toplam eksik olacağı için sessiz
        kalınır — yanlış "hedefte!" demektense.
        """
        if not s.hedef_butce:
            return 0
        if s.son_bildirim_ts and simdi - s.son_bildirim_ts < timedelta(
                minutes=HATIRLATMA_DK):
            return 0

        toplam = 0.0
        for uye in s.watches:
            f = uye.kilitli_fiyat if uye.kilitli else (
                uye.product.guncel_fiyat if uye.product else None)
            if f is None:
                return 0                       # eksik üye → hesap güvenilmez
            toplam += f

        if toplam > s.hedef_butce:
            return 0

        parcalar = "\n".join(
            f"  • {u.product.ad}: {kisa_tl(u.product.guncel_fiyat)}"
            for u in s.watches if u.product)
        self._uyari_ekle(
            w, "SET_HEDEF", f"📦🔥 Set hedefte: {s.ad}",
            f"Toplam {tl(toplam)} (bütçe {tl(s.hedef_butce)})\n{parcalar}")
        s.son_bildirim_ts = simdi
        return 1

    def _uyari_ekle(self, w: Watch, tur: str, baslik: str, mesaj: str) -> None:
        self.db.add(Alert(user_id=w.user_id, watch_id=w.id, tur=tur,
                          baslik=baslik, mesaj=mesaj, created_at=utc_simdi()))
        olcumler.uretilen_uyari.labels(tur=tur).inc()
        log.info("Uyarı [%s] kullanıcı=%s: %s", tur, w.user_id, baslik)

    # ── yardımcılar ──────────────────────────────────────────────

    def _okuma_gecmisi(self, product_id: int) -> list[analiz.Okuma]:
        satirlar = (self.db.query(PriceReading.ts, PriceReading.fiyat)
                    .filter(PriceReading.product_id == product_id)
                    .order_by(PriceReading.ts).all())
        return [analiz.Okuma(ts=ts, fiyat=f) for ts, f in satirlar if f]

    def _sonraki_aralik(self, urun: Product,
                        gecmis: list[analiz.Okuma] | None = None) -> int:
        """Uyarlanabilir sıklık — maliyetin kontrol edildiği yer.

        SIK tara: hedefine yakın (birazcık düşse alarm olacak) ya da fiyatı
        oynak ürünler. SEYREK tara: kimsenin hedefine yakın olmayan, aylardır
        kıpırdamayan ürünler.
        """
        fiyat = urun.guncel_fiyat
        if fiyat is None:
            return ARALIK_MIN_DK          # okunamıyorsa sık dene, sorunu gör

        hedefler = [w.hedef_fiyat for w in urun.watches if w.hedef_fiyat]
        if hedefler:
            en_yakin = min(abs(fiyat - h) / fiyat * 100 for h in hedefler)
            if en_yakin <= HEDEFE_YAKIN_YUZDE:
                return ARALIK_MIN_DK

        okumalar = self._okuma_gecmisi(urun.id) if gecmis is None else gecmis
        gunluk = analiz.gunluk_minimumlar(okumalar)
        if len(gunluk) >= 7:
            son_hafta = [v for g, v in gunluk.items()
                         if (tr_bugun() - g).days <= 7]
            if son_hafta and max(son_hafta) > 0:
                oynaklik = (max(son_hafta) - min(son_hafta)) / max(son_hafta)
                if oynaklik < 0.01:       # bir haftadır %1'den az oynamış
                    return ARALIK_MAKS_DK
        return 180                        # varsayılan: 3 saat

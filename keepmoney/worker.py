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

from . import analiz, ayikla, karar, siteler
from .cekici import Cekici
from .fiyat import kisa_tl, tl
from .models import Alert, PriceReading, Product, Source, Watch
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
                 throttle: HostThrottle | None = None):
        self.db = db
        self.cekici = cekici
        self.throttle = throttle or HostThrottle()

    # ── seçim ────────────────────────────────────────────────────

    def taranacak_urunler(self, limit: int = 100,
                          simdi: datetime | None = None) -> list[Product]:
        """Sırası gelen ürünler: hiç taranmamışlar önce, sonra aralığı dolanlar.

        Sıralama `izleyen_sayisi`'na göre: çok izlenen ürün önce taranır.
        Bütçe yetmediğinde en çok kişiyi etkileyen ürün güncel kalır.
        """
        simdi = simdi or utc_simdi()
        urunler = (self.db.query(Product)
                   .order_by(Product.izleyen_sayisi.desc(), Product.id)
                   .all())
        sirasi_gelen = [
            u for u in urunler
            if u.son_kontrol is None
            or simdi - u.son_kontrol >= timedelta(
                minutes=u.kontrol_araligi_dk or ARALIK_MIN_DK)
        ]
        return sirasi_gelen[:limit]

    # ── tek kaynak okuma ─────────────────────────────────────────

    def kaynak_oku(self, kaynak: Source) -> karar.KaynakOkumasi | None:
        """Bir kaynağı çeker, çıkarır, koruma katmanından geçirir.

        None döner = bu tur atlandı (host geri çekilmede). Bu bir HATA DEĞİL:
        kaynağın durumuna dokunulmaz, bir sonraki turda tekrar denenir.
        """
        if self.throttle.ertelenmeli_mi(kaynak.host):
            log.info("%s geri çekilmede, bu tur atlandı", kaynak.host)
            return None

        kural = siteler.kural(kaynak.url)
        cekim = self.cekici.cek(kaynak.url, kural)

        if cekim.engellendi:
            ceza = self.throttle.cezalandir(kaynak.host)
            log.warning("%s bot koruması — %.0f dk geri çekilme",
                        kaynak.host, ceza / 60)
            kaynak.durum = "ENGELLI"
            kaynak.son_kontrol = utc_simdi()
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host,
                                       engelli=True)

        if not cekim.html:
            kaynak.durum = "HATA"
            kaynak.hata_serisi = (kaynak.hata_serisi or 0) + 1
            kaynak.son_kontrol = utc_simdi()
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host)

        c = ayikla.cikar(cekim.html, kural, cekim.http_kodu)

        if c.engelli:
            self.throttle.cezalandir(kaynak.host)
            kaynak.durum = "ENGELLI"
            kaynak.son_kontrol = utc_simdi()
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host,
                                       engelli=True)

        if c.olu:
            kaynak.durum = "OLU"
            kaynak.son_kontrol = utc_simdi()
            log.warning("Ölü kaynak: %s", kaynak.url)
            return karar.KaynakOkumasi(url=kaynak.url, host=kaynak.host, olu=True)

        self.throttle.odullendir(kaynak.host)

        okuma = karar.KaynakOkumasi(
            url=kaynak.url, host=kaynak.host, fiyat=c.fiyat, guven=c.guven,
            satici=kural.get("satici") or kaynak.satici,
            ekstra={"puan": c.puan, "yorum": c.yorum_sayisi, "baslik": c.baslik},
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

        if not guvenilir:
            kaynak.durum = "HATA" if sebep == "bozuk" else "BEKLEMEDE"
            log.info("%s okuması kullanılmadı (%s): %s",
                     kaynak.host, sebep, tl(c.fiyat))
            okuma.ekstra["reddedildi"] = sebep
            return okuma

        kaynak.durum = "OK"
        kaynak.hata_serisi = 0
        kaynak.son_fiyat = c.fiyat
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

        urun.son_kontrol = utc_simdi()
        sonuc.taranan_urun += 1

        en_iyi = karar.en_iyi_kaynak(okumalar)
        if en_iyi is not None and en_iyi.fiyat is not None:
            urun.guncel_fiyat = en_iyi.fiyat
            urun.guncel_satici = en_iyi.satici or en_iyi.host
            kaynak_kaydi = next((k for k in urun.sources if k.url == en_iyi.url), None)
            urun.guncel_kaynak_id = kaynak_kaydi.id if kaynak_kaydi else None
            if eski_fiyat != en_iyi.fiyat:
                sonuc.fiyat_degisen += 1

        self.db.flush()
        sonuc.uretilen_uyari += self.uyari_uret(urun, eski_fiyat)
        urun.kontrol_araligi_dk = self._sonraki_aralik(urun)
        self.db.commit()

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

    def uyari_uret(self, urun: Product, eski_fiyat: float | None) -> int:
        """Ürünün fiyatı güncellendikten sonra izleyicilere uyarı üretir.

        Uyarı KİŞİSELDİR: aynı fiyat düşüşü, hedefi 50.000 olan kullanıcı için
        alarm, hedefi 40.000 olan için değildir. Bu yüzden döngü Watch üstünde.
        """
        fiyat = urun.guncel_fiyat
        if fiyat is None:
            return 0

        okumalar = self._okuma_gecmisi(urun.id)
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

        if hedefte and self._hatirlatma_zamani(w, fiyat, simdi, acil):
            onek = "🚨 ACİL — " if acil else "🎯 "
            mesaj = f"{tl(fiyat)} (hedef {tl(w.hedef_fiyat)}) · {urun.guncel_satici}"
            if baglam:
                mesaj += (f"\n{baglam.emoji} {baglam.etiket} — 90g dip "
                          f"{kisa_tl(baglam.dip90)}, günlerin "
                          f"%{baglam.yuzdelik}'inden ucuz")
                if baglam.sahte_indirim:
                    mesaj += "\n⚠️ Dikkat: bu indirim şişirilmiş fiyattan yapılmış"
            self._uyari_ekle(w, "HEDEF", f"{onek}{urun.ad}", mesaj)
            w.son_bildirim_ts = simdi
            w.son_bildirim_fiyat = fiyat
            uretilen += 1

        # Hedefe inmese bile haber değeri olan olay — ürünün ana vaadi bu.
        elif dip_kirildi and onceki_dip and baglam and baglam.gun_sayisi >= 7:
            self._uyari_ekle(
                w, "DIP", f"📉 {urun.ad} son 30 günün en düşüğünde",
                f"{tl(fiyat)} — önceki dip {tl(onceki_dip)} · {urun.guncel_satici}")
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
        """Setin TOPLAMI bütçenin altına indi mi?

        Ürünün en ayırt edici özelliği: parçalar tek tek hedefte olmasa bile
        toplam fırsatı yakalanır. Tüm üyelerin fiyatı bilinmiyorsa toplam
        eksik olacağı için sessiz kalınır — yanlış "hedefte!" demektense.
        """
        s = w.set
        if s is None or not s.hedef_butce:
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
        log.info("Uyarı [%s] kullanıcı=%s: %s", tur, w.user_id, baslik)

    # ── yardımcılar ──────────────────────────────────────────────

    def _okuma_gecmisi(self, product_id: int) -> list[analiz.Okuma]:
        satirlar = (self.db.query(PriceReading.ts, PriceReading.fiyat)
                    .filter(PriceReading.product_id == product_id)
                    .order_by(PriceReading.ts).all())
        return [analiz.Okuma(ts=ts, fiyat=f) for ts, f in satirlar if f]

    def _sonraki_aralik(self, urun: Product) -> int:
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

        okumalar = self._okuma_gecmisi(urun.id)
        gunluk = analiz.gunluk_minimumlar(okumalar)
        if len(gunluk) >= 7:
            son_hafta = [v for g, v in gunluk.items()
                         if (tr_bugun() - g).days <= 7]
            if son_hafta and max(son_hafta) > 0:
                oynaklik = (max(son_hafta) - min(son_hafta)) / max(son_hafta)
                if oynaklik < 0.01:       # bir haftadır %1'den az oynamış
                    return ARALIK_MAKS_DK
        return 180                        # varsayılan: 3 saat

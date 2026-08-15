"""Fiyat zekâsı — "bu iyi bir fiyat mı?" sorusunun cevabı.

Ürünün kalbi burasıdır. Keepa'nın Türkiye'de karşılığı olmayan işlevi tam
olarak budur: fiyatı göstermek değil, fiyatı BAĞLAMA oturtmak.

Tasarım kararı — hepsi SAF fonksiyon: girdi bir okuma listesi, çıktı bir
dataclass. Veritabanı, ORM, ağ yok. Sebebi:
  • test edilebilir (kurulum gerektirmeden, gerçek senaryolarla),
  • hem tarama worker'ı hem API hem bot aynı kodu çağırır — üç yerde üç
    farklı "dip" tanımı oluşamaz,
  • depolama değişse (SQLite → Postgres) bu katman etkilenmez.

GÜNLÜK MİNİMUM İLKESİ: tüm hesaplar ham okumalar üzerinden değil, GÜNLÜK
MİNİMUMLAR üzerinden yapılır. Sık taranan bir ürün günde 48 okuma, seyrek
taranan 2 okuma üretir; ham listede ilki medyanı domine eder. Gün başına tek
değer bu çarpıklığı ortadan kaldırır.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta

# Bağlam üretmek için gereken minimum gün sayısı. Altında kalan veriyle
# "dip bölgesi" demek kullanıcıyı yanıltır — 2 günlük veride her fiyat diptir.
MIN_GUN = 5

# Güncel fiyat, 90 günün dibine bu oran kadar yakınsa "dip bölgesi" sayılır.
# %2'lik pay bilinçli: kuruş farkıyla dibi ıskalayan fiyat pratikte diptir.
DIP_TOLERANS = 1.02

# Sahte indirim eşiği: medyandan bu kadar pahalıysa "indirim" gerçek değildir.
SAHTE_INDIRIM_ESIGI = 1.10


@dataclass(frozen=True)
class Okuma:
    """Tek bir fiyat gözlemi."""
    ts: datetime
    fiyat: float


@dataclass(frozen=True)
class Baglam:
    """'Bu iyi bir fiyat mı?' sorusunun yapılandırılmış cevabı."""
    sinyal: str                 # "dip" | "ucuz" | "pahali"
    etiket: str                 # kullanıcıya gösterilecek metin
    dip90: float
    medyan90: float
    yuzdelik: int               # günlerin yüzde kaçından ucuz (yüksek = iyi)
    tum_zamanlar_dibi: float
    tum_zamanlar_dibi_tarih: date
    gun_sayisi: int
    sahte_indirim: bool
    trend_yonu: str             # "dusuyor" | "yukseliyor" | "sabit"
    trend_gucu: float           # 0.0 - 1.0

    @property
    def emoji(self) -> str:
        return {"dip": "🟢", "ucuz": "🟡", "pahali": "🔴"}[self.sinyal]

    @property
    def iyi_firsat(self) -> bool:
        """Alım tavsiyesine dönüşebilecek durum: dip bölgesinde VE sahte
        indirim değil. Nihai kararı çağıran verir; burası sadece sinyal."""
        return self.sinyal == "dip" and not self.sahte_indirim


def gunluk_minimumlar(okumalar: list[Okuma]) -> dict[date, float]:
    """Her gün için o günün EN DÜŞÜK okuması. Tüm analizin girdisi budur."""
    out: dict[date, float] = {}
    for o in okumalar:
        if o.fiyat is None or o.fiyat <= 0:
            continue
        g = o.ts.date()
        mevcut = out.get(g)
        if mevcut is None or o.fiyat < mevcut:
            out[g] = o.fiyat
    return out


def _pencere(gunluk: dict[date, float], gun: int, bugun: date) -> list[float]:
    sinir = bugun - timedelta(days=gun)
    return [v for g, v in gunluk.items() if g >= sinir]


def trend(gunluk: dict[date, float], bugun: date | None = None) -> tuple[str, float]:
    """Kısa/uzun vadeli hareketli ortalama kesişimiyle yön ve güç.

    Dönen güç 0-1 arasıdır; %3'lük sapma eşik kabul edilir (altı "sabit"),
    %10'luk sapma tam güç sayılır.
    """
    bugun = bugun or date.today()
    seri = [v for _, v in sorted(gunluk.items())]
    if len(seri) < 2:
        return "sabit", 0.0

    kisa = statistics.mean(seri[-min(3, len(seri)):])
    uzun = statistics.mean(seri[-min(7, len(seri)):])
    if uzun <= 0:
        return "sabit", 0.0

    oran = (kisa - uzun) / uzun
    if oran < -0.03:
        yon = "dusuyor"
    elif oran > 0.03:
        yon = "yukseliyor"
    else:
        yon = "sabit"
    return yon, round(min(1.0, abs(oran) * 10), 2)


def sahte_indirim_mi(guncel: float, gunluk: dict[date, float],
                     bugun: date | None = None) -> bool:
    """Bull-trap: fiyat önce şişirilip sonra 'indirildi' ama hâlâ normalin
    üstünde.

    Şart İKİ TARAFLIDIR — sadece "düştü" yetmez, sadece "pahalı" da yetmez:
      1) güncel fiyat 90 günün medyanından %10+ pahalı, VE
      2) son 14 gün içinde güncelden DAHA YÜKSEK bir fiyat görülmüş
         (yani gerçekten bir "indirim" anlatısı var).

    Tek taraflı kontrol (sadece 'önceki fiyattan düşük') normal fiyat
    dalgalanmasını da tuzak sayıyordu; iki şartın kesişimi çok daha az
    yanlış pozitif üretiyor.
    """
    bugun = bugun or date.today()
    doksan = _pencere(gunluk, 90, bugun)
    if len(doksan) < MIN_GUN or guncel <= 0:
        return False

    medyan = statistics.median(doksan)
    if guncel <= medyan * SAHTE_INDIRIM_ESIGI:
        return False

    son_iki_hafta = _pencere(gunluk, 14, bugun)
    return any(v > guncel for v in son_iki_hafta)


def fiyat_baglami(okumalar: list[Okuma], guncel: float,
                  bugun: date | None = None) -> Baglam | None:
    """Ana giriş noktası. Yeterli veri yoksa None döner — yanıltıcı bağlam
    sunmaktansa hiç sunmamak doğrudur."""
    if not okumalar or not guncel or guncel <= 0:
        return None

    bugun = bugun or date.today()
    gunluk = gunluk_minimumlar(okumalar)
    doksan = _pencere(gunluk, 90, bugun)
    if len(doksan) < MIN_GUN:
        return None

    dip90 = min(doksan)
    medyan90 = statistics.median(doksan)

    # Yüzdelik: 90 günün yüzde kaçında bugünkünden PAHALIYDI?
    # Yüksek değer = bugün ucuz bir gün.
    yuzdelik = round(sum(1 for v in doksan if v >= guncel) / len(doksan) * 100)

    tum_dip_gun = min(gunluk, key=lambda g: gunluk[g])

    if guncel <= dip90 * DIP_TOLERANS:
        sinyal, etiket = "dip", "dip bölgesi"
    elif guncel <= medyan90:
        sinyal, etiket = "ucuz", "ortalamanın altı"
    else:
        sinyal, etiket = "pahali", "pahalı dönem"

    yon, guc = trend(gunluk, bugun)

    return Baglam(
        sinyal=sinyal,
        etiket=etiket,
        dip90=dip90,
        medyan90=medyan90,
        yuzdelik=yuzdelik,
        tum_zamanlar_dibi=gunluk[tum_dip_gun],
        tum_zamanlar_dibi_tarih=tum_dip_gun,
        gun_sayisi=len(doksan),
        sahte_indirim=sahte_indirim_mi(guncel, gunluk, bugun),
        trend_yonu=yon,
        trend_gucu=guc,
    )


def dip_kirildi_mi(okumalar: list[Okuma], guncel: float, gun: int = 30,
                   bugun: date | None = None) -> tuple[bool, float | None, int]:
    """Hedef fiyata inmese bile haber değeri olan olay: 'son N günün dibi'.

    BUGÜNÜ HARİÇ TUTAR — bugünkü okuma dibin kendisi olduğu için, dahil
    edilirse hiçbir zaman kırılmış sayılmaz.

    Dönüş: (kırıldı_mı, önceki_dip, kaç_günlük_veri)
    """
    bugun = bugun or date.today()
    gunluk = gunluk_minimumlar(okumalar)
    gunluk.pop(bugun, None)

    onceki = _pencere(gunluk, gun, bugun)
    if not onceki:
        return False, None, 0

    dip = min(onceki)
    return (guncel < dip), dip, len(onceki)

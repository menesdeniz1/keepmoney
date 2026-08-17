"""Koruma katmanı — bir okumaya güvenilir mi, alarm gitmeli mi?

Bu modüldeki her kural GERÇEK bir arıza vakasından doğdu (`tracker` projesinde
aylarca üretimde çalışırken yaşananlar). Kuralları "temizlemeden" önce
docstring'lerdeki vakaları oku: her biri sessizce yanlış alarm göndermiş bir
senaryonun kapatılmasıdır.

Temel ilke: YANLIŞ ALARM, KAÇIRILMIŞ FIRSATTAN PAHALIDIR. Kullanıcı bir kez
"5.000 TL'ye düştü!" bildirimiyle heyecanlanıp sayfada 50.000 TL görürse
ürüne bir daha güvenmez.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KaynakOkumasi:
    """Tek bir kaynaktan (mağaza URL'i) yapılan tek okuma."""
    url: str
    host: str
    fiyat: float | None = None
    guven: str = "yok"          # "json-ld" | "secici" | "meta" | "regex" | "yok"
    satici: str | None = None
    stokta: bool | None = None
    engelli: bool = False       # bot koruması/captcha
    olu: bool = False           # 404/410 — sayfa kaldırılmış
    ekstra: dict = field(default_factory=dict)
    # Toplayıcı sayfalarından gelen pazar derinliği (bkz. pazar_aykiri).
    satici_sayisi: int | None = None
    ikinci_fiyat: float | None = None

    @property
    def dusuk_guven(self) -> bool:
        """Gövde regex'i son çaredir: sayfadaki ilk '12.345,67 TL' kalıbını
        alır ve bu pekâlâ önerilen/sponsorlu bir ürünün fiyatı olabilir."""
        return self.guven == "regex"


@dataclass
class IzlemeDurumu:
    """Bir izlemenin (Watch) kalıcı durumu — mükerrer bildirim engelleme."""
    son_iyi_fiyat: float | None = None
    bekleyen_fiyat: float | None = None      # 2-okuma doğrulaması bekleyen değer
    asiri_supheli_seri: int = 0
    asiri_supheli_uyarildi: bool = False


def alarm_gerekli(hedef: float | None, okuma: KaynakOkumasi) -> bool:
    """Fiyat hedefin altına indi mi? Hedef yoksa alarm yok."""
    if not hedef or okuma.fiyat is None:
        return False
    return okuma.fiyat <= float(hedef)


# Pazar aykırılığı eşikleri.
#   ŞÜPHELİ: ikinci en ucuz, en ucuzun 1,5 katından fazla. Gerçek kampanyada
#   bir satıcı diğerlerinden %20-30 ucuz olabilir; %50 fark olağandışıdır ama
#   imkânsız değil — ikinci okumayla doğrulanır.
#   BOZUK: ikinci en ucuz, en ucuzun 3 katından fazla. Bu artık kampanya
#   değil, hatalı girilmiş bir liste kaydıdır.
PAZAR_AYKIRI_ORAN = 1.5
PAZAR_BOZUK_ORAN = 3.0


def pazar_aykiri(okuma: KaynakOkumasi, oran: float = PAZAR_AYKIRI_ORAN) -> bool:
    """Toplayıcıda en ucuz fiyat, ikinci en ucuzdan ORANTISIZ ucuz mu?

    NEDEN AYRI BİR ÖLÇÜT: bu modüldeki diğer bütün kontroller SON İYİ FİYATA
    bakıyor. Yeni eklenen bir üründe öyle bir fiyat YOKTUR — ilk okumada gelen
    absürt bir değeri hiçbir kural yakalayamaz. Üstelik o değer geçmişin
    başlangıcı olur ve sonraki tüm "dip" hesaplarını kirletir.

    Toplayıcı sayfası bu boşluğu dolduruyor: aynı ürünü satan onlarca satıcı
    tek sayfada. "En ucuz 4.000 TL ama ikincisi 52.000 TL" tablosu, geçmiş
    olmadan da o 4.000'in gerçek olmadığını söyler — referans pazarın kendisi.

    TEK SATICI TEK BAŞINA ŞÜPHE SEBEBİ DEĞİLDİR: birçok ürünü gerçekten tek
    mağaza satıyor. Sinyal, kıyaslanacak ikinci bir fiyatın VARLIĞINDA ve
    aradaki farkın büyüklüğünde.
    """
    fp, ikinci = okuma.fiyat, okuma.ikinci_fiyat
    if fp is None or ikinci is None or fp <= 0:
        return False
    return ikinci > fp * oran


def fiyat_supheli(okuma: KaynakOkumasi, durum: IzlemeDurumu,
                  hedef: float | None = None) -> bool:
    """Parse hatası ihtimali — bildirimden önce ikinci okumayla doğrula.

    Beş tetikleyici (sonuncusu geçmişi olmayan ürünler için):
      1. Doğrulanmamış regex okuması (düşük güven kaynağı),
      2. Hedefin yarısından da ucuz (gerçek olamayacak kadar iyi),
      3. Son bilinen fiyattan %40+ ani düşüş,
      4. Son bilinen fiyattan %80+ ani YÜKSELİŞ,
      5. Toplayıcıda ikinci en ucuzdan orantısız ucuz (bkz. `pazar_aykiri`).

    (5) diğer dördünün göremediği durumu kapatır: GEÇMİŞİ OLMAYAN ürün. İlk
    okumada 1-4 numaralı ölçütlerin hepsi `son_iyi` yokluğunda sessizdir.

    (4) simetri için değil, gerçek bir vakadan: bir karşılaştırma sitesinin
    KENDİ sayfasında (json-ld — yüksek güven sayılan kaynak) tek bir pazaryeri
    satıcısı ürünü gerçek değerinin 2-9 katı fiyatla listelemişti; site bunu
    "en ucuz" diye gösterdi. Kaynak güvenilir OLDUĞU için eskiden hiç
    yakalanmıyordu.

    Not: regex okuması son iyi fiyata ±%5 yakınsa temiz sayılır — geçmiş bu
    okumayı doğruluyor demektir. Aksi halde sürekli regex'e düşen ürünler her
    turda gereksiz yere yeniden doğrulanırdı.
    """
    fp = okuma.fiyat
    if fp is None:
        return False

    son_iyi = durum.son_iyi_fiyat

    if okuma.dusuk_guven and (not son_iyi or abs(fp - son_iyi) > son_iyi * 0.05):
        return True

    if hedef and fp < float(hedef) * 0.5:
        return True

    if son_iyi:
        if fp < son_iyi * 0.6:
            return True
        if fp > son_iyi * 1.8:
            return True

    return pazar_aykiri(okuma)


def asiri_supheli(okuma: KaynakOkumasi, durum: IzlemeDurumu,
                  hedef: float | None = None) -> bool:
    """Kaynağın YAPISAL olarak bozuk olduğunu gösteren aşırı sapma.

    Bu durumda normal 2-okuma tutarlılığı GEÇERSİZ sayılır. Sebep kritik:
    bozuk bir kaynak, DÜZELENE KADAR kendisiyle saatlerce/günlerce "tutarlı"
    kalabilir — iki ardışık okumanın örtüşmesi doğruluk kanıtı değildir.

    İki gerçek vaka:
      • DÜŞÜK: bir mağaza linki genel 'Hard Disk' kategori sayfasına düşmüştü;
        regex oradan hedefin (12.500 TL) çok altında sabit 1.260 TL okuyordu.
        Sayfa hep aynı yanlış değeri döndürdüğü için "tutarlı" sayılıp iki kez
        yanlış alarm gönderildi.
      • YÜKSEK: güvenilir json-ld kaynağından, son bilinen fiyatın 11 katı.

    Bu durumdan çıkış: ya güvenilir bir kaynaktan makul okuma gelir, ya da
    fiyat normal aralığa döner. Otomatik "kendini onaylama" yolu yoktur.
    """
    fp = okuma.fiyat
    if fp is None:
        return False

    # DÜŞÜK uç: sadece düşük güvenli kaynakta. Aynı değer güvenilir kaynaktan
    # gelirse gerçek bir çöküş olabilir — normal 2-okuma yolu işlesin.
    if okuma.dusuk_guven and hedef and fp < float(hedef) * 0.2:
        return True

    # PAZAR: ikinci en ucuz, en ucuzun 3 katından fazlaysa bu bir kampanya
    # değil, hatalı girilmiş bir liste kaydıdır. Geçmiş GEREKTİRMEZ — yeni
    # eklenen üründe de çalışan tek "bozuk" ölçütü budur. İkinci okuma da
    # aynı hatalı kaydı okuyacağı için 2-okuma yolu burada işe yaramaz.
    if pazar_aykiri(okuma, PAZAR_BOZUK_ORAN):
        return True

    # YÜKSEK uç: kaynağın güveni ne olursa olsun, son bilinen fiyatın 3 katı
    # bir perakende fiyatı gerçek değildir.
    return bool(durum.son_iyi_fiyat and fp > durum.son_iyi_fiyat * 3)


def dogrula(okuma: KaynakOkumasi, durum: IzlemeDurumu,
            hedef: float | None = None) -> tuple[bool, str]:
    """Koruma katmanının tek giriş noktası. Durumu YERİNDE günceller.

    Dönüş: (güvenilir_mi, sebep)
      • (True,  "temiz")     → fiyat kullanılabilir, geçmişe yazılabilir
      • (False, "beklemede") → ikinci okuma gerekli, yakında tekrar dene
      • (False, "bozuk")     → kaynak muhtemelen kırık, kullanıcıya haber ver
    """
    fp = okuma.fiyat
    if fp is None:
        return False, "fiyat-yok"

    if asiri_supheli(okuma, durum, hedef):
        durum.bekleyen_fiyat = None          # 2-okuma onayı bu vakada uygulanmaz
        durum.asiri_supheli_seri += 1
        return False, "bozuk"

    if fiyat_supheli(okuma, durum, hedef):
        bekleyen = durum.bekleyen_fiyat
        # İkinci okuma öncekiyle ±%2 tutarlıysa fiyat gerçek kabul edilir.
        if bekleyen and abs(bekleyen - fp) <= fp * 0.02:
            durum.bekleyen_fiyat = None
            durum.asiri_supheli_seri = 0
            durum.asiri_supheli_uyarildi = False
            return True, "ikinci-okuma-dogruladi"
        durum.bekleyen_fiyat = fp
        return False, "beklemede"

    durum.bekleyen_fiyat = None
    durum.asiri_supheli_seri = 0
    durum.asiri_supheli_uyarildi = False
    return True, "temiz"


def en_iyi_kaynak(okumalar: list[KaynakOkumasi]) -> KaynakOkumasi | None:
    """Birden çok kaynak arasından bildirime esas olanı seçer: EN UCUZ olan.

    Çoklu kaynak kurgusunun kalbi — aynı ürünü 4 mağazadan izleyip en ucuzunu
    bildirmek, kullanıcının site site gezmesini tamamen ortadan kaldırır.
    Engelli ve ölü kaynaklar elenir; hiç fiyatlı kaynak yoksa en azından
    ilk aday döner (stok/durum bilgisi taşıyor olabilir).
    """
    adaylar = [o for o in okumalar if not o.engelli and not o.olu]
    if not adaylar:
        return None
    fiyatlilar = [o for o in adaylar if o.fiyat is not None]
    if fiyatlilar:
        return min(fiyatlilar, key=lambda o: o.fiyat)
    return adaylar[0]

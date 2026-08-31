"""CSV dışa aktarma (BACKLOG H1) — Türkçe Excel'in okuyabildiği biçimde.

Bu dosya HTTP bilmez: içerik üretir, rota katmanı paketler. Böylece
"Excel'de doğru açılıyor mu" sorusu tarayıcı açmadan, düz birim testiyle
sınanabiliyor.

ÜÇ BİÇİM KARARI VE HER BİRİNİN SEBEBİ — üçü de gerçek arıza:

  1. AYRAÇ NOKTALI VİRGÜL. Excel liste ayracını işletim sisteminin bölge
     ayarından alır; Türkçe Windows'ta bu noktalı virgüldür. Virgülle
     ayrılmış bir dosya Türkçe Excel'de TEK KOLONA düşer ve kullanıcı bunu
     "dosya bozuk" diye okur.
  2. ONDALIK VİRGÜL. `1639.90` Türkçe Excel için sayı değil METİNDİR;
     kolon toplanmaz, sıralanmaz, grafiklenmez. `1639,90` sayı olur.
  3. UTF-8 BOM İLE. BOM'suz bir `.csv`yi Excel Windows-1254 sanar ve
     "Kulaklık" → "KulaklÄ±k" olur. Üç bayt; teşhisi yarım gün.

Bu üçü BİRLİKTE gerekir: ikisi doğru, biri yanlış olan dosya yine bozuk
görünür.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import PriceReading, Product, Source, Watch
from ..zaman import tr_bugun, tr_saat
from . import urun as urun_svc

AYRAC = ";"
# Kaçış dizisiyle yazıldı, karakterin kendisiyle DEĞİL: BOM görünmez bir
# karakterdir ve kaynak dosyada tırnak içinde BOŞ durur — sonraki bir
# düzenlemede fark edilmeden silinebilir. O gün arıza "Excel'de Türkçe
# harfler bozuk" olarak döner ve koddaki hiçbir değişiklikle
# açıklanamaz görünür.
BOM = "\ufeff"
# Excel'in kendi ürettiği CSV de CRLF kullanır (RFC 4180). Tek `\n` çoğu
# okuyucuda çalışır ama eski Excel sürümlerinde son kolonu bir sonraki
# satıra taşıyabiliyor.
SATIR_SONU = "\r\n"

# Metin hücresi bu karakterlerden biriyle başlıyorsa Excel onu FORMÜL
# sanar. `=1+1` hesaplanır, `=HYPERLINK(...)`/`=cmd|...` ise gerçek bir
# saldırı yüzeyidir (CSV/formül enjeksiyonu). Bizim metin hücrelerimiz
# ÜRÜN SAYFALARINDAN kazınıyor — yani içeriği bize yabancı bir site
# belirliyor; "bizim veri, güvenli" varsayımı burada geçmez.
_FORMUL_BASLANGICI = ("=", "+", "-", "@", "\t", "\r")

# Rozetin metniyle BİREBİR aynı (arayuz/src/bilesenler/SinyalRozeti.tsx).
# Ham `dip`/`ucuz`/`pahali` değerleri iç kodlardır; kullanıcı ekranda
# hiçbir yerde onları görmüyor, CSV'de de görmemeli.
SINYAL_METNI = {
    "dip": "90 günün dibi",
    "ucuz": "ucuz dönem",
    "pahali": "pahalı dönem",
}

LISTE_BASLIKLARI = [
    "Ürün", "Mağaza", "Güncel Fiyat (TL)", "Hedef Fiyat (TL)",
    "Acil Fiyat (TL)", "Sinyal", "90 Gün Dip (TL)", "90 Gün Medyan (TL)",
    "Yüzdelik", "Geçmiş (gün)", "Son Kontrol", "Durum", "Link",
]

GECMIS_BASLIKLARI = [
    "Ürün", "Mağaza", "Site", "Tarih", "Saat", "Fiyat (TL)", "Stokta",
]


# ── Hücre biçimleyicileri ────────────────────────────────────────

def _metin(deger: object) -> str:
    """Metin hücresi — formül enjeksiyonuna karşı kalkanlı.

    Baştaki tek tırnak Excel'in "bu hücre metindir" işaretidir: hücrede
    GÖRÜNMEZ ama formül yorumlamasını kapatır. Değeri kırpmak ya da
    karakteri atmak yerine bu seçildi — kullanıcının verisi bozulmadan
    kalsın (`-5 TL indirim` diye bir ürün adı gerçekten olabilir).
    """
    s = "" if deger is None else str(deger)
    return "'" + s if s[:1] in _FORMUL_BASLANGICI else s


def _sayi(deger: float | None, basamak: int = 2) -> str:
    """Ondalık ayracı VİRGÜL. Boş değer boş hücre — `0` DEĞİL: fiyatı
    okunamamış ürünün fiyatını sıfır yazmak, ortalamayı sessizce bozar."""
    if deger is None:
        return ""
    return f"{deger:.{basamak}f}".replace(".", ",")


def _tam(deger: int | None) -> str:
    return "" if deger is None else str(deger)


def _tarih(dt: datetime | None) -> str:
    """gg.aa.yyyy — Türkçe Excel'in tarih olarak TANIDIĞI biçim."""
    return "" if dt is None else tr_saat(dt).strftime("%d.%m.%Y")


def _saat(dt: datetime | None) -> str:
    return "" if dt is None else tr_saat(dt).strftime("%H:%M")


def _tarih_saat(dt: datetime | None) -> str:
    return "" if dt is None else f"{_tarih(dt)} {_saat(dt)}"


def csv_metni(basliklar: list[str], satirlar: list[list[str]]) -> str:
    """Başlık + satırları tek bir CSV metnine çevirir (BOM dahil).

    `csv.writer` elle birleştirmeye tercih edildi: içinde noktalı virgül ya
    da tırnak geçen bir ürün adını (yeterince oluyor) tırnaklama işini
    standart kütüphane doğru yapar, elle yazılan `AYRAC.join(...)` yapmaz —
    ve o hata dosyanın TAMAMINI bir kolon kaydırır.
    """
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=AYRAC, lineterminator=SATIR_SONU,
                        quoting=csv.QUOTE_MINIMAL)
    yazici.writerow(basliklar)
    yazici.writerows(satirlar)
    return BOM + tampon.getvalue()


# ── İçerik üreticileri ───────────────────────────────────────────

def liste_csv(izlemeler: list[Watch]) -> str:
    """Takip listesinin tamamı — panelde görünen kolonlar.

    ÇAĞIRAN SORUMLU: liste `izleme.izlemeler(db, k, kaynaklarla=True)` ile
    gelmelidir; `Link` kolonu `product.sources`a bakıyor ve tembel
    yüklemede ürün başına bir sorgu daha açılır.
    """
    satirlar = []
    for w in izlemeler:
        u = w.product
        kaynak = urun_svc.en_ucuz_kaynak(u)
        satirlar.append([
            _metin(u.ad),
            _metin(u.guncel_satici),
            _sayi(u.guncel_fiyat),
            _sayi(w.hedef_fiyat),
            _sayi(w.acil_fiyat),
            # Bilinmeyen bir sinyal kodu BOŞ değil, HAM hâliyle yazılır:
            # `analiz`e yeni bir sinyal eklenip bu sözlük güncellenmezse
            # kolon sessizce boşalacaktı — "veri yok" ile "çevirisi yok"
            # aynı görünürdü.
            _metin(SINYAL_METNI.get(u.sinyal, u.sinyal) if u.sinyal else ""),
            _sayi(u.dip90),
            _sayi(u.medyan90),
            _tam(u.yuzdelik),
            _tam(u.gecmis_gun),
            _tarih_saat(u.son_kontrol),
            "aktif" if w.aktif else "duraklatıldı",
            # Ortaklık çıkış linki DEĞİL, ham mağaza adresi: bu dosya
            # kullanıcının kendi verisi. Yönlendirici bir adres yıllar
            # sonra ölür ve elde gerçek adresi olmayan bir arşiv kalır.
            _metin(kaynak.url if kaynak else ""),
        ])
    return csv_metni(LISTE_BASLIKLARI, satirlar)


def gecmis_csv(db: Session, urun: Product) -> str:
    """Tek ürünün fiyat geçmişi — HAM OKUMALAR, gün özeti değil.

    Grafik gün başına tek nokta gösteriyor (MIMARI K4) ama dışa aktarma
    onu tekrarlamıyor: günlük özet ham veriden Excel'de bir özet tabloyla
    üretilebilir, TERSİ ÜRETİLEMEZ. Dışa aktarmada bilgi kaybetmek, iki
    biçimden yanlış olanıdır.

    STOKTA_YOK satırları da geliyor (B4'ten beri `fiyat=None,
    stokta_var=False` olarak yazılıyorlar): fiyat hücresi BOŞ, `Stokta`
    hücresi `hayır`. "O gün hiç taranmadı" ile "tarandı, ürün yoktu"
    farkı grafikte gösteriliyor; CSV'de de kaybolmamalı.
    """
    satirlar = (db.query(PriceReading.ts, PriceReading.fiyat,
                         PriceReading.stokta_var, Source.satici, Source.host)
                .join(Source, Source.id == PriceReading.source_id)
                .filter(PriceReading.product_id == urun.id)
                .order_by(PriceReading.ts)
                .all())
    return csv_metni(GECMIS_BASLIKLARI, [
        [
            _metin(urun.ad),
            # Satıcı adı yoksa alan adı: bu kolon boş kalırsa Excel'de
            # mağazaya göre özet tablo kurulamaz.
            _metin(satici or host),
            _metin(host),
            _tarih(ts),
            _saat(ts),
            _sayi(fiyat),
            "evet" if stokta_var else "hayır",
        ]
        for ts, fiyat, stokta_var, satici, host in satirlar
    ])


# ── Dosya adları ─────────────────────────────────────────────────

# Türkçe harflerin ASCII karşılığı. `unicodedata` ile ayrıştırma `ı` ve `ğ`
# için doğru sonuç vermiyor (`ı`nın ASCII ayrışması yok, harf tamamen
# düşerdi) — küçük ve açık bir tablo daha dürüst.
_ASCII_HARFLER = str.maketrans({
    "ç": "c", "Ç": "C", "ğ": "g", "Ğ": "G", "ı": "i", "İ": "I",
    "ö": "o", "Ö": "O", "ş": "s", "Ş": "S", "ü": "u", "Ü": "U",
})


def slug(metin: str, azami: int = 40) -> str:
    """Dosya adı için ASCII, kısa, güvenli ad.

    ASCII olması ZORUNLU: dosya adı `Content-Disposition` başlığına
    yazılıyor ve HTTP başlıkları ASCII taşır. Harf/rakam dışındaki her
    şeyin tireye dönmesi ayrıca tırnak/satır sonu enjeksiyonu ihtimalini
    de kapatıyor — başlığa kullanıcı verisi giriyor.
    """
    d = metin.translate(_ASCII_HARFLER)
    d = "".join(c if c.isascii() and c.isalnum() else "-" for c in d)
    d = re.sub("-+", "-", d).strip("-").lower()
    return d[:azami].strip("-") or "urun"


def liste_dosya_adi() -> str:
    return f"keepmoney-takip-listem-{tr_bugun().isoformat()}.csv"


def gecmis_dosya_adi(urun: Product) -> str:
    """Ürün adı dosya adına giriyor çünkü aksi hâlde her indirme
    `gecmis.csv` olurdu: üç ürün dışa aktaran kullanıcının indirilenler
    klasöründe `gecmis.csv`, `gecmis (1).csv`, `gecmis (2).csv` kalır ve
    hangisinin hangi ürün olduğu dosyayı açmadan anlaşılmaz."""
    return f"keepmoney-{slug(urun.ad)}-gecmis-{tr_bugun().isoformat()}.csv"

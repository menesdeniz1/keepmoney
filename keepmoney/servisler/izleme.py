"""İzleme (Watch) use-case'leri — kullanıcının ürün takip etmesi.

Bu katmanın işi: HTTP'yi bilmeden, iş kurallarını uygulamak. Rotalar buradan
sadece fonksiyon çağırır; buradaki hiçbir şey `fastapi` import etmez. Aynı
fonksiyonları Telegram botu da çağıracak — kural iki yerde yazılmasın diye.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlparse, urlunparse

from sqlalchemy.orm import Session

from .. import siteler
from ..ayarlar import ayarlar
from ..models import Product, Source, User, Watch, WatchSet
from ..zaman import utc_simdi

# URL'den atılacak takip parametreleri. Aynı ürünün linki farklı kampanya
# etiketleriyle geldiğinde AYNI kaynağa düşsün — yoksa aynı sayfa 5 kez
# taranır ve fiyat geçmişi 5'e bölünür.
COP_PARAMETRELER = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "referrer", "sellerId", "merchantId",
    "boutiqueId", "adjust_t", "adjust_tracker",
}


class IzlemeHatasi(Exception):
    """İş kuralı ihlali. Rota katmanı bunu 400'e çevirir."""


class KotaDoldu(IzlemeHatasi):
    pass


def url_normalize(ham: str) -> str:
    """Takip parametrelerini atar, şemayı ve host'u normalize eder.

    Kanonik URL, küresel ürün modelinin can damarı: iki kullanıcı aynı ürünü
    farklı linklerle eklediğinde aynı `Source` satırına düşmeliler.
    """
    p = urlparse(ham.strip())
    host = (p.netloc or "").lower().removeprefix("www.")
    sorgu = "&".join(
        parca for parca in (p.query or "").split("&")
        if parca and parca.split("=")[0] not in COP_PARAMETRELER
    )
    yol = p.path.rstrip("/") or "/"
    return urlunparse(("https", host, yol, "", sorgu, ""))


def _urun_adi_uret(url: str) -> str:
    """Ağa çıkmadan, URL'den okunabilir geçici ad. Gerçek başlık ilk taramada
    gelir — kullanıcıyı istek içinde 10 saniye bekletmeye değmez."""
    p = urlparse(url)
    parcalar = [s for s in p.path.split("/") if s]
    ham = parcalar[-1] if parcalar else p.netloc
    for ek in (".html", ".htm", ".php", ".aspx"):
        ham = ham.removesuffix(ek)
    ad = ham.replace("-", " ").replace("_", " ").strip()
    # Akakçe tarzı ",1234567" son ekini at
    ad = ad.split(",")[0].strip()
    return (ad[:80] or p.netloc) if ad else p.netloc


def kaynak_bul_veya_olustur(db: Session, url: str) -> Source:
    """URL'yi küresel kaynak tablosuna bağlar; yoksa ürünüyle birlikte kurar.

    Ürün paylaşımının gerçekleştiği yer burası: aynı linki ekleyen ikinci
    kullanıcı yeni satır yaratmaz, mevcut ürüne bağlanır ve tüm fiyat
    geçmişini anında görür.
    """
    kanonik = url_normalize(url)
    kaynak = db.query(Source).filter(Source.url == kanonik).one_or_none()
    if kaynak is not None:
        return kaynak

    host = siteler.host_cikar(kanonik)
    kural = siteler.kural(kanonik)

    urun = Product(ad=_urun_adi_uret(kanonik), ad_gecici=True, izleyen_sayisi=0)
    db.add(urun)
    db.flush()

    kaynak = Source(
        product_id=urun.id, url=kanonik, host=host,
        satici=kural.get("satici"), toplayici=bool(kural.get("toplayici")),
    )
    db.add(kaynak)
    db.flush()
    return kaynak


def izlemeler(db: Session, kullanici: User) -> list[Watch]:
    return (db.query(Watch)
            .filter(Watch.user_id == kullanici.id)
            .order_by(Watch.created_at.desc())
            .all())


def izleme_getir(db: Session, kullanici: User, izleme_id: int) -> Watch:
    w = (db.query(Watch)
         .filter(Watch.id == izleme_id, Watch.user_id == kullanici.id)
         .one_or_none())
    if w is None:
        raise IzlemeHatasi("İzleme bulunamadı")
    return w


def ekle(db: Session, kullanici: User, url: str,
         hedef_fiyat: float | None = None, acil_fiyat: float | None = None,
         set_id: int | None = None) -> Watch:
    limit = ayarlar().kullanici_basina_izleme_limiti
    mevcut = db.query(Watch).filter(Watch.user_id == kullanici.id).count()
    if mevcut >= limit:
        raise KotaDoldu(
            f"Ücretsiz planda en fazla {limit} ürün izleyebilirsin. "
            "Önce izlemediğin bir ürünü çıkar.")

    kaynak = kaynak_bul_veya_olustur(db, url)

    var_olan = (db.query(Watch)
                .filter(Watch.user_id == kullanici.id,
                        Watch.product_id == kaynak.product_id)
                .one_or_none())
    if var_olan is not None:
        raise IzlemeHatasi("Bu ürünü zaten izliyorsun")

    if set_id is not None:
        _set_dogrula(db, kullanici, set_id)

    w = Watch(user_id=kullanici.id, product_id=kaynak.product_id,
              hedef_fiyat=hedef_fiyat, acil_fiyat=acil_fiyat, set_id=set_id)
    db.add(w)

    urun = db.get(Product, kaynak.product_id)
    urun.izleyen_sayisi = (urun.izleyen_sayisi or 0) + 1
    # Yeni eklenen ürün ilk turda taransın (son_kontrol None → sırası gelmiş)
    urun.son_kontrol = None

    db.commit()
    db.refresh(w)
    return w


def guncelle(db: Session, kullanici: User, izleme_id: int, **alanlar) -> Watch:
    w = izleme_getir(db, kullanici, izleme_id)

    sustur_gun = alanlar.pop("sustur_gun", None)
    if sustur_gun is not None:
        w.sustur_bitis = (utc_simdi() + timedelta(days=sustur_gun)
                          if sustur_gun > 0 else None)

    if (set_id := alanlar.get("set_id")) is not None:
        _set_dogrula(db, kullanici, set_id)

    for ad, deger in alanlar.items():
        if deger is not None and hasattr(w, ad):
            setattr(w, ad, deger)

    # Kilitlenirken fiyat verilmediyse güncel fiyatı sabitle
    if w.kilitli and w.kilitli_fiyat is None and w.product:
        w.kilitli_fiyat = w.product.guncel_fiyat

    # Hedef değişince susturma kalkar: kullanıcı yeni hedeften alarm bekliyor
    if "hedef_fiyat" in alanlar and alanlar["hedef_fiyat"] is not None:
        w.sustur_bitis = None
        w.son_bildirim_ts = None
        w.son_bildirim_fiyat = None

    db.commit()
    db.refresh(w)
    return w


def sil(db: Session, kullanici: User, izleme_id: int) -> None:
    w = izleme_getir(db, kullanici, izleme_id)
    urun = w.product
    db.delete(w)
    if urun is not None:
        urun.izleyen_sayisi = max(0, (urun.izleyen_sayisi or 1) - 1)
    db.commit()
    # NOT: izleyeni kalmayan ürün ve geçmişi SİLİNMEZ. Küresel geçmiş ortak
    # varlıktır; birinin vazgeçmesi diğerlerinin (ve ileride eklenecek
    # kullanıcıların) fiyat hafızasını silmemeli. Temizlik ayrı bir bakım
    # işinin konusu (aylardır izleyeni olmayan ürünler arşivlenebilir).


def _set_dogrula(db: Session, kullanici: User, set_id: int) -> WatchSet:
    s = (db.query(WatchSet)
         .filter(WatchSet.id == set_id, WatchSet.user_id == kullanici.id)
         .one_or_none())
    if s is None:
        raise IzlemeHatasi("Set bulunamadı")
    return s

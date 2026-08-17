"""İzleme (Watch) use-case'leri — kullanıcının ürün takip etmesi.

Bu katmanın işi: HTTP'yi bilmeden, iş kurallarını uygulamak. Rotalar buradan
sadece fonksiyon çağırır; buradaki hiçbir şey `fastapi` import etmez. Aynı
fonksiyonları Telegram botu da çağıracak — kural iki yerde yazılmasın diye.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlparse, urlunparse

from sqlalchemy import case
from sqlalchemy.orm import Session, selectinload

from .. import aglar, siteler
from ..ayarlar import ayarlar
from ..models import Product, Source, User, Watch, WatchSet
from ..zaman import utc_simdi
from .ortak import alanlari_uygula

# URL'den atılacak takip parametreleri. Aynı ürünün linki farklı kampanya
# etiketleriyle geldiğinde AYNI kaynağa düşsün — yoksa aynı sayfa 5 kez
# taranır ve fiyat geçmişi 5'e bölünür.
COP_PARAMETRELER = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "referrer", "sellerId", "merchantId",
    "boutiqueId", "adjust_t", "adjust_tracker",
    # Amazon öneri/karusel izleri. `pd_rd_i` ÖZELLİKLE tehlikeli: linkin
    # GELDİĞİ ürünün ASIN'ini taşır, açılan ürünün değil — atılmazsa kanonik
    # URL'ye alakasız bir ürün kimliği karışır.
    "pd_rd_w", "pd_rd_wg", "pd_rd_r", "pd_rd_i", "pf_rd_p", "pf_rd_r",
    "content-id", "th", "psc", "smid", "linkCode", "tag",
    # Hepsiburada / Trendyol mağaza ve kampanya izleri
    "magaza", "wt_pc", "adj_t", "adj_campaign", "adj_adgroup", "v",
}

# Amazon takip verisini yolun İÇİNE gömer:
#   /dp/B09CD32DNH/ref=pd_lpo_d_sccl_4/262-3702812-9941328
# `ref=` sonrası ürünü tanımlamaz. Kesilmezse aynı ürünün "önerilerden gelen"
# linki ile doğrudan linki FARKLI kanonik URL üretir ve küresel fiyat geçmişi
# ikiye bölünür — K16'nın tam ihlali. Gerçek linklerle yapılan ilk denemede
# yakalandı; sentetik test URL'leri temiz olduğu için gözden kaçmıştı.
_YOL_KESICILER = ("ref=", "ref_=")


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
    yol = _yolu_kirp(p.path).rstrip("/") or "/"
    return urlunparse(("https", host, yol, "", sorgu, ""))


def _yolu_kirp(yol: str) -> str:
    """Takip verisi taşıyan yol parçasında ve sonrasında keser."""
    parcalar = yol.split("/")
    for i, parca in enumerate(parcalar):
        if parca.startswith(_YOL_KESICILER):
            return "/".join(parcalar[:i])
    return yol


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

    # SSRF kapısı (bkz. aglar.py). Asıl koruma çekme anındadır; buradaki
    # kontrol kullanıcının anlamlı bir hata görmesi içindir.
    sorun = aglar.url_sorunu(kanonik)
    if sorun is not None:
        raise IzlemeHatasi(f"Bu adres izlenemez: {sorun}")

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


def kaynak_ekle(db: Session, kullanici: User, izleme_id: int,
                url: str) -> Source:
    """İzlenen ürüne İKİNCİ bir kaynak bağlar (çoklu kaynak kurgusu).

    Tipik kullanım: kullanıcı bir mağaza linki eklemiş, sonra aynı ürünün
    toplayıcı (akakçe) sayfasını da ekliyor. Sistem her turda hepsini okur ve
    EN UCUZU bildirir; ayrıca bir kaynak bot duvarına takılsa bile ürün
    okunmaya devam eder.

    ONAY KULLANICININ: bu fonksiyon yalnızca kullanıcının açıkça seçtiği bir
    URL ile çağrılır. Otomatik eşleştirme yapılmıyor — yanlış ürünün fiyatını
    doğru ürünün geçmişine yazmak, sessiz ve geri dönüşü olmayan bir veri
    hatasıdır (bkz. toplayici.py).
    """
    w = (db.query(Watch)
         .filter(Watch.id == izleme_id, Watch.user_id == kullanici.id)
         .one_or_none())
    if w is None:
        raise IzlemeHatasi("İzleme bulunamadı")

    kanonik = url_normalize(url)
    sorun = aglar.url_sorunu(kanonik)
    if sorun is not None:
        raise IzlemeHatasi(f"Bu adres izlenemez: {sorun}")

    mevcut = db.query(Source).filter(Source.url == kanonik).one_or_none()
    if mevcut is not None:
        if mevcut.product_id == w.product_id:
            return mevcut                 # zaten bu ürünün kaynağı
        # ADRES BAŞKA BİR ÜRÜNE BAĞLI. Taşımak iki ürünü birleştirmek demek;
        # fiyat geçmişleri karışır ve bu GERİ ALINAMAZ. Kullanıcıya ayrı ürün
        # olarak eklemesini söylemek, sessizce birleştirmekten iyidir.
        raise IzlemeHatasi(
            "Bu adres başka bir ürüne bağlı. Ayrı ürün olarak ekleyebilirsin.")

    # `kaynak_bul_veya_olustur` KULLANILMIYOR: o fonksiyon adres yeniyse
    # yanına bir Product da yaratır. Burada ürün zaten var; geçici bir ürün
    # yaratıp sonra silmek, Product→Source cascade'i yüzünden yeni kaynağı da
    # silerdi. Kaynağı doğrudan mevcut ürüne bağlamak hem daha basit hem doğru.
    kural = siteler.kural(kanonik)
    kaynak = Source(
        product_id=w.product_id, url=kanonik,
        host=siteler.host_cikar(kanonik),
        satici=kural.get("satici"), toplayici=bool(kural.get("toplayici")),
    )
    db.add(kaynak)
    # Yeni kaynak bu turda okunsun — kullanıcı eklediği mağazanın fiyatını
    # bir sonraki uzun aralığı beklemeden görmeli.
    w.product.sonraki_kontrol = None
    db.flush()
    return kaynak


def izlemeler(db: Session, kullanici: User) -> list[Watch]:
    """Kullanıcının izlemeleri — ürünleriyle BİRLİKTE yüklenir.

    `selectinload` olmadan her satırın `w.product` erişimi ayrı bir SELECT
    açar (N+1): 20 izleme = 21 sorgu. Bu liste hem web ana ekranında hem
    /liste komutunda her açılışta çekiliyor, yani en sıcak sorgu yolu burası.
    `selectinload` (JOIN değil) seçildi çünkü ilişki koleksiyon değil ama
    JOIN, satır çoğaltmadan kaçınmak için gereksiz; iki sorguyla biter.
    """
    return (db.query(Watch)
            .options(selectinload(Watch.product))
            .filter(Watch.user_id == kullanici.id)
            .order_by(Watch.created_at.desc())
            .all())


def izleme_getir(db: Session, kullanici: User, izleme_id: int) -> Watch:
    # Kaynaklar da yüklenir: detay ucu her kaynağın çıkış linkini üretiyor,
    # tembel bırakılırsa kaynak başına ayrı sorgu açılır.
    w = (db.query(Watch)
         .options(selectinload(Watch.product).selectinload(Product.sources))
         .filter(Watch.id == izleme_id, Watch.user_id == kullanici.id)
         .one_or_none())
    if w is None:
        raise IzlemeHatasi("İzleme bulunamadı")
    return w


def _izleyen_sayaci(db: Session, urun_id: int, delta: int) -> None:
    """Sayacı VERİTABANINDA artırır/azaltır — Python'da değil.

    `urun.izleyen_sayisi = urun.izleyen_sayisi + 1` bir OKU-DEĞİŞTİR-YAZ
    dizisidir: aynı ürünü aynı anda ekleyen iki istek de 5 okur, ikisi de 6
    yazar, biri kaybolur. Sayaç yalnızca tarama önceliğini belirlediği için
    felaket değil ama zamanla gerçeklikten kopar. Tek UPDATE ifadesi bunu
    veritabanının atomikliğine devreder.

    Azaltmada `CASE` kullanılıyor, `MAX()` değil: SQLite'ta `max(a,b)` skaler,
    PostgreSQL'de ise `MAX()` bir toplam (aggregate) fonksiyonudur ve orada
    `GREATEST` gerekir. `CASE` iki motorda da aynı çalışır.
    """
    mevcut = case((Product.izleyen_sayisi.is_(None), 0),
                  else_=Product.izleyen_sayisi)
    yeni = mevcut + delta if delta > 0 else case(
        (mevcut + delta < 0, 0), else_=mevcut + delta)
    (db.query(Product)
     .filter(Product.id == urun_id)
     .update({Product.izleyen_sayisi: yeni}, synchronize_session=False))


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

    _izleyen_sayaci(db, kaynak.product_id, +1)

    # Ürün ilk turda taransın. `sonraki_kontrol` sıfırlanır, `son_kontrol`
    # DEĞİL: ikincisi "en son ne zaman okundu" olgusudur ve arayüzde
    # gösterilir. Eskiden burada o da siliniyordu — yani başkasının aylardır
    # izlediği bir ürüne yeni biri abone olunca, ürün herkes için "hiç
    # kontrol edilmemiş" görünüyordu.
    urun = db.get(Product, kaynak.product_id)
    urun.sonraki_kontrol = None

    db.commit()
    db.refresh(w)
    return w


# Kullanıcının PATCH ile değiştirebileceği alanların TAM listesi.
# Kuralların gerekçesi için bkz. `ortak.alanlari_uygula`.
GUNCELLENEBILIR = frozenset({
    "hedef_fiyat", "acil_fiyat", "aktif", "kilitli", "kilitli_fiyat", "set_id",
})

# Bunlara açıkça `null` gönderilmesi "değeri SİL" demektir.
# `aktif`/`kilitli` burada YOK: onlar boolean, null'un anlamı yok.
TEMIZLENEBILIR = frozenset({
    "hedef_fiyat", "acil_fiyat", "kilitli_fiyat", "set_id",
})


def guncelle(db: Session, kullanici: User, izleme_id: int, **alanlar) -> Watch:
    """İzlemeyi kısmi olarak günceller (PATCH semantiği).

    Rota `exclude_unset=True` ile çağırır: bir anahtarın VARLIĞI kullanıcının
    o alana bilerek dokunduğu anlamına gelir. Bu yüzden `None` "dokunulmadı"
    değil, "temizle" demektir — eskiden ikisi ayırt edilemediği için hedef
    fiyat bir kez konduktan sonra API'den ASLA kaldırılamıyordu.
    """
    w = izleme_getir(db, kullanici, izleme_id)

    # `sustur_gun` bir sütun değil, gün sayısından tarihe çevrilen bir komut.
    sustur_gun = alanlar.pop("sustur_gun", None)
    if sustur_gun is not None:
        w.sustur_bitis = (utc_simdi() + timedelta(days=sustur_gun)
                          if sustur_gun > 0 else None)

    if alanlar.get("set_id") is not None:
        _set_dogrula(db, kullanici, alanlar["set_id"])

    eski_hedef = w.hedef_fiyat
    alanlari_uygula(w, alanlar, GUNCELLENEBILIR, TEMIZLENEBILIR, IzlemeHatasi)

    # Kilitlenirken fiyat verilmediyse güncel fiyatı sabitle
    if w.kilitli and w.kilitli_fiyat is None and w.product:
        w.kilitli_fiyat = w.product.guncel_fiyat

    # Hedef GERÇEKTEN değiştiyse bildirim geçmişi sıfırlanır: kullanıcı yeni
    # hedeften alarm bekliyor, eski eşikte gönderilmiş bildirimin dedup kaydı
    # yeni eşiği susturmamalı. Aynı değeri yeniden göndermek sıfırlama sayılmaz.
    if w.hedef_fiyat != eski_hedef:
        w.son_bildirim_ts = None
        w.son_bildirim_fiyat = None
        # Susturma da kalkar — AMA aynı istekte açıkça susturma istendiyse
        # kullanıcının dediği kazanır (eskiden sessizce eziliyordu).
        if sustur_gun is None:
            w.sustur_bitis = None

    db.commit()
    db.refresh(w)
    return w


def sil(db: Session, kullanici: User, izleme_id: int) -> None:
    w = izleme_getir(db, kullanici, izleme_id)
    urun_id = w.product_id
    db.delete(w)
    db.flush()
    _izleyen_sayaci(db, urun_id, -1)
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

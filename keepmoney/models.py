"""Veri modeli.

EN ÖNEMLİ TASARIM KARARI — küresel ürün / kişisel izleme ayrımı:

    Product  (mantıksal ürün)        ← KÜRESEL, tüm kullanıcılar paylaşır
      └ Source (mağaza URL'i)        ← KÜRESEL, url ile tekil
           └ PriceReading            ← KÜRESEL fiyat geçmişi
    Watch    (kullanıcının izlemesi) ← KİŞİSEL: hedef, susturma, bildirim durumu
      └ WatchSet (bütçeli koleksiyon)

Neden böyle: fiyat, ürünün nesnel bir özelliğidir — kullanıcıya göre değişmez.
Geçmişi kullanıcı başına tutmak iki felakete yol açar:
  1) MALİYET — 500 kişi aynı ekran kartını izliyorsa aynı sayfa 500 kez
     taranır. Bu modelde 1 kez taranır; ürün paylaşımı arttıkça kullanıcı
     başına maliyet DÜŞER.
  2) DEĞER — yeni kullanıcı bir ürünü eklediği an aylarca geriye giden fiyat
     geçmişini görür. Kişiye özel geçmişte ilk gün boş grafik görür ve
     "bu iyi fiyat mı" sorusuna 5 gün cevap alamaz.

Kişisel olan yalnızca KARAR katmanıdır: hedef fiyat, susturma, hangi sette
olduğu, en son ne zaman bildirim aldığı. Watch tablosu tam olarak budur.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base
from .zaman import utc_simdi


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # Telegram bağlama — chat_id'yi kullanıcı ELLE GİRMEZ. Web'de üretilen
    # tek kullanımlık token, bot /start ile alındığında sunucu tarafından
    # doğrulanır ve chat_id buraya yazılır. Elle giriş, botun yazma yetkisi
    # olduğu bir sistemde hesap ele geçirme yoludur.
    telegram_chat_id = Column(String, unique=True, index=True, nullable=True)
    telegram_token = Column(String, index=True, nullable=True)
    telegram_token_biter = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utc_simdi)

    watches = relationship("Watch", back_populates="user",
                           cascade="all, delete-orphan")
    sets = relationship("WatchSet", back_populates="user",
                        cascade="all, delete-orphan")


# ───────────────────────── KÜRESEL KATMAN ─────────────────────────

class Product(Base):
    """Mantıksal ürün. Birden çok mağaza kaynağı (Source) taşıyabilir;
    güncel fiyat bunların EN UCUZUdur."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    ad = Column(String, nullable=False)
    kategori = Column(String, nullable=True, index=True)

    # Denormalize (hız için) — her taramada en ucuz kaynaktan güncellenir
    guncel_fiyat = Column(Float, nullable=True)
    guncel_satici = Column(String, nullable=True)
    guncel_kaynak_id = Column(Integer, nullable=True)
    son_kontrol = Column(DateTime, nullable=True)

    # Puan/yorum — fiyatın tek başına yetmediği yer. 40.000 TL'lik dip fiyat,
    # 2.1 puanlı bir üründe fırsat değildir. Grafiğin yanında gösterilir.
    puan = Column(Float, nullable=True)            # 0-5
    yorum_sayisi = Column(Integer, nullable=True)

    # Tarama sıklığı uyarlanabilir: hedefe yakın/oynak ürün sık, aylardır
    # kıpırdamayan ürün seyrek taranır. Ölçeklenmenin anahtarı bu alandır.
    kontrol_araligi_dk = Column(Integer, default=60)
    izleyen_sayisi = Column(Integer, default=0)   # kaç Watch işaret ediyor

    created_at = Column(DateTime, default=utc_simdi)

    sources = relationship("Source", back_populates="product",
                           cascade="all, delete-orphan")
    watches = relationship("Watch", back_populates="product")


class Source(Base):
    """Bir ürünün tek bir mağazadaki sayfası. URL küresel olarak tekildir —
    iki kullanıcı aynı linki eklerse aynı satıra bağlanırlar."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    url = Column(String, unique=True, index=True, nullable=False)
    host = Column(String, index=True, nullable=False)
    satici = Column(String, nullable=True)

    # Toplayıcı (akakce vb.) kaynaklar önceliklidir: tek sayfada N satıcının
    # en ucuzu bulunur — N mağaza taramaktan çok daha ucuz.
    toplayici = Column(Boolean, default=False)

    son_fiyat = Column(Float, nullable=True)
    son_guven = Column(String, nullable=True)     # json-ld | secici | meta | regex
    durum = Column(String, default="BEKLEMEDE")   # OK | ENGELLI | OLU | HATA
    son_kontrol = Column(DateTime, nullable=True)
    hata_serisi = Column(Integer, default=0)

    # Koruma katmanı durumu (karar.IzlemeDurumu) — KAYNAĞA ait, kullanıcıya
    # değil: "bu okuma güvenilir mi" sorusu nesneldir, herkes için aynı cevabı
    # verir. Kişisel olan yalnızca bildirim durumudur (Watch'ta).
    bekleyen_fiyat = Column(Float, nullable=True)     # 2-okuma doğrulaması bekliyor
    asiri_supheli_seri = Column(Integer, default=0)   # üst üste bozuk okuma
    bozuk_uyarildi = Column(Boolean, default=False)

    product = relationship("Product", back_populates="sources")
    readings = relationship("PriceReading", back_populates="source",
                            cascade="all, delete-orphan")


class PriceReading(Base):
    """Küresel fiyat geçmişi. Analiz katmanının tek girdisi.
    Kaynak bazında tutulur ki grafikte mağaza başına ayrı çizgi çizilebilsin."""
    __tablename__ = "price_readings"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False,
                       index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False,
                        index=True)
    fiyat = Column(Float, nullable=False)
    ts = Column(DateTime, default=utc_simdi, index=True)

    source = relationship("Source", back_populates="readings")


class DomainHealth(Base):
    """Hangi mağaza sitesi ne sıklıkla başarısız oluyor. Domain başına TEK
    satır (upsert) — sınırsız büyüyen log tablosu değil."""
    __tablename__ = "domain_health"

    id = Column(Integer, primary_key=True)
    domain = Column(String, unique=True, index=True, nullable=False)
    basarili = Column(Integer, default=0)
    basarisiz = Column(Integer, default=0)
    son_durum = Column(String, nullable=True)
    son_kontrol = Column(DateTime, default=utc_simdi)


# ───────────────────────── KİŞİSEL KATMAN ─────────────────────────

class WatchSet(Base):
    """Bütçeli koleksiyon ("PC Toplama", "Kombin"). Ürün üstü kavram:
    parçalar tek tek hedefte olmasa bile TOPLAM bütçenin altına inince
    bildirim gider — bu, rakiplerde bulunmayan asıl ayırt edici özellik."""
    __tablename__ = "watch_sets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ad = Column(String, nullable=False)
    hedef_butce = Column(Float, nullable=True)
    sablon = Column(String, nullable=True)
    son_bildirim_ts = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_simdi)

    user = relationship("User", back_populates="sets")
    watches = relationship("Watch", back_populates="set")


class Watch(Base):
    """Kullanıcının bir ürünü izlemesi. TÜM kişisel karar durumu burada."""
    __tablename__ = "watches"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    set_id = Column(Integer, ForeignKey("watch_sets.id"), nullable=True)

    hedef_fiyat = Column(Float, nullable=True)
    # İkinci eşik: altına inince cooldown beklemez, sessiz saati deler.
    acil_fiyat = Column(Float, nullable=True)

    aktif = Column(Boolean, default=True)
    # Kilitli izleme: kullanıcı "bunu aldım/fiyatı sabitledim" der, bütçe
    # hesabında bu değer kullanılır, tarama sonucu üzerine yazmaz.
    kilitli = Column(Boolean, default=False)
    kilitli_fiyat = Column(Float, nullable=True)

    sustur_bitis = Column(DateTime, nullable=True)
    son_bildirim_ts = Column(DateTime, nullable=True)
    son_bildirim_fiyat = Column(Float, nullable=True)

    created_at = Column(DateTime, default=utc_simdi)

    user = relationship("User", back_populates="watches")
    product = relationship("Product", back_populates="watches")
    set = relationship("WatchSet", back_populates="watches")

    __table_args__ = (
        # Aynı kullanıcı aynı ürünü iki kez izleyemez.
        UniqueConstraint("user_id", "product_id", name="uix_watch_user_product"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    watch_id = Column(Integer, ForeignKey("watches.id"), nullable=True)
    tur = Column(String, nullable=False)   # HEDEF | DIP | SAHTE_INDIRIM | SET_HEDEF | KAYNAK_BOZUK
    baslik = Column(String, nullable=False)
    mesaj = Column(String, nullable=False)
    okundu = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_simdi, index=True)

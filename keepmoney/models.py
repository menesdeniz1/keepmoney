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
    Index,
    Integer,
    String,
    Table,
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

    # ── Hesap yaşam döngüsü ──────────────────────────────────────
    # Token'lar HASH'LENMİŞ saklanır, ham hâlleriyle değil. Sebep: bu
    # sütunlar parolaya eşdeğer yetki taşır — sıfırlama token'ı olan kişi
    # hesabı ele geçirir. Veritabanı yedeği sızarsa (ya da bir SQL enjeksiyonu
    # okuma yaparsa) ham token doğrudan hesap devralmadır; hash'i işe yaramaz.
    parola_sifirlama_hash = Column(String, index=True, nullable=True)
    parola_sifirlama_biter = Column(DateTime, nullable=True)

    eposta_dogrulandi = Column(Boolean, default=False, nullable=False)
    eposta_dogrulama_hash = Column(String, index=True, nullable=True)
    eposta_dogrulama_biter = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utc_simdi)

    watches = relationship("Watch", back_populates="user",
                           cascade="all, delete-orphan")
    sets = relationship("WatchSet", back_populates="user",
                        cascade="all, delete-orphan")
    # Uyarılar da kişisel veridir: hesap silinince gider (KVKK).
    alerts = relationship("Alert", back_populates="user",
                          cascade="all, delete-orphan")


# ───────────────────────── KÜRESEL KATMAN ─────────────────────────

class Product(Base):
    """Mantıksal ürün. Birden çok mağaza kaynağı (Source) taşıyabilir;
    güncel fiyat bunların EN UCUZUdur."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    ad = Column(String, nullable=False)
    kategori = Column(String, nullable=True, index=True)

    # Ürün eklenirken ad URL'den türetilir (istek içinde ağa çıkıp kullanıcıyı
    # bekletmemek için). İlk başarılı taramada gerçek başlıkla değiştirilir ve
    # bu bayrak düşer — sonraki taramalar kullanıcının düzelttiği adı EZMEZ.
    ad_gecici = Column(Boolean, default=True)

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

    # Sıradaki tarama zamanı — KUYRUĞUN KENDİSİ (bkz. MIMARI K24: DB kuyruk
    # yerine geçiyor). `son_kontrol + kontrol_araligi_dk` her satırda farklı
    # bir aralık demek; bu hesabı SQL'de taşınabilir biçimde yapmanın yolu yok
    # (SQLite ile PostgreSQL'in tarih aritmetiği farklı). Sonucu sütunda
    # tutmak, seçimi indeksli tek karşılaştırmaya indirger:
    #     WHERE sonraki_kontrol IS NULL OR sonraki_kontrol <= now()
    # Aksi hâlde her turda TÜM ürün tablosu belleğe çekilip Python'da
    # süzülmek zorundaydı. NULL = "sırası gelmiş" (yeni eklendi ya da hiç
    # taranmadı). İş kuyruklarının `next_run_at`/`visible_at` deseni.
    sonraki_kontrol = Column(DateTime, nullable=True, index=True)

    izleyen_sayisi = Column(Integer, default=0)   # kaç Watch işaret ediyor

    # "Bu iyi bir fiyat mı" bağlamı — HER TARAMADA analiz.fiyat_baglami() ile
    # hesaplanıyordu ve atılıyordu (yalnızca uyarı kararı için kullanılıp
    # unutuluyordu). Liste ucu ürün başına geçmiş sorgusu açmadan sinyali
    # gösterebilsin diye burada saklanır. `sahte_indirim` ve `trend_yonu`
    # BİLEREK YOK: kart bunları göstermiyor, gösteren detay sayfası zaten
    # canlı hesaplıyor — gereksiz sütun yazma maliyeti olurdu.
    sinyal = Column(String, nullable=True)          # dip | ucuz | pahali
    dip90 = Column(Float, nullable=True)
    medyan90 = Column(Float, nullable=True)
    yuzdelik = Column(Integer, nullable=True)       # 0-100
    gecmis_gun = Column(Integer, nullable=True)     # kaç günlük veriye dayanıyor
    baglam_ts = Column(DateTime, nullable=True)     # ne zaman hesaplandı

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
    # OK | ENGELLI | OLU | HATA | BEKLEMEDE | STOKTA_YOK
    durum = Column(String, default="BEKLEMEDE")
    son_kontrol = Column(DateTime, nullable=True)
    hata_serisi = Column(Integer, default=0)

    # Pazar derinliği — yalnızca toplayıcı kaynaklarda dolar (bkz.
    # ayikla.pazar_ayikla). Saklanıyor çünkü kullanıcıya gösterilen "5 satıcı ·
    # 2. en ucuz 41.500" bilgisi kararın BAĞLAMIDIR: tek satıcının aykırı
    # fiyatı, geçmişi olmayan üründe elimizdeki tek uyarı işaretidir.
    satici_sayisi = Column(Integer, nullable=True)
    ikinci_fiyat = Column(Float, nullable=True)

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
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    fiyat = Column(Float, nullable=False)
    ts = Column(DateTime, default=utc_simdi, index=True)

    source = relationship("Source", back_populates="readings")

    __table_args__ = (
        # ÜRÜNÜN EN SICAK SORGUSU: `WHERE product_id=? ORDER BY ts`.
        # Hem grafik hem HER tarama turu (worker `_okuma_gecmisi` ile analiz
        # ve bir sonraki kontrol aralığı için okuyor) bu deseni kullanıyor.
        #
        # ÖLÇÜLDÜ: yalnız `product_id` indeksiyle SQLite planı
        #   SEARCH ... USING INDEX ix_price_readings_product_id
        #   USE TEMP B-TREE FOR ORDER BY        ← her sorguda bellekte sıralama
        # Bileşik indeks o sıralamayı ortadan kaldırıyor.
        #
        # Bu tablo SÜREKLİ BÜYÜR (ürünün asıl değeri fiyat geçmişi) ve
        # yazma yolu da sıcak; bu yüzden tek `product_id` indeksi bırakılmadı:
        # bileşiğin en soldaki sütunu zaten aynı işi görüyor, ikisini birden
        # tutmak her INSERT'e bedava olmayan ikinci bir ağaç eklerdi.
        Index("ix_price_readings_product_ts", "product_id", "ts"),
    )


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

# İzleme ↔ set: ÇOKTAN ÇOKA.
#
# Başta `Watch.set_id` tek bir sütundu ve bir ürün yalnızca TEK sete
# girebiliyordu. Bu belgelenmiş bir karar değildi — en basit hâli önce
# yazılmış, sonra dokunulmamıştı. Oysa gerçek kullanımda aynı ekran kartı
# hem "PC Toplama" hem "Kara Cuma" listesinde olabilir; kullanıcıyı ikisinden
# birini seçmeye zorlamak modelin eksikliğiydi.
#
# İki tarafta da ON DELETE CASCADE: izleme ya da set silinince üyelik satırı
# kendiliğinden gider. Uygulama katmanına bırakılsaydı, silme yollarından
# birinde unutulunca öksüz satır kalırdı (SQLite'ta da yabancı anahtarlar
# açık — bkz. db.py).
set_uyeleri = Table(
    "set_uyeleri",
    Base.metadata,
    Column("watch_id", Integer,
           ForeignKey("watches.id", ondelete="CASCADE"),
           primary_key=True),
    Column("set_id", Integer,
           ForeignKey("watch_sets.id", ondelete="CASCADE"),
           primary_key=True),
)


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
    watches = relationship("Watch", secondary=set_uyeleri,
                           back_populates="setler")


class Watch(Base):
    """Kullanıcının bir ürünü izlemesi. TÜM kişisel karar durumu burada."""
    __tablename__ = "watches"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    hedef_fiyat = Column(Float, nullable=True)
    # İkinci eşik: altına inince cooldown beklemez, sessiz saati deler.
    acil_fiyat = Column(Float, nullable=True)

    # BACKLOG E1: mutlak hedef fiyatı BİLMEYEN kullanıcının doğal ifadesi
    # ("%15 düşerse haber ver"). Referans 90 GÜNLÜK MEDYAN olacak (E2'nin
    # worker.py işi) — "en son gördüğüm fiyat" referans alınırsa yükselip
    # düşen fiyat sahte uyarı üretir. Burada yalnızca kullanıcının SEÇTİĞİ
    # eşik saklanır, hesap burada YAPILMAZ.
    dusus_yuzdesi = Column(Integer, nullable=True)      # 1-90
    # Yeniden kurma (rearm) süresi gün cinsinden — E4'ün "3g · 7g · 30g ·
    # hiç" seçeneği. `None` = varsayılan (7 gün). "hiç" gibi özel
    # değerlerin sayısal karşılığı E4'ün işi — burada yalnızca BOŞ
    # BIRAKILAN bir tam sayı sütunu var, kısıt yok.
    yeniden_kur_gun = Column(Integer, nullable=True)

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
    # Bir izleme BİRDEN ÇOK sette olabilir (bkz. `set_uyeleri`).
    setler = relationship("WatchSet", secondary=set_uyeleri,
                          back_populates="watches")

    @property
    def set_idler(self) -> list[int]:
        """API yanıtının okuduğu düz kimlik listesi.

        Şema (`IzlemeYaniti`) ORM nesnesinden doğruluyor; ilişkiyi orada
        kimliğe çevirmek her rotada tekrar edilen bir dönüşüm olurdu.
        """
        return [s.id for s in self.setler]
    # İzleme silinince uyarı SİLİNMEZ, yalnızca bağı kopar (aşağıya bak).
    # passive_deletes: bağı veritabanı koparır, ORM satırları belleğe çekmez.
    alerts = relationship("Alert", back_populates="watch", passive_deletes=True)

    __table_args__ = (
        # Aynı kullanıcı aynı ürünü iki kez izleyemez.
        UniqueConstraint("user_id", "product_id", name="uix_watch_user_product"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False)
    # ON DELETE SET NULL — SİLME DEĞİL: uyarı, olmuş bir olayın kaydıdır.
    # Kullanıcı ürünü takipten çıkardığında geçmiş bildirimleri kaybolmamalı;
    # yalnızca artık var olmayan izlemeye işaret etmemeli.
    #
    # Bu kural eksikti ve Postgres'te "takipten çıkar" düğmesi, o üründen bir
    # kez bile uyarı almış her kullanıcı için yabancı anahtar ihlaliyle 500
    # dönüyordu. SQLite yabancı anahtarları zorlamadığı için testler
    # görmüyordu (bkz. db.py — artık SQLite'ta da açık).
    watch_id = Column(Integer, ForeignKey("watches.id", ondelete="SET NULL"),
                      nullable=True)
    tur = Column(String, nullable=False)   # HEDEF | DIP | SAHTE_INDIRIM | SET_HEDEF | KAYNAK_BOZUK
    baslik = Column(String, nullable=False)
    mesaj = Column(String, nullable=False)
    okundu = Column(Boolean, default=False)
    # Telegram'a iletildi mi? Uyarı ÜRETİMİ ile İLETİMİ ayrı sorumluluklar:
    # worker uyarıyı yazar, gönderici ayrı bir döngüde iletir. Böylece
    # Telegram kesintisi taramayı durdurmaz ve uyarı kaybolmaz.
    telegram_gonderildi = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=utc_simdi, index=True)

    user = relationship("User", back_populates="alerts")
    watch = relationship("Watch", back_populates="alerts")

    __table_args__ = (
        # Bildirim listesi: `WHERE user_id=? ORDER BY created_at DESC`.
        # Panel her açılışta okunmamış sayısını da soruyor. Tek `user_id`
        # indeksiyle plan yine TEMP B-TREE ile sıralıyordu.
        Index("ix_alerts_user_created", "user_id", "created_at"),
    )

"""API şemaları (Pydantic v2).

ORM modellerinden AYRI tutulur. Sebep: veritabanı şeması iç mesele, API
sözleşmesi dış mesele. `Watch.son_bildirim_ts` gibi iç alanlar dışarı
sızmamalı; `yorum` gibi hesaplanan alanlar DB'de olmadığı halde dışarı
verilmeli. İkisini tek sınıfa bindirmek, zamanla ya API'yi ya şemayı rehin alır.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, HttpUrl

# ─────────────────────────── Kimlik ───────────────────────────


class KayitIstegi(BaseModel):
    eposta: EmailStr
    # Üst sınır bcrypt'in 72 baytlık sessiz kesme davranışı yüzünden;
    # alt sınır asgari makullük.
    parola: str = Field(min_length=8, max_length=72)


class GirisIstegi(BaseModel):
    eposta: EmailStr
    parola: str = Field(max_length=72)


class TokenYaniti(BaseModel):
    erisim_tokeni: str
    tur: str = "bearer"


class KullaniciYaniti(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    eposta: str = Field(validation_alias="email")
    telegram_bagli: bool = False
    eposta_dogrulandi: bool = False
    created_at: datetime


class ParolaSifirlamaIstegi(BaseModel):
    eposta: EmailStr


class ParolaSifirlamaUygulaIstegi(BaseModel):
    token: str = Field(min_length=16, max_length=200)
    parola: str = Field(min_length=8, max_length=72)


class TokenIstegi(BaseModel):
    """E-posta doğrulama bağlantısındaki token."""
    token: str = Field(min_length=16, max_length=200)


class HesapSilmeIstegi(BaseModel):
    """Yıkıcı işlem — parola YENİDEN sorulur.

    Oturumu çalınmış birinin hesabı silmesini zorlaştırır ve kullanıcının
    niyetini teyit eder.
    """
    parola: str = Field(max_length=72)


class TelegramBaglamaYaniti(BaseModel):
    """Kullanıcıya verilen deep-link. Chat ID elle girilmez."""
    baglanti: str
    gecerlilik_dk: int


# ─────────────────────────── Ürün ───────────────────────────


class KaynakYaniti(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    host: str
    satici: str | None = None
    son_fiyat: float | None = None
    durum: str
    son_kontrol: datetime | None = None
    # Mağazaya gidiş linki. Ortaklık etiketi SAKLANAN url'ye değil buraya
    # eklenir (bkz. affiliate.py). `ortaklik` bayrağı arayüzde açıkça
    # gösterilir — gizli komisyon, fiyat tavsiyesi veren bir üründe güveni
    # tümden bitirir.
    cikis_url: str = ""
    ortaklik: bool = False

    # Pazar derinliği — yalnızca toplayıcı kaynaklarda dolu. Kullanıcıya
    # gösterilmesi kararın BAĞLAMIDIR: "en ucuz 4.000, ikincisi 52.000"
    # tablosu, o fiyata neden temkinli yaklaşıldığını tek bakışta anlatır.
    satici_sayisi: int | None = None
    ikinci_fiyat: float | None = None


class KaynakOnerisi(BaseModel):
    """Toplayıcı aramasından çıkan aday. HİÇBİR ŞEYE YAZILMAZ.

    Kullanıcı bir adayı seçene kadar sistem hiçbir bağ kurmaz. Otomatik
    eşleştirme bilinçli olarak yok: benzer adlı iki ürünün fiyatını
    karıştırmak, grafiğe işleyen ve geri alınamayan bir veri hatasıdır.
    """
    ad: str
    url: str


class KaynakEkleIstegi(BaseModel):
    """Kullanıcının onayladığı kaynak. `url` doğrulanır, SSRF kapısından
    servis katmanında ayrıca geçer."""
    url: HttpUrl


class FiyatNoktasi(BaseModel):
    """Grafik verisi — gün başına tek nokta (bkz. MIMARI K4)."""
    gun: date
    fiyat: float


class BaglamYaniti(BaseModel):
    """'Bu iyi bir fiyat mı?' — Keepa'nın karşılığı olan katman."""
    sinyal: str                       # dip | ucuz | pahali
    emoji: str
    yorum: str                        # kullanıcıya gösterilecek İNSAN CÜMLESİ
    dip90: float
    medyan90: float
    yuzdelik: int
    tum_zamanlar_dibi: float
    tum_zamanlar_dibi_tarih: date
    en_dusuk_gun: int
    gun_sayisi: int
    sahte_indirim: bool
    trend_yonu: str
    iyi_firsat: bool


class UrunOzet(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ad: str
    kategori: str | None = None
    guncel_fiyat: float | None = None
    guncel_satici: str | None = None
    puan: float | None = None
    yorum_sayisi: int | None = None
    son_kontrol: datetime | None = None
    # BACKLOG A4: liste ucu artık sinyali DÖNDÜRÜYOR — ek sorgu YOK, hepsi
    # `Product` sütunu (A1) ve `Watch.product` zaten `selectinload` ile
    # yükleniyor (bkz. servisler/izleme.py::izlemeler). `UrunDetay.baglam`
    # (aşağıda) canlı hesaplanmaya devam ediyor; ikisi arasında bir tarama
    # turu kadar fark olabilir — kart saklanan değeri, detay sayfası anlık
    # hesabı gösterir, bu kabul edilebilir (bkz. A2).
    sinyal: str | None = None
    dip90: float | None = None
    medyan90: float | None = None
    yuzdelik: int | None = None
    gecmis_gun: int | None = None


class UrunDetay(UrunOzet):
    kaynaklar: list[KaynakYaniti] = []
    gecmis: list[FiyatNoktasi] = []
    baglam: BaglamYaniti | None = None


# ─────────────────────────── İzleme ───────────────────────────


class IzlemeEkleIstegi(BaseModel):
    """Kullanıcı sadece linki yapıştırır; ad/kategori sayfadan çıkarılır."""
    url: HttpUrl
    hedef_fiyat: float | None = Field(default=None, gt=0)
    acil_fiyat: float | None = Field(default=None, gt=0)
    # Bir ürün BİRDEN ÇOK sette olabilir (bkz. models.set_uyeleri).
    set_idler: list[int] | None = None


class IzlemeGuncelleIstegi(BaseModel):
    hedef_fiyat: float | None = Field(default=None, gt=0)
    acil_fiyat: float | None = Field(default=None, gt=0)
    aktif: bool | None = None
    kilitli: bool | None = None
    kilitli_fiyat: float | None = Field(default=None, ge=0)
    # PATCH semantiği: anahtarın VARLIĞI "üyelikleri şu listeye eşitle"
    # demek. Boş liste "hiçbir sette olmasın" — silme değil, tanım.
    set_idler: list[int] | None = None
    sustur_gun: int | None = Field(default=None, ge=0, le=365)


class IzlemeYaniti(BaseModel):
    # populate_by_name: ORM nesnesi (`Watch.product`) de, servis sözlüğü
    # (`{"urun": ...}`) de aynı şemaya doğrulanabilsin.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    hedef_fiyat: float | None = None
    acil_fiyat: float | None = None
    aktif: bool
    kilitli: bool
    kilitli_fiyat: float | None = None
    sustur_bitis: datetime | None = None
    set_idler: list[int] = Field(default_factory=list)
    urun: UrunOzet = Field(validation_alias=AliasChoices("urun", "product"))


class IzlemeDetay(IzlemeYaniti):
    urun: UrunDetay = Field(validation_alias=AliasChoices("urun", "product"))


# ─────────────────────────── Set ───────────────────────────


class SetIstegi(BaseModel):
    ad: str = Field(min_length=1, max_length=60)
    hedef_butce: float | None = Field(default=None, gt=0)
    sablon: str | None = None


class UyelikIstegi(BaseModel):
    """Sete toplu ürün ekleme. Üst sınır var: sınırsız liste, tek istekte
    binlerce satır yazma girişimine açık kapı bırakır."""
    izleme_idler: list[int] = Field(min_length=1, max_length=200)


class UyelikSonucu(BaseModel):
    """Kısmi başarı sonucu.

    `atlandi` yalnızca sayı değil SEBEP taşır ("zaten_uye" / "bulunamadi"):
    kullanıcı hangi ürünün neden alınmadığını görmeden düzeltemez (K56).
    """
    eklendi: list[int]
    atlandi: list[dict]


class SetGuncelleIstegi(BaseModel):
    """Kısmi güncelleme — TÜM alanlar isteğe bağlı.

    PATCH ucu bir dönem `SetIstegi`yi yeniden kullanıyordu; orada `ad`
    zorunlu olduğu için "sadece bütçeyi değiştir" isteği 422 dönüyordu.
    Oluşturma ile güncellemenin sözleşmesi aynı değildir.
    """
    ad: str | None = Field(default=None, min_length=1, max_length=60)
    hedef_butce: float | None = Field(default=None, gt=0)
    sablon: str | None = None


class SetUyesi(BaseModel):
    """Setin içindeki bir ürün — listede göstermeye yetecek kadarı."""
    izleme_id: int
    ad: str
    fiyat: float | None = None
    kilitli: bool = False


class SetYaniti(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ad: str
    hedef_butce: float | None = None
    # Hesaplanan alanlar — DB'de yok, API sözleşmesinde var
    toplam: float = 0.0
    eksik_uye: int = 0
    hedefte: bool = False
    uye_sayisi: int = 0
    # ÜYELER DE DÖNER: set kartı yalnızca "3 ürün" yazıyordu, içinde ne
    # olduğu hiç görünmüyordu — bütçe takibi yapılan bir listede neyin
    # toplandığını göstermemek eksikti. Ek sorgu maliyeti YOK: üyeler
    # `_UYELERLE` ile zaten yükleniyor.
    uyeler: list[SetUyesi] = Field(default_factory=list)


# ─────────────────────────── Uyarı ───────────────────────────


class UyariYaniti(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tur: str
    baslik: str
    mesaj: str
    okundu: bool
    created_at: datetime
    watch_id: int | None = None

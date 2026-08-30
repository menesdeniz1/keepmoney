"""Bot testleri — mesaj kurucular ve uyarı gönderici, gerçek ağ olmadan."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from keepmoney.bot import kartlar
from keepmoney.bot.gonderici import bekleyenleri_gonder
from keepmoney.models import Alert, Product, User, Watch


@pytest.fixture
def db(motor):
    s = sessionmaker(bind=motor)()
    yield s
    s.close()


class SahtePostaci:
    """Gerçek Telegram yerine — tüm akış ağa çıkmadan doğrulanır."""

    def __init__(self, basarili: bool = True):
        self.basarili = basarili
        self.gonderilenler: list[tuple[str, str]] = []

    async def gonder(self, chat_id: str, metin: str) -> bool:
        self.gonderilenler.append((chat_id, metin))
        return self.basarili


def urun(db, ad="Ürün", fiyat=None, puan=None):
    p = Product(ad=ad, guncel_fiyat=fiyat, guncel_satici="Mağaza", puan=puan)
    db.add(p)
    db.commit()
    return p


def izleme(db, urun_, hedef=None, aktif=True):
    u = db.query(User).first()
    if u is None:
        u = User(email="a@x.com", password_hash="x", telegram_chat_id="99")
        db.add(u)
        db.commit()
    w = Watch(user_id=u.id, product_id=urun_.id, hedef_fiyat=hedef, aktif=aktif)
    db.add(w)
    db.commit()
    return w


# ─────────────────────── mesaj kurucular ───────────────────────

def test_karsilama_bagli_degilse_yonlendirir():
    metin = kartlar.karsilama(False)
    assert "Ayarlar" in metin
    assert "Chat ID kopyalaman gerekmiyor" in metin


def test_karsilama_bagliysa_epostayi_gosterir():
    assert "a@x.com" in kartlar.karsilama(True, "a@x.com")


def test_baglama_basarisiz_yeni_baglanti_soyler():
    assert "10 dakika" in kartlar.baglama_basarisiz()


def test_liste_bos():
    assert "Henüz takip ettiğin ürün yok" in kartlar.liste_metni([])


def test_liste_hedeftekileri_basa_alir(db):
    """Kullanıcı önce fırsatı görsün."""
    uzak = izleme(db, urun(db, "Uzak", fiyat=1000), hedef=500)
    yakin = izleme(db, urun(db, "Hedefte", fiyat=400), hedef=500)
    metin = kartlar.liste_metni([uzak, yakin])
    assert metin.index("Hedefte") < metin.index("Uzak")
    assert "🎯" in metin


def test_liste_hedefe_kalani_gosterir(db):
    w = izleme(db, urun(db, "Ürün", fiyat=1000), hedef=800)
    assert "→" in kartlar.liste_metni([w])


def test_durum_metni_sayar(db):
    a = izleme(db, urun(db, "A", fiyat=400), hedef=500)     # hedefte
    b = izleme(db, urun(db, "B", fiyat=1000), hedef=500)
    c = izleme(db, urun(db, "C", fiyat=None))               # okunamayan
    metin = kartlar.durum_metni([a, b, c])
    assert "İzlenen ürün: 3" in metin
    assert "Hedefte: 1" in metin
    assert "Henüz okunamayan: 1" in metin


def test_urun_karti_yorumu_tasir(db):
    w = izleme(db, urun(db, "Ekran Kartı", fiyat=45000, puan=4.5), hedef=50000)
    metin = kartlar.urun_karti(w, None, "🟢 Son 90 günün en düşüğü.")
    assert "Ekran Kartı" in metin
    assert "HEDEFTE" in metin
    assert "🟢 Son 90 günün en düşüğü." in metin
    assert "⭐ 4.5" in metin


def test_urun_karti_uzun_adi_kirpar(db):
    w = izleme(db, urun(db, "A" * 200, fiyat=100))
    assert "…" in kartlar.urun_karti(w, None, "x")


# ─────────────────────── klavyeler ───────────────────────

def test_callback_verisi_64_bayti_asmaz():
    """Aşan düğme Telegram'da SESSİZCE çalışmaz — sınır testle korunuyor."""
    for satir in kartlar.urun_klavyesi(999999, True):
        for dugme in satir:
            assert kartlar.callback_gecerli_mi(dugme["callback_data"])

    for satir in kartlar.hedef_secim_klavyesi(999999, 1234567.89):
        for dugme in satir:
            assert kartlar.callback_gecerli_mi(dugme["callback_data"])


def test_hedef_klavyesi_yuzdelik_kisayollar():
    satirlar = kartlar.hedef_secim_klavyesi(1, 10000)
    metinler = [d["text"] for s in satirlar for d in s]
    assert any("%3" in m for m in metinler)
    assert any("%10" in m for m in metinler)
    assert any("Elle" in m for m in metinler)


def test_hedef_klavyesi_fiyat_yoksa_sadece_elle():
    satirlar = kartlar.hedef_secim_klavyesi(1, None)
    assert len(satirlar) == 1
    assert "Elle" in satirlar[0][0]["text"]


def test_duraklat_dugmesi_duruma_gore_degisir():
    # [2]: BACKLOG E5'in %15 düğmesi araya bir satır eklediği için
    # duraklat/sil satırı [1]'den [2]'ye kaydı.
    aktif = kartlar.urun_klavyesi(1, True)[2][0]["text"]
    pasif = kartlar.urun_klavyesi(1, False)[2][0]["text"]
    assert "Duraklat" in aktif
    assert "Devam" in pasif


def test_callback_coz():
    assert kartlar.callback_coz("hs:12:45000") == ("hs", ["12", "45000"])


# ─────────────────────── uyarı gönderici ───────────────────────

@pytest.mark.asyncio
async def test_bekleyen_uyari_gonderilir(db):
    u = User(email="a@x.com", password_hash="x", telegram_chat_id="12345")
    db.add(u)
    db.commit()
    db.add(Alert(user_id=u.id, tur="HEDEF", baslik="🎯 Ürün",
                 mesaj="45.000 TL — hedefin altında"))
    db.commit()

    postaci = SahtePostaci()
    assert await bekleyenleri_gonder(db, postaci) == 1
    assert postaci.gonderilenler[0][0] == "12345"
    assert "🎯 Ürün" in postaci.gonderilenler[0][1]
    assert db.query(Alert).one().telegram_gonderildi is True


@pytest.mark.asyncio
async def test_ayni_uyari_iki_kez_gonderilmez(db):
    u = User(email="a@x.com", password_hash="x", telegram_chat_id="1")
    db.add(u)
    db.commit()
    db.add(Alert(user_id=u.id, tur="DIP", baslik="b", mesaj="m"))
    db.commit()

    postaci = SahtePostaci()
    await bekleyenleri_gonder(db, postaci)
    assert await bekleyenleri_gonder(db, postaci) == 0
    assert len(postaci.gonderilenler) == 1


@pytest.mark.asyncio
async def test_gonderim_basarisizsa_bayrak_cevrilmez(db):
    """Sonraki turda yeniden denensin — uyarı kaybolmamalı."""
    u = User(email="a@x.com", password_hash="x", telegram_chat_id="1")
    db.add(u)
    db.commit()
    db.add(Alert(user_id=u.id, tur="HEDEF", baslik="b", mesaj="m"))
    db.commit()

    assert await bekleyenleri_gonder(db, SahtePostaci(basarili=False)) == 0
    assert db.query(Alert).one().telegram_gonderildi is False

    # Telegram düzelince gönderilir
    assert await bekleyenleri_gonder(db, SahtePostaci()) == 1


@pytest.mark.asyncio
async def test_telegram_baglamamis_kullanici_atlanir(db):
    """Uyarı web'de duruyor; her turda yeniden denenmesin diye bayrak çevrilir."""
    u = User(email="a@x.com", password_hash="x", telegram_chat_id=None)
    db.add(u)
    db.commit()
    db.add(Alert(user_id=u.id, tur="HEDEF", baslik="b", mesaj="m"))
    db.commit()

    postaci = SahtePostaci()
    assert await bekleyenleri_gonder(db, postaci) == 0
    assert postaci.gonderilenler == []
    assert db.query(Alert).one().telegram_gonderildi is True


@pytest.mark.asyncio
async def test_tur_basina_limit(db):
    u = User(email="a@x.com", password_hash="x", telegram_chat_id="1")
    db.add(u)
    db.commit()
    for i in range(10):
        db.add(Alert(user_id=u.id, tur="HEDEF", baslik=f"b{i}", mesaj="m"))
    db.commit()

    assert await bekleyenleri_gonder(db, SahtePostaci(), limit=4) == 4
    assert db.query(Alert).filter(
        Alert.telegram_gonderildi.is_(False)).count() == 6


# ─────────────────── Markdown enjeksiyonu ───────────────────

def test_urun_adindaki_markdown_kacirilir(db):
    """Ürün adı KAZINMIŞ HTML'den gelir — saldırganın kontrolünde.
    Kaçırılmazsa mağaza sayfası bot mesajına kimlik avı köprüsü sokabilir."""
    w = izleme(db, urun(db, "[BEDAVA](https://kotu.site) *ürün*", fiyat=100))
    metin = kartlar.urun_karti(w, None, "yorum")
    assert "\\[BEDAVA\\]" in metin
    assert "\\*ürün\\*" in metin
    # Ham köprü sözdizimi kalmamalı
    assert "[BEDAVA](https://kotu.site)" not in metin


def test_liste_metninde_de_kacirilir(db):
    w = izleme(db, urun(db, "Ürün `kod` _italik_", fiyat=100))
    metin = kartlar.liste_metni([w])
    assert "\\`kod\\`" in metin
    assert "\\_italik\\_" in metin


def test_md_kacir_tum_ozel_karakterleri_kapsar():
    assert kartlar.md_kacir("_*`[]") == "\\_\\*\\`\\[\\]"


def test_normal_metin_bozulmaz():
    assert kartlar.md_kacir("Kingston Beast 32GB DDR5") == "Kingston Beast 32GB DDR5"


# ── Pazar derinliği: iki yüz AYNI bilgiyi göstermeli ─────────────
# Kullanıcı Telegram'dan "dip bölgesi" mesajı alıp web'de "tek satıcı
# belirgin ucuz" uyarısını görüyorsa, bilgiyi eksik veren yüz güveni bozar.

class _SahteKaynak:
    def __init__(self, satici_sayisi=None, ikinci_fiyat=None, son_fiyat=None):
        self.satici_sayisi = satici_sayisi
        self.ikinci_fiyat = ikinci_fiyat
        self.son_fiyat = son_fiyat


class _SahteUrun:
    def __init__(self, sources, ad="Test Ürün", guncel_fiyat=40000.0):
        self.sources = sources
        self.ad = ad
        self.guncel_fiyat = guncel_fiyat
        self.guncel_satici = None
        self.puan = None
        self.yorum_sayisi = None


class _SahteIzleme:
    def __init__(self, urun):
        self.product = urun
        self.hedef_fiyat = None


def test_kartta_pazar_derinligi_gorunur():
    urun = _SahteUrun([_SahteKaynak(satici_sayisi=14, ikinci_fiyat=41500.0,
                                    son_fiyat=38999.0)])
    metin = kartlar.urun_karti(_SahteIzleme(urun), None, "yorum")
    assert "14 satıcı" in metin
    assert "41.500" in metin


def test_kartta_aykiri_fiyat_uyarisi_cikar():
    """Web'deki uyarının Telegram karşılığı."""
    urun = _SahteUrun([_SahteKaynak(satici_sayisi=9, ikinci_fiyat=52000.0,
                                    son_fiyat=4000.0)])
    metin = kartlar.urun_karti(_SahteIzleme(urun), None, "yorum")
    assert "Tek satıcı belirgin ucuz" in metin


def test_makul_farkta_uyari_cikmaz():
    urun = _SahteUrun([_SahteKaynak(satici_sayisi=9, ikinci_fiyat=46000.0,
                                    son_fiyat=40000.0)])
    metin = kartlar.urun_karti(_SahteIzleme(urun), None, "yorum")
    assert "belirgin ucuz" not in metin


def test_pazar_verisi_yoksa_satir_hic_cikmaz():
    """Toplayıcı olmayan üründe boş bir '🏪' satırı gürültüdür."""
    urun = _SahteUrun([_SahteKaynak()])
    assert "🏪" not in kartlar.urun_karti(_SahteIzleme(urun), None, "yorum")


# ── Link ile ürün ekleme (telefondan asıl kullanım) ───────────────
#
# Bot ürünü listeliyor, hedefini değiştiriyor, susturuyor ve siliyordu ama
# EKLEYEMİYORDU: telefondayken yeni ürün için bilgisayara gitmek gerekiyordu.


@pytest.mark.parametrize("metin, beklenen_url, beklenen_hedef", [
    ("https://magaza.com/urun", "https://magaza.com/urun", None),
    ("https://magaza.com/urun 45000", "https://magaza.com/urun", 45000.0),
    # Kullanıcı fiyatı SİTEDEKİ GİBİ yazar: binlik nokta, kuruş virgül.
    ("https://magaza.com/urun 45.000", "https://magaza.com/urun", 45000.0),
    ("https://magaza.com/urun 45.000,50", "https://magaza.com/urun", 45000.5),
    ("https://magaza.com/urun 45000,50", "https://magaza.com/urun", 45000.5),
    # Telegram linki cümlenin içine gömüyor.
    ("şuna bak https://magaza.com/urun fiyatı düştü", "https://magaza.com/urun", None),
    # Takip parametreleri korunur: kanonik URL'yi `izleme_svc` üretiyor.
    ("https://magaza.com/u?utm_source=x", "https://magaza.com/u?utm_source=x", None),
])
def test_link_ve_hedef_ayiklanir(metin, beklenen_url, beklenen_hedef):
    url, hedef = kartlar.link_ve_hedef(metin)
    assert url == beklenen_url
    assert hedef == beklenen_hedef


def test_sifir_hedef_yok_sayilir():
    """`gt=0` doğrulaması serviste var; bot da anlamsız değeri hiç göndermesin."""
    _, hedef = kartlar.link_ve_hedef("https://magaza.com/urun 0")
    assert hedef is None


def test_eklendi_metni_fiyatin_sonra_gelecegini_soyler(db):
    """Ürünü ekleyen istek sayfayı ÇEKMEZ (K56); bunu söylemezsek kullanıcı
    fiyat görünmeyince ürünü bozuk sanar."""
    w = izleme(db, urun(db, "Ekran Kartı"), hedef=45000)
    metin = kartlar.eklendi_metni(w, 45000)
    assert "Takibe alındı" in metin
    assert "Ekran Kartı" in metin
    assert "45.000,00" in metin
    assert "birkaç dakika" in metin


def test_eklendi_metni_hedefsiz_de_calisir(db):
    w = izleme(db, urun(db, "Kulaklık"))
    metin = kartlar.eklendi_metni(w, None)
    assert "Takibe alındı" in metin
    assert "Hedef" not in metin


def test_yardim_link_yapistirmayi_anlatir():
    """Yardım metni "siteye link yapıştır" diyordu — bot ekleyemediği için
    doğruydu. Artık ekleyebiliyor; metin de onu söylemeli."""
    assert "linki buraya yapıştır" in kartlar.YARDIM


@pytest.mark.parametrize("metin, eslesmeli", [
    ("https://magaza.com/u", True),
    ("şuna bak https://magaza.com/u fiyatı düştü", True),   # cümle içinde
    ("bak:\nhttps://magaza.com/u", True),                   # ikinci satırda
    ("ekran kartı", False),                                 # arama olmalı
    ("/liste", False),                                      # komut olmalı
])
def test_link_filtresi_gomulu_baglantiyi_de_yakalar(metin, eslesmeli):
    """Handler filtresi ile ayıklayıcı AYNI deseni kullanmalı.

    Önce `F.text.regexp(...)` kullanılıyordu ve ÖLÇÜLDÜ: aiogram onu
    `re.match` ile uyguluyor, yani deseni metnin başına sabitliyor. Cümle
    içine gömülü link — Telegram'da en yaygın biçim — handler'a hiç
    ulaşmıyor, arama handler'ına düşüp "ürün bulamadım" cevabı alıyordu.
    """
    from types import SimpleNamespace

    from aiogram import F

    filtre = F.text.func(lambda t: bool(kartlar.LINK.search(t or ""))).resolve
    assert bool(filtre(SimpleNamespace(text=metin))) is eslesmeli


# ── Ölü düğme koruması ────────────────────────────────────────────


def test_her_dugmenin_handleri_var():
    """Klavyeler `dr:` (Duraklat) ve `he:` (Elle yaz) üretiyordu ama bu iki
    kodun HANDLER'I YOKTU: kullanıcı basıyor, Telegram dönen çarkı gösterip
    susuyordu. "JSX'te düğme var" ile "düğme çalışıyor" arasındaki farkın bot
    tarafındaki hâli.

    Bu test iki listeyi karşılaştırıyor: klavyelerin ÜRETTİĞİ kodlar ve
    dispatcher'ın KAYITLI olduğu kodlar. Yeni bir düğme eklenip handler'ı
    unutulursa burası kırmızıya döner.
    """
    import pathlib
    import re

    kok = pathlib.Path(__file__).resolve().parents[1] / "keepmoney" / "bot"
    uretilen = set(re.findall(r'callback_data": f"([a-z]+):',
                              (kok / "kartlar.py").read_text(encoding="utf-8")))
    islenen = set(re.findall(r'F\.data\.startswith\("([a-z]+):',
                             (kok / "uygulama.py").read_text(encoding="utf-8")))

    assert uretilen, "klavyelerde hiç callback bulunamadı — desen değişmiş olabilir"
    eksik = uretilen - islenen
    assert not eksik, f"handler'ı olmayan düğme kodları: {sorted(eksik)}"


def test_duraklat_dugmesi_durumu_yansitir():
    """Basınca metin değişmeli: 'Duraklat' ↔ 'Devam ettir'."""
    aktifken = kartlar.urun_klavyesi(1, aktif=True)
    duraklatilmisken = kartlar.urun_klavyesi(1, aktif=False)
    def metinler(klavye):
        return [d["text"] for satir in klavye for d in satir]

    assert any("Duraklat" in t for t in metinler(aktifken))
    assert any("Devam ettir" in t for t in metinler(duraklatilmisken))


# ── Yüzde düşüş kısayolu (BACKLOG E5) ──────────────────────────────


def test_urun_klavyesi_yuzde_dugmesini_uretir():
    klavye = kartlar.urun_klavyesi(7, aktif=True)
    kodlar = [d["callback_data"] for satir in klavye for d in satir]
    assert "yz:7:15" in kodlar


@pytest.mark.asyncio
async def test_yuzde_dugmesi_dusus_yuzdesini_kurar_ve_webde_gorunur(motor, db, monkeypatch):
    """Kabul ölçütü: "bottan kurulan kural webde görünüyor".

    Handler'ın içindeki tek iş `izleme_svc.guncelle(..., dusus_yuzdesi=...)`
    çağrısı — web PATCH'inin (BACKLOG E3, `IzlemeGuncelleIstegi`) kullandığı
    AYNI fonksiyon, aynı `GUNCELLENEBILIR` beyaz listesi (MIMARI K13). Web
    ucunun bu alanı doğru serileştirdiği kendi testleriyle zaten kanıtlı
    (E3/E4 — `izlemeler.py::detay()`); burada asıl doğrulanması gereken BOT
    tarafının doğru alanı doğru değerle DB'ye yazdığı. Bu dosyada başka
    hiçbir test bir `uygulama.py` handler'ını doğrudan çalıştırmıyor (yalnız
    `test_her_dugmenin_handleri_var` statik bir eşleşme kontrolü) — burada
    gerçekten çalıştırıyoruz çünkü ölçüt "DB'ye yazıldı", "kod eşleşiyor" değil.

    Handler kendi `SessionLocal()`ını açıyor (bkz. `db.py` — üretim kodu DI
    almıyor); bu, test fikstürünün `db` oturumundan FARKLI bir bağlantı
    demek. `motor` StaticPool bellek-içi motoru, `uygulama.SessionLocal`ı
    ona yamamak testin ve handler'ın AYNI şemaya yazıp okumasını sağlıyor
    (bkz. test_baglam_doldur.py'deki aynı desen)."""
    from types import SimpleNamespace

    from sqlalchemy.orm import sessionmaker

    from keepmoney.bot import uygulama

    monkeypatch.setattr(uygulama, "SessionLocal", sessionmaker(bind=motor))

    w = izleme(db, urun(db, "Ürün", fiyat=1000))
    cevaplar: list[tuple[str | None, bool]] = []

    async def cevapla(text=None, show_alert=False):
        cevaplar.append((text, show_alert))

    cb = SimpleNamespace(
        data=f"yz:{w.id}:15",
        message=SimpleNamespace(chat=SimpleNamespace(id="99")),
        answer=cevapla,
    )

    await uygulama.yuzde_dususu(cb)

    db.expire_all()
    assert db.query(Watch).filter(Watch.id == w.id).one().dusus_yuzdesi == 15
    assert cevaplar == [("%15 düşünce haber vereceğim", False)]


# ── Elle hedef girişi (ForceReply akışı) ──────────────────────────


def test_hedef_istegi_urun_kimligini_tasir():
    """Durum süreç belleğinde TUTULMUYOR: hangi ürün olduğu, kullanıcının
    yanıtladığı mesajın içinde duruyor. Bot yeniden başlasa da akış bozulmaz."""
    metin = kartlar.hedef_iste_metni(42)
    assert kartlar.hedef_isteginden_id(metin) == 42


def test_baska_mesaja_verilen_yanit_hedef_sayilmaz():
    """Kullanıcı rastgele bir mesajı yanıtlarsa hedef yazılmamalı."""
    assert kartlar.hedef_isteginden_id("merhaba #42") is None
    assert kartlar.hedef_isteginden_id("") is None


@pytest.mark.parametrize("metin, beklenen", [
    ("45000", 45000.0),
    ("45.000", 45000.0),
    ("45.000,50", 45000.5),
    ("45000,5", 45000.5),
    (" 45000 ₺ ", 45000.0),
    ("45000 TL", 45000.0),
    ("bilmiyorum", None),
    ("", None),
    ("0", None),          # anlamsız hedef
    ("-5", None),
])
def test_sayi_cozumu(metin, beklenen):
    assert kartlar.sayi_coz(metin) == beklenen


def test_hedef_kondu_metni_kalan_farki_soyler(db):
    w = izleme(db, urun(db, "Ekran Kartı", fiyat=50000), hedef=45000)
    metin = kartlar.hedef_kondu_metni(w, 45000)
    assert "45.000,00" in metin
    assert "kaldı" in metin


def test_hedef_kondu_metni_hedefteyse_soyler(db):
    w = izleme(db, urun(db, "Kulaklık", fiyat=4000), hedef=5000)
    assert "HEDEFTE" in kartlar.hedef_kondu_metni(w, 5000)

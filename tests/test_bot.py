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
    aktif = kartlar.urun_klavyesi(1, True)[1][0]["text"]
    pasif = kartlar.urun_klavyesi(1, False)[1][0]["text"]
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

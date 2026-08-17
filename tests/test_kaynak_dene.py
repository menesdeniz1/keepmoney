"""`betikler/kaynak_dene.py` tanı aracının testi.

NEDEN TEST EDİLİYOR: Bu betik canlıya alma kararının dayanağı. "Seçiciler
çalışıyor mu" sorusunu bu araç cevaplayacak; aracın kendisi yanlışsa yanlış
bir güvenle canlıya çıkılır — en pahalı hata türü. Ayrıca betikler genelde
test edilmediği için sessizce çürür: kod tabanında bir fonksiyon adı
değişince `python betikler/...` ancak biri elle çalıştırdığında patlar.

Gerçek HTTP sunucusuna, gerçek çekme zinciriyle koşuyor (requests yolu —
tarayıcı gerekmez). Dış ağa çıkılmaz.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from typing import ClassVar

import pytest

from keepmoney import aglar

BETIK = pathlib.Path(__file__).resolve().parents[1] / "betikler" / "kaynak_dene.py"


def _betigi_yukle():
    """Betik paket içinde değil; dosya yolundan modül olarak yüklenir."""
    spec = importlib.util.spec_from_file_location("kaynak_dene", BETIK)
    modul = importlib.util.module_from_spec(spec)
    # `sys.modules`e ÖNCE eklenir: `@dataclass` sınıfın modülünü buradan
    # arıyor ve bulamazsa çözümleme sırasında patlıyor.
    sys.modules["kaynak_dene"] = modul
    spec.loader.exec_module(modul)                       # type: ignore[union-attr]
    return modul


kd = _betigi_yukle()


FIYATLI = """<!doctype html>
<html><head><title>Ekran Kartı RTX 5080</title>
<script type="application/ld+json">
{"@type":"Product","name":"Ekran Kartı RTX 5080",
 "offers":{"price":"48999.90","priceCurrency":"TRY"}}
</script></head><body><div>48.999,90 TL</div></body></html>"""

# Fiyat YOK — ne JSON-LD ne de tanınabilir bir tutar. Aracın "okunamadı"
# demesi gereken durum.
FIYATSIZ = """<!doctype html>
<html><head><title>Kampanya</title></head>
<body><p>Bu sayfada ürün yok.</p></body></html>"""


class _Islemci(BaseHTTPRequestHandler):
    sayfalar: ClassVar[dict[str, str]] = {}

    def do_GET(self):
        govde = self.sayfalar.get(self.path)
        if govde is None:
            self.send_response(404)
            self.end_headers()
            return
        ham = govde.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(ham)))
        self.end_headers()
        self.wfile.write(ham)

    def log_message(self, *a):
        pass


@pytest.fixture
def sunucu():
    _Islemci.sayfalar = {"/urun": FIYATLI, "/bos": FIYATSIZ}
    s = HTTPServer(("127.0.0.1", 0), _Islemci)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()
    s.server_close()


@pytest.fixture
def yerel_ag_serbest(monkeypatch):
    """Yalnızca loopback'i 'halka açık' say — SSRF koruması kaldırılmıyor."""
    gercek = aglar._ip_halka_acik_mi
    monkeypatch.setattr(
        aglar, "_ip_halka_acik_mi",
        lambda ip: True if str(ip) == "127.0.0.1" else gercek(ip))


@pytest.fixture
def arac(monkeypatch):
    """Betiğin çalıştırıcıları — throttle beklemesi testte sıfırlanır."""
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
    cekici = kd.HttpCekici(zaman_asimi=10)
    yield cekici, kd.RobotsKapisi(), kd.HostThrottle()
    cekici.kapat()


# ── Tek URL denemesi ────────────────────────────────────────────
def test_fiyat_okunan_sayfa_basarili(sunucu, yerel_ag_serbest, arac):
    sonuc, html = kd._dene(*arac, f"{sunucu}/urun")
    assert sonuc.basarili
    assert sonuc.fiyat == 48999.90
    assert sonuc.guven == "json-ld"
    assert sonuc.baslik == "Ekran Kartı RTX 5080"
    assert sonuc.sorun is None
    assert html is not None


def test_fiyat_okunamayan_sayfa_sebep_veriyor(sunucu, yerel_ag_serbest, arac):
    sonuc, html = kd._dene(*arac, f"{sunucu}/bos")
    assert not sonuc.basarili
    # Sebep, düzeltmenin NEREDE yapılacağını söylemeli — "hata" demek yetmez.
    assert "fiyat okunamadı" in sonuc.sorun
    assert html is not None            # seçici yazmak için sayfa lazım


def test_olu_sayfa_basarisiz(sunucu, yerel_ag_serbest, arac):
    sonuc, _ = kd._dene(*arac, f"{sunucu}/yok-boyle-bir-sey")
    assert not sonuc.basarili


def test_robots_yasagi_ag_istegi_yapmadan_durdurur(sunucu, arac, monkeypatch):
    cekici, robots, throttle = arac
    monkeypatch.setattr(robots, "izin_var_mi", lambda url: False)
    monkeypatch.setattr(
        cekici, "cek",
        lambda *a, **k: pytest.fail("robots yasakken çekim YAPILMAMALI"))
    sonuc, html = kd._dene(cekici, robots, throttle, f"{sunucu}/urun")
    assert not sonuc.basarili
    assert "robots" in sonuc.sorun
    assert html is None


def test_ssrf_korumasi_yamasiz_calisiyor(sunucu, arac):
    """Yerel ağ yaması OLMADAN: koruma devrede, çekim reddedilir."""
    sonuc, _ = kd._dene(*arac, f"{sunucu}/urun")
    assert not sonuc.basarili


# ── Link listesi ────────────────────────────────────────────────
def test_linkler_tekillestirilir_ve_yorumlar_atlanir(tmp_path):
    dosya = tmp_path / "linkler.txt"
    dosya.write_text(
        "# yorum satırı\n"
        "https://a.com/1\n"
        "\n"
        "  https://a.com/2  \n"
        "https://a.com/1\n", encoding="utf-8")

    args = SimpleNamespace(url=["https://a.com/1"], dosya=str(dosya))
    assert kd._linkleri_oku(args) == ["https://a.com/1", "https://a.com/2"]


def test_linkler_uretimdeki_kanonik_haline_cevrilir(tmp_path):
    """Tarayıcıdan kopyalanan ham link değil, sistemin ÇEKTİĞİ URL denenmeli.

    Aynı ürüne giden iki kampanya linki tek çekime inmeli — yoksa araç aynı
    sayfayı iki kez çeker ve raporda iki satır olarak sayar.
    """
    dosya = tmp_path / "linkler.txt"
    dosya.write_text(
        "https://www.amazon.com.tr/x/dp/B01/ref=pd_lpo/262-370?pd_rd_i=B99\n"
        "https://www.amazon.com.tr/x/dp/B01\n", encoding="utf-8")

    args = SimpleNamespace(url=[], dosya=str(dosya))
    assert kd._linkleri_oku(args) == ["https://amazon.com.tr/x/dp/B01"]


# ── Uçtan uca: main() ───────────────────────────────────────────
def _ham_linkler(args) -> list[str]:
    """Kanoniklestirmeyi atlar.

    `url_normalize` şemayı `https`e zorluyor — üretimde DOĞRU davranış ama
    testin yerel HTTP sunucusuna erişilemez hale getirir. Kanoniklestirmenin
    kendisi yukarıda ayrıca test ediliyor; buradaki testler main()'in rapor
    ve çıkış kodu davranışını ölçüyor.
    """
    return list(args.url)
def test_main_hepsi_okunursa_sifir_doner(sunucu, yerel_ag_serbest, monkeypatch,
                                         capsys):
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
    monkeypatch.setattr(kd, "_linkleri_oku", _ham_linkler)
    monkeypatch.setattr("sys.argv", ["kaynak_dene.py", f"{sunucu}/urun"])
    assert kd.main() == 0
    cikti = capsys.readouterr().out
    assert "OKUMA ORANI: 1/1" in cikti
    assert "%100" in cikti


def test_main_okunamayan_varsa_bir_doner(sunucu, yerel_ag_serbest, monkeypatch,
                                         capsys):
    """Çıkış kodu ANLAMLI olmalı: CI'da eşik olarak kullanılabilsin."""
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
    monkeypatch.setattr(kd, "_linkleri_oku", _ham_linkler)
    monkeypatch.setattr(
        "sys.argv", ["kaynak_dene.py", f"{sunucu}/urun", f"{sunucu}/bos"])
    assert kd.main() == 1
    cikti = capsys.readouterr().out
    assert "OKUMA ORANI: 1/2" in cikti
    assert "Düzeltilecekler:" in cikti
    assert f"{sunucu}/bos" in cikti


def test_main_html_kaydeder(sunucu, yerel_ag_serbest, monkeypatch, tmp_path):
    dizin = tmp_path / "hatalar"
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
    monkeypatch.setattr(kd, "_linkleri_oku", _ham_linkler)
    monkeypatch.setattr("sys.argv", [
        "kaynak_dene.py", f"{sunucu}/bos", "--html-kaydet", str(dizin)])
    assert kd.main() == 1
    kaydedilen = list(dizin.glob("*.html"))
    assert len(kaydedilen) == 1
    assert "Bu sayfada ürün yok" in kaydedilen[0].read_text(encoding="utf-8")


def test_main_basarili_sayfanin_htmlini_kaydetmez(sunucu, yerel_ag_serbest,
                                                  monkeypatch, tmp_path):
    """Yalnızca SORUNLU sayfa kaydedilir — çalışan siteler disk doldurmasın."""
    dizin = tmp_path / "hatalar"
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
    monkeypatch.setattr(kd, "_linkleri_oku", _ham_linkler)
    monkeypatch.setattr("sys.argv", [
        "kaynak_dene.py", f"{sunucu}/urun", "--html-kaydet", str(dizin)])
    assert kd.main() == 0
    assert list(dizin.glob("*.html")) == []


def test_rapor_site_basina_dokum_veriyor(sunucu, yerel_ag_serbest, monkeypatch,
                                         capsys):
    """Genel oran tek başına yetmez: hangi site kırık, görünmeli."""
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
    monkeypatch.setattr(kd, "_linkleri_oku", _ham_linkler)
    monkeypatch.setattr(
        "sys.argv", ["kaynak_dene.py", f"{sunucu}/urun", f"{sunucu}/bos"])
    kd.main()
    cikti = capsys.readouterr().out
    assert "Site başına:" in cikti
    assert "KISMİ" in cikti
    assert "Fiyat nereden geldi: json-ld=1" in cikti


# ── --incele: kaydedilmiş HTML'i ağa çıkmadan çözümleme ─────────
# Seçici yazarken gereken döngü budur: sayfayı bir kez kaydet, sonra ağa
# çıkmadan defalarca çözümle. Aksi halde her denemede siteye istek atılır ve
# tam da doğrulama yaparken IP yasaklanır.

AMAZON_KABUK = """<html><head><title>HyperX Cloud III S</title></head><body>
  <div id="corePriceDisplay_desktop_feature_div"></div>
  <div id="corePrice_desktop">
    <span class="a-price"><span class="a-offscreen">15.049,00\xa0TL</span></span>
  </div></body></html>"""

AMAZON_CAPTCHA = """<html><head><title>Amazon.com.tr</title></head><body>
  <form action="/errors/validateCaptcha"></form></body></html>"""


def test_incele_fiyati_bulunca_sifir_doner(tmp_path, capsys):
    dosya = tmp_path / "amazon.com.tr-1.html"
    dosya.write_text(AMAZON_KABUK, encoding="utf-8")
    assert kd.incele(dosya) == 0
    cikti = capsys.readouterr().out
    assert "15.049,00" in cikti
    assert "secici" in cikti


def test_incele_hangi_secicinin_tuttugunu_gosterir(tmp_path, capsys):
    """Asıl değeri bu: 'tutmadı' demek yetmez, HANGİSİ tutmadı belli olmalı."""
    dosya = tmp_path / "amazon.com.tr-1.html"
    dosya.write_text(AMAZON_KABUK, encoding="utf-8")
    kd.incele(dosya)
    cikti = capsys.readouterr().out
    assert "corePriceDisplay_desktop_feature_div span.a-price .a-offscreen  → 0" in cikti
    assert "+ #corePrice_desktop" in cikti


def test_incele_captcha_sayfasini_ayirt_eder(tmp_path, capsys):
    """Yanlış teşhis pahalıdır: engelli sayfada seçici aranmaz."""
    dosya = tmp_path / "amazon.com.tr-2.html"
    dosya.write_text(AMAZON_CAPTCHA, encoding="utf-8")
    assert kd.incele(dosya) == 1
    cikti = capsys.readouterr().out
    assert "BOT KORUMASI" in cikti
    assert "Güven zinciri" not in cikti      # boşuna seçici denemesin


def test_incele_site_dosya_adindan_bulunur(tmp_path, capsys):
    """Kaydedilen ad `<domain>-<hash>.html`; kural ondan çözülmeli."""
    dosya = tmp_path / "amazon.com.tr-94749959.html"
    dosya.write_text(AMAZON_KABUK, encoding="utf-8")
    kd.incele(dosya)
    assert "Site  : amazon.com.tr" in capsys.readouterr().out


def test_incele_fiyat_tasiyan_elemanlari_listeler(tmp_path, capsys):
    """Seçici tutmadığında bir sonraki adımı SÖYLEMELİ: fiyat nerede duruyor."""
    dosya = tmp_path / "bilinmeyen.com-1.html"
    dosya.write_text(
        '<html><head><title>X</title></head><body>'
        '<div id="urun-kutusu"><span class="price-now">2.499,00 TL</span></div>'
        '</body></html>', encoding="utf-8")
    kd.incele(dosya)
    cikti = capsys.readouterr().out
    assert "2,499.00" in cikti
    assert "urun-kutusu" in cikti


def test_incele_aga_cikmaz(tmp_path, monkeypatch):
    """Çözümleme tamamen çevrimdışı olmalı."""
    monkeypatch.setattr(
        kd.HttpCekici, "cek",
        lambda *a, **k: pytest.fail("--incele ağa ÇIKMAMALI"))
    dosya = tmp_path / "amazon.com.tr-1.html"
    dosya.write_text(AMAZON_KABUK, encoding="utf-8")
    kd.incele(dosya)


# ── Sponsorlu kutu uyarısı ──────────────────────────────────────
# Gerçek bir Amazon sayfasında ana fiyat JS ile geliyordu ve HTML'deki TEK
# fiyatlar `sp_detail_<ASIN>` reklam kutularındaydı. O listeye bakıp seçici
# yazmak, 15.049 TL'lik bir reklamı bu ürünün fiyatı sanmak demekti — ve hata
# SESSİZ olurdu: fiyat okunur, grafik çizilir, "dibe vurdu" uyarısı gider.

AMAZON_SADECE_SPONSORLU = """<html><head><title>HyperX Cloud III S</title></head>
<body><div id="sp_detail">
  <div id="sp_detail_B09ZLRD7Z9"><span class="a-price-whole">15.049,00 TL</span></div>
  <div id="sp_detail_B08TTZVNNH"><span class="a-price-whole">1.099,00 TL</span></div>
</div></body></html>"""


def test_incele_sponsorlu_kutuyu_isaretler(tmp_path, capsys):
    dosya = tmp_path / "amazon.com.tr-3.html"
    dosya.write_text(AMAZON_SADECE_SPONSORLU, encoding="utf-8")
    assert kd.incele(dosya) == 1
    cikti = capsys.readouterr().out
    assert cikti.count("BAŞKA ÜRÜN") == 2
    assert "TÜM fiyatlar sponsorlu" in cikti


def test_incele_gercek_fiyati_yabanci_saymaz(tmp_path, capsys):
    """Yanlış pozitif olmamalı: ana fiyat kutusu uyarı almamalı."""
    dosya = tmp_path / "amazon.com.tr-4.html"
    dosya.write_text(AMAZON_KABUK, encoding="utf-8")
    kd.incele(dosya)
    assert "BAŞKA ÜRÜN" not in capsys.readouterr().out


@pytest.mark.parametrize(("kimlik", "atalar", "beklenen"), [
    ("a-price-whole", ["sp_detail_B09Z", "sp_detail"], True),
    ("price", ["sponsored-products"], True),
    ("fiyat", ["benzer-urunler"], True),
    ("a-offscreen", ["corePrice_desktop"], False),
    ("price-current", ["urun-detay"], False),
])
def test_yabanci_kutu_tespiti(kimlik, atalar, beklenen):
    assert kd._baska_urun_mu(kimlik, atalar) is beklenen


# ── Toplayıcıda pazar derinliği doğrulaması ─────────────────────
# Bu seçiciler çalışmazsa koruma katmanının "tek satıcı aykırı ucuz" ölçütü
# SESSİZCE devre dışı kalır ve geçmişi olmayan ürün savunmasız olur. Tanı
# aracı bunu göstermezse kimse fark etmez.

AKAKCE = """<html><head><title>RTX 5070 Ti fiyatları</title></head><body>
<span class="pt_v8">38.999,00 TL</span>
<ul id="PL">
  <li><img alt="UcuzSepet"><span class="pt_v8">38.999,00 TL</span></li>
  <li><img alt="Vatan"><span class="pt_v8">41.500,00 TL</span></li>
</ul></body></html>"""


def test_incele_pazar_derinligini_gosterir(tmp_path, capsys):
    dosya = tmp_path / "akakce.com-1.html"
    dosya.write_text(AKAKCE, encoding="utf-8")
    kd.incele(dosya)
    cikti = capsys.readouterr().out
    assert "Pazar derinliği" in cikti
    assert "UcuzSepet" in cikti
    assert "41.500,00" in cikti


def test_incele_kirik_satici_secicisini_uyarir(tmp_path, capsys):
    """Sessiz devre dışı kalma en kötüsü — açıkça söylenmeli."""
    dosya = tmp_path / "akakce.com-2.html"
    dosya.write_text(AKAKCE.replace('id="PL"', 'id="degisti"'), encoding="utf-8")
    kd.incele(dosya)
    assert "koruma ölçütü devre dışı" in capsys.readouterr().out


def test_incele_toplayici_olmayanda_pazar_bolumu_cikmaz(tmp_path, capsys):
    dosya = tmp_path / "amazon.com.tr-9.html"
    dosya.write_text(AMAZON_KABUK, encoding="utf-8")
    kd.incele(dosya)
    assert "Pazar derinliği" not in capsys.readouterr().out


# ── Dosya adı güvenliği (Windows CI'da yakalandı) ────────────────

@pytest.mark.parametrize(("domain", "yasak"), [
    ("127.0.0.1:61749", ":"),          # port — NTFS'te alternate data stream
    ("mağaza.com", "ğ"),               # ASCII dışı
    ("a/b\\c.com", "/"),               # yol ayracı
    ('a"b<c>d|e.com', '"'),            # Windows'ta yasak karakterler
])
def test_dosya_adi_tehlikeli_karakter_tasimaz(domain, yasak):
    """Dış girdiden doğrudan dosya adı üretmek platforma bağlı olarak
    SESSİZCE bozuluyor: Windows'ta `host:port.html` içerik `host` dosyasının
    gizli bir akışına yazılıyor — hata yok, 'kaydedildi' yazıyor, dosya yok."""
    ad = kd._dosya_adi(domain, "https://x/y")
    assert yasak not in ad
    assert ad.endswith(".html")


def test_dosya_adi_ayirt_edici_kalir():
    """Temizleme aşırıya kaçıp iki farklı sitenin adını AYNI yapmamalı."""
    a = kd._dosya_adi("magaza.com", "https://magaza.com/1")
    b = kd._dosya_adi("magaza.com", "https://magaza.com/2")
    assert a != b                      # farklı URL → farklı dosya
    assert "magaza.com" in a


def test_dosya_adi_uzunlugu_sinirli():
    """Çok uzun host, dosya sistemi sınırını aşmamalı."""
    ad = kd._dosya_adi("a" * 300, "https://x/y")
    assert len(ad) < 100

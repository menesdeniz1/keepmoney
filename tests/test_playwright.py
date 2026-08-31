"""Playwright yolunun GERÇEK entegrasyon testi.

Bu dosya bir boşluğu kapatıyor: `_playwright` kod yolu uzun süre bir kez bile
çalıştırılmamıştı (paket isteğe bağlı, ortamda kurulu değildi). Yani JS ile
fiyat yükleyen siteler — `render: true` olan akakçe, trendyol vb. — için
yazılmış her şey teoriydi. SSRF route süzgeci de dahil.

Burada gerçek Chromium açılır ve yerelde çalışan gerçek bir HTTP sunucusuna
gider. Dış ağa çıkılmaz.

Playwright ya da tarayıcı yoksa test ATLANIR — isteğe bağlı bağımlılık
yüzünden CI kırılmaz.
"""
from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from keepmoney import aglar
from keepmoney.ayarlar import ayarlar
from keepmoney.cekici import HttpCekici

pytest.importorskip("playwright", reason="playwright isteğe bağlı bağımlılık")

# Tarayıcı nereden bulunacak?
#   • Ortam değişkeni verilmişse o yol (bu geliştirme kabında /opt altında
#     hazır bir chromium var, yeniden indirmenin anlamı yok).
#   • Boş/tanımsızsa Playwright kendi indirdiğini bulur (CI böyle çalışır).
# İkisi de yoksa test ATLANIR; testin içinde tarayıcı İNDİRMEYİZ.
CHROMIUM = os.environ.get("KEEPMONEY_PLAYWRIGHT_CALISTIRILABILIR", "").strip()
if CHROMIUM and not os.path.exists(CHROMIUM):
    pytest.skip(f"chromium bulunamadı: {CHROMIUM}", allow_module_level=True)
if not CHROMIUM and os.path.exists("/opt/pw-browsers/chromium"):
    CHROMIUM = "/opt/pw-browsers/chromium"


def _tarayici_var_mi() -> bool:
    """Playwright kendi tarayıcısını bulabiliyor mu?"""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


if not CHROMIUM and not _tarayici_var_mi():
    pytest.skip("kullanılabilir chromium yok", allow_module_level=True)


# Fiyat yalnızca JS ÇALIŞTIKTAN SONRA DOM'a giriyor: `requests` bu sayfadan
# fiyat okuyamaz, Playwright okuyabilmeli. `render: true`nin varlık sebebi.
JS_ILE_FIYAT = """<!doctype html>
<html><head><title>Yükleniyor…</title></head>
<body><div id="fiyat">yükleniyor</div>
<script>
  document.title = "Ekran Kartı RTX 5080";
  const s = document.createElement('script');
  s.type = 'application/ld+json';
  s.textContent = JSON.stringify({
    "@type": "Product", "name": "Ekran Kartı RTX 5080",
    "offers": {"price": "48999.90", "priceCurrency": "TRY"}
  });
  document.head.appendChild(s);
  document.getElementById('fiyat').textContent = '48.999,90 TL';
</script></body></html>"""

# GEÇ YERLEŞEN FİYAT. Gerçek bir vakada Amazon sayfası 1451 KB olarak geldi,
# başlık ve ürün kolonu yerindeydi, ama fiyat bloğu henüz yoktu: kanıt olarak
# basılan kolon metninde ad, puan, enerji sınıfı ve buybox'ın "güvenli işlem /
# iade politikası" DİPNOTU vardı — buybox render edilmeye başlamış, fiyat
# satırı gelmemişti. Aynı koşuda aynı sitenin altı sayfası sorunsuz okundu;
# mesele seçici değil ZAMANLAMA'ydı ve hatası sessizdi: sayfa dolu gelir,
# fiyat yok.
#
# Burada 2500 ms, testte kullanılan `bekleme_sn: 1`den kasten BÜYÜK: sabit
# bekleme tek başına yetmez, `_fiyati_bekle` devreye girmezse test kırılır.
GEC_GELEN_FIYAT = """<!doctype html>
<html><head><title>MSI Monitör</title></head>
<body><div id="centerCol"><h1>MSI Monitör</h1>
  <div>Güvenli işlem · İade Politikası</div>
  <div id="corePrice_desktop"></div></div>
<script>
  setTimeout(function () {
    document.getElementById('corePrice_desktop').innerHTML =
      '<span class="a-price"><span class="a-offscreen">25.999,00 TL</span></span>';
  }, 2500);
</script></body></html>"""

# Sayfa iç ağdaki bir kaynağı çekmeye çalışıyor — SSRF süzgecinin
# engellemesi gereken şey tam olarak bu.
IC_AGA_ISTEK = """<!doctype html>
<html><head><title>Ürün</title></head><body>
<img src="http://169.254.169.254/latest/meta-data/iam/security-credentials/">
<div>fiyat: 100 TL</div>
</body></html>"""


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
        pass                       # test çıktısını kirletme


@pytest.fixture
def sunucu():
    """Yerelde gerçek HTTP sunucusu. Dönen: taban URL."""
    _Islemci.sayfalar = {"/js": JS_ILE_FIYAT, "/ssrf": IC_AGA_ISTEK,
                        "/gec": GEC_GELEN_FIYAT}
    s = HTTPServer(("127.0.0.1", 0), _Islemci)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()
    s.server_close()


@pytest.fixture
def yerel_ag_serbest(monkeypatch):
    """Mutlu yol için 127.0.0.1'i 'halka açık' say.

    SSRF koruması yerel adresleri DOĞRU biçimde engelliyor; test sunucusu da
    yerelde. Korumayı kaldırmıyoruz — yalnızca bu testte loopback'i geçerli
    sayıyoruz ki gerçek tarayıcı + gerçek çıkarım zinciri sınanabilsin.
    Engelleme davranışı ayrı testte, YAMASIZ olarak doğrulanıyor.
    """
    gercek = aglar._ip_halka_acik_mi
    monkeypatch.setattr(
        aglar, "_ip_halka_acik_mi",
        lambda ip: True if str(ip) == "127.0.0.1" else gercek(ip))


@pytest.fixture
def cekici(monkeypatch):
    if CHROMIUM:
        monkeypatch.setenv("KEEPMONEY_PLAYWRIGHT_CALISTIRILABILIR", CHROMIUM)
    else:
        monkeypatch.delenv("KEEPMONEY_PLAYWRIGHT_CALISTIRILABILIR", raising=False)
    ayarlar.cache_clear()
    c = HttpCekici(zaman_asimi=30)
    yield c
    c.kapat()
    ayarlar.cache_clear()


# ── Mutlu yol: JS ile yüklenen fiyat gerçekten okunuyor mu? ──────

def test_js_ile_yuklenen_fiyat_okunur(sunucu, cekici, yerel_ag_serbest):
    """`render: true` olan siteler tam olarak buna bağlı. Bu doğrulanmadan
    akakçe/trendyol kurallarının çalışacağını varsaymak temelsizdi."""
    from keepmoney import ayikla

    cekim = cekici.cek(f"{sunucu}/js", {"render": True, "bekleme_sn": 1})

    assert cekim.yontem == "playwright", cekim.hata
    assert cekim.http_kodu == 200
    assert "48.999,90" in cekim.html

    # Uçtan uca: tarayıcıdan gelen HTML çıkarım zincirinden geçiyor mu?
    c = ayikla.cikar(cekim.html, {"render": True}, 200)
    assert c.fiyat == 48999.90
    assert c.guven == "json-ld"
    assert "RTX 5080" in (c.baslik or "")


def test_requests_ayni_sayfadan_fiyat_okuyamaz(sunucu, yerel_ag_serbest):
    """Kontrol grubu: JS çalışmazsa fiyat YOK. `render: true` gerçekten
    gerekli mi sorusunun cevabı — süs değil."""
    from keepmoney import ayikla

    c = HttpCekici(zaman_asimi=10)
    cekim = c._requests(f"{sunucu}/js")
    assert cekim.http_kodu == 200
    assert ayikla.cikar(cekim.html, {}, 200).fiyat is None


def test_turkce_baslik_bozulmadan_gelir(sunucu, cekici, yerel_ag_serbest):
    cekim = cekici.cek(f"{sunucu}/js", {"render": True, "bekleme_sn": 1})
    assert "Ekran Kartı" in cekim.html


# ── SSRF: route süzgeci gerçek tarayıcıda çalışıyor mu? ─────────

def test_sayfanin_ic_ag_istegi_engellenir(sunucu, cekici, yerel_ag_serbest):
    """Sayfa `169.254.169.254`e (bulut metadata ucu) istek atıyor.

    Bu, `requests` yolunda hiç oluşmayan bir risk: tarayıcı sayfanın ALT
    KAYNAKLARINI da çeker. Süzgeç olmadan sayfaya gömülü tek bir <img>
    sunucuyu iç ağa istek atmaya zorlayabilirdi.

    Sayfanın yüklenmesi TEK BAŞINA hiçbir şey kanıtlamaz (istek engellense
    de engellenmese de sayfa yüklenir). Bu yüzden iptal edilen isteklerin
    listesi doğrudan gözleniyor.
    """
    # Tarayıcıyı önce ısıt: `_sayfa` ilk çekimde oluşuyor, dinleyiciyi
    # ancak ondan sonra bağlayabiliriz.
    cekici.cek(f"{sunucu}/js", {"render": True, "bekleme_sn": 0})

    iptal_edilenler: list[str] = []
    cekici._sayfa.on("requestfailed",
                     lambda i: iptal_edilenler.append(i.url))

    cekim = cekici.cek(f"{sunucu}/ssrf", {"render": True, "bekleme_sn": 2})
    assert cekim.yontem == "playwright", cekim.hata

    # Sayfa yüklenmeli — engellenen YALNIZCA kötü alt istek.
    assert "fiyat: 100 TL" in cekim.html
    assert any("169.254.169.254" in u for u in iptal_edilenler), (
        f"metadata isteği engellenmedi; iptal edilenler: {iptal_edilenler}")


def test_hedefin_kendisi_ic_agdaysa_engellenir(sunucu, cekici):
    """YAMASIZ: burada 127.0.0.1 gerçekten iç ağ sayılır ve çekim
    başlamadan reddedilmeli — tarayıcı hiç açılmamalı."""
    cekim = cekici.cek(f"{sunucu}/js", {"render": True, "bekleme_sn": 1})
    assert cekim.html is None
    assert "guvensiz_hedef" in (cekim.hata or "")


def test_metadata_ucuna_gidilmez(cekici):
    cekim = cekici.cek("http://169.254.169.254/latest/meta-data/",
                       {"render": True})
    assert cekim.html is None
    assert "guvensiz_hedef" in (cekim.hata or "")


# ── Ayar gerçekten uygulanıyor mu? ──────────────────────────────

def test_sistem_chromiumu_kullaniliyor(cekici, sunucu, yerel_ag_serbest):
    """Ayar okunmasaydı Playwright kendi indirdiği sürümü arar ve
    'Executable doesn't exist' ile düşerdi."""
    assert ayarlar().playwright_calistirilabilir == (CHROMIUM or None)
    cekim = cekici.cek(f"{sunucu}/js", {"render": True, "bekleme_sn": 1})
    assert cekim.html is not None, cekim.hata


# ── Geç yerleşen fiyat ──────────────────────────────────────────
# Sabit bekleme "yavaş olan sayfa" diye bir şeyi hesaba katmıyordu ve hatası
# SESSİZDİ: sayfa dolu gelir, fiyat yoktur, rapor "fiyat okunamadı" der ve
# kimse zamanlamadan şüphelenmez — seçici aranır, oysa seçici doğrudur.

AMAZON_KURALI = {
    "render": True,
    "bekleme_sn": 1,                       # fiyat 2500 ms'de geliyor
    "fiyat_secici": "#corePrice_desktop span.a-price .a-offscreen",
}


def test_sabit_beklemeden_sonra_gelen_fiyat_yakalanir(sunucu, cekici,
                                                      yerel_ag_serbest):
    from keepmoney import ayikla

    cekim = cekici.cek(f"{sunucu}/gec", AMAZON_KURALI)

    assert cekim.yontem == "playwright", cekim.hata
    assert "25.999,00" in cekim.html
    c = ayikla.cikar(cekim.html, AMAZON_KURALI, 200)
    assert c.fiyat == 25999.0
    assert c.guven == "secici"


def test_sabit_bekleme_tek_basina_yetmiyordu(sunucu, cekici, yerel_ag_serbest):
    """Kontrol grubu: düzeltme olmadan bu sayfa fiyatsız gelirdi.

    `fiyat_secici` verilmezse `_fiyati_bekle` beklemez — yani eski davranış.
    Bu test kırmızıya dönerse sayfa artık hızlanmış demektir ve üstteki test
    de anlamını yitirmiştir.
    """
    from keepmoney import ayikla

    cekim = cekici.cek(f"{sunucu}/gec", {"render": True, "bekleme_sn": 1})
    assert ayikla.cikar(cekim.html, AMAZON_KURALI, 200).fiyat is None


def test_fiyati_olmayan_sayfa_ek_beklemeden_sonra_yine_doner(sunucu, cekici,
                                                             yerel_ag_serbest,
                                                             monkeypatch):
    """Fiyatı GERÇEKTEN olmayan sayfa hata değil: sessizce devam edilmeli.

    Aksi halde tükenmiş bir ürün, düzeltilecek bir arıza gibi raporlanırdı.
    """
    from keepmoney import cekici as c_mod
    monkeypatch.setattr(c_mod, "FIYAT_EK_BEKLEME_SN", 1)   # testi bekletmesin

    cekim = cekici.cek(f"{sunucu}/ssrf",
                       {"render": True, "bekleme_sn": 1,
                        "fiyat_secici": "#asla-olmayan-secici"})
    assert cekim.yontem == "playwright", cekim.hata
    assert cekim.html                                       # gövde YİNE geldi


# ── Çöken tarayıcıdan toparlanma ─────────────────────────────────
#
# ÖLÇÜLDÜ (düzeltmeden önce): tarayıcı bir kez çöktüğünde art arda üç çekim
# de `TargetClosedError` verdi ve süreç KENDİNİ TOPARLAMADI. `HttpCekici`
# tarayıcıyı süreç ömrü boyunca yeniden kullanıyor (`_playwright_baslat`,
# `_sayfa` doluysa erken dönüyor) ve çöken örneği kimse temizlemiyordu.
#
# Üretimdeki karşılığı ağır: `render: true` isteyen siteler — Amazon,
# Trendyol, akakçe, n11, Hepsiburada, cimri, tebilon, yani pazarın çoğu —
# worker ELLE yeniden başlatılana kadar hiç okunmaz. Süreç ölmediği için
# `restart: unless-stopped` da devreye girmez: konteyner sağlıklı görünür,
# tarama durur.

def test_coken_tarayici_sonraki_cekimde_yeniden_aciliyor(
        sunucu, cekici, yerel_ag_serbest):
    """Asıl regresyon. Çökme BİR çekime mal olur, kalıcı arızaya değil."""
    ilk = cekici._playwright(f"{sunucu}/js", {"render": True})
    assert ilk.html, f"ilk çekim başarısız: {ilk.hata}"

    # Gerçek çökmenin taklidi: tarayıcı ayağımızın altından kapanıyor.
    cekici._sayfa.context.browser.close()

    cokerken = cekici._playwright(f"{sunucu}/js", {"render": True})
    assert cokerken.html is None, "çökme anındaki çekim başarısız olmalı"

    sonraki = cekici._playwright(f"{sunucu}/js", {"render": True})
    assert sonraki.html, (
        "tarayıcı çökmesinden sonra toparlanmadı — worker elle yeniden "
        f"başlatılana kadar render:true siteler okunamaz. Hata: {sonraki.hata}")


def test_saglam_tarayici_hata_sonrasi_ATILMIYOR(sunucu, cekici,
                                                yerel_ag_serbest):
    """Ayrımın diğer yarısı: tek bir bozuk sayfa ya da zaman aşımı yüzünden
    chromium'u yeniden başlatmak, düzelttiğinden çok maliyet getirirdi.
    Var olmayan bir yol 404 verir; tarayıcı sağlamdır ve KORUNMALI."""
    assert cekici._playwright(f"{sunucu}/js", {"render": True}).html
    onceki_sayfa = cekici._sayfa

    cekici._playwright(f"{sunucu}/olmayan-yol", {"render": True})

    assert cekici._sayfa is onceki_sayfa, (
        "sağlam tarayıcı gereksiz yere kapatıldı")


# ── Tarayıcı yenileme: sınırsız bellek büyümesi ──────────────────
#
# ÖLÇÜLDÜ (düzeltmeden önce): tek chromium sayfası yeniden kullanılarak 60
# gezinme yapıldı, RSS 366 MB'den 761 MB'ye çıktı — gezinme başına ~6,6 MB,
# PLATO YOK, büyüme baştan sona doğrusal. 35 ürünün saatlik taranmasında
# günde ~5,5 GB demek: `tarayici` konteyneri bir günü doldurmadan OOM.
#
# Düzeltmeden sonra aynı ölçüm 120 gezinmede 367-510 MB bandında kaldı.
# Buradaki test bellek ÖLÇMÜYOR (kırılgan olurdu) — MEKANİZMAYI ölçüyor:
# sayaç eşiğe gelince tarayıcı gerçekten atılıyor ve yenisi açılıyor mu.

def test_tarayici_belirli_gezinmeden_sonra_YENILENIYOR(sunucu, cekici,
                                                       yerel_ag_serbest,
                                                       monkeypatch):
    """Eşik testte küçültülüyor: 40 gezinme koşturmak testi yavaşlatırdı,
    ölçülen şey sayacın davranışı."""
    from keepmoney import cekici as modul

    monkeypatch.setattr(modul, "AZAMI_GEZINME", 3)

    assert cekici._playwright(f"{sunucu}/js", {"render": True}).html
    ilk_sayfa = cekici._sayfa
    assert cekici._gezinme == 1

    cekici._playwright(f"{sunucu}/js", {"render": True})
    cekici._playwright(f"{sunucu}/js", {"render": True})
    assert cekici._sayfa is ilk_sayfa, "eşiğe gelmeden yenilenmemeli"
    assert cekici._gezinme == 3

    # 4. çekim: eşik aşıldı → tarayıcı yenilenir
    sonuc = cekici._playwright(f"{sunucu}/js", {"render": True})
    assert sonuc.html, "yenileme çekimi başarısız olmamalı"
    assert cekici._sayfa is not ilk_sayfa, "tarayıcı yenilenmedi"
    assert cekici._gezinme == 1, "sayaç yeni tarayıcıda sıfırdan başlamalı"


def test_yenileme_kesintisiz_calisiyor(sunucu, cekici, yerel_ag_serbest,
                                       monkeypatch):
    """Yenileme kullanıcıya HATA olarak yansımamalı: tarama turu ortasında
    tarayıcı değişse de o turdaki her çekim başarılı dönmeli."""
    from keepmoney import cekici as modul

    monkeypatch.setattr(modul, "AZAMI_GEZINME", 2)
    for _ in range(7):
        sonuc = cekici._playwright(f"{sunucu}/js", {"render": True})
        assert sonuc.html, f"yenileme sırasında çekim düştü: {sonuc.hata}"


def test_kapatinca_sayac_sifirlaniyor(sunucu, cekici, yerel_ag_serbest):
    """Aksi hâlde çökme sonrası açılan taze tarayıcı, eski sayaçla hemen
    yeniden kapatılırdı."""
    cekici._playwright(f"{sunucu}/js", {"render": True})
    assert cekici._gezinme == 1
    cekici.kapat()
    assert cekici._gezinme == 0

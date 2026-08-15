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


# ── Uçtan uca: main() ───────────────────────────────────────────
def test_main_hepsi_okunursa_sifir_doner(sunucu, yerel_ag_serbest, monkeypatch,
                                         capsys):
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
    monkeypatch.setattr("sys.argv", ["kaynak_dene.py", f"{sunucu}/urun"])
    assert kd.main() == 0
    cikti = capsys.readouterr().out
    assert "OKUMA ORANI: 1/1" in cikti
    assert "%100" in cikti


def test_main_okunamayan_varsa_bir_doner(sunucu, yerel_ag_serbest, monkeypatch,
                                         capsys):
    """Çıkış kodu ANLAMLI olmalı: CI'da eşik olarak kullanılabilsin."""
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
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
    monkeypatch.setattr("sys.argv", [
        "kaynak_dene.py", f"{sunucu}/urun", "--html-kaydet", str(dizin)])
    assert kd.main() == 0
    assert list(dizin.glob("*.html")) == []


def test_rapor_site_basina_dokum_veriyor(sunucu, yerel_ag_serbest, monkeypatch,
                                         capsys):
    """Genel oran tek başına yetmez: hangi site kırık, görünmeli."""
    monkeypatch.setattr(kd.HostThrottle, "bekle", lambda self, host: 0.0)
    monkeypatch.setattr(
        "sys.argv", ["kaynak_dene.py", f"{sunucu}/urun", f"{sunucu}/bos"])
    kd.main()
    cikti = capsys.readouterr().out
    assert "Site başına:" in cikti
    assert "KISMİ" in cikti
    assert "Fiyat nereden geldi: json-ld=1" in cikti

"""robots.txt kapısı testleri — gerçek ağ YOK.

SAHTELEME HTTP SEVİYESİNDE. Bu bilinçli bir değişiklik: eskiden `_oku`
yamalanıyordu, yani "indirme başarısız olursa ne olur" sorusunun cevabı hiç
sınanmıyordu. Sonuç, gerçek bir denemede görüldü — Hepsiburada ve n11
robots.txt'nin KENDİSİNE 403 döndüğünde `urllib.robotparser` sessizce
`disallow_all = True` yapıyor ve Türkiye'nin en büyük iki pazaryeri
"robots.txt yasaklıyor" diye eleniyordu. Oysa o siteler hiçbir şey
yasaklamamıştı.

Ders: sahtelemeyi ne kadar yukarıda yaparsan, altında kalan davranışı o
kadar sınamamış olursun.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from keepmoney.robots import BOT_ADI, RobotsKapisi


class _Yanit(SimpleNamespace):
    """requests.Response'un bu modülün kullandığı yüzeyi."""


def _yanit(metin: str = "", kod: int = 200) -> _Yanit:
    return _Yanit(status_code=kod, text=metin)


def kapi(metin: str | None = "", kod: int = 200, patlasin: bool = False,
         **kw) -> tuple[RobotsKapisi, list[dict]]:
    """robots.txt'yi sahte bir HTTP yanıtıyla veren kapı + istek kaydı."""
    import keepmoney.robots as modul

    k = RobotsKapisi(**kw)
    istekler: list[dict] = []

    def sahte_get(url, **kwargs):
        istekler.append({"url": url, **kwargs})
        if patlasin:
            raise OSError("ağ yok")
        return _yanit(metin or "", kod)

    modul.requests.get = sahte_get            # `_requests_geri_al` geri alır
    return k, istekler


@pytest.fixture(autouse=True)
def _requests_geri_al():
    """Modül düzeyinde yamalanan `requests.get` her testten sonra geri alınır."""
    import keepmoney.robots as modul
    gercek = modul.requests.get
    yield
    modul.requests.get = gercek


# ── temel davranış ───────────────────────────────────────────────

def test_yasaklanan_yol_engellenir():
    k, _ = kapi("User-agent: *\nDisallow: /sepet\n")
    assert k.izin_var_mi("https://magaza.com/sepet/ekle") is False


def test_serbest_yol_gecer():
    k, _ = kapi("User-agent: *\nDisallow: /sepet\n")
    assert k.izin_var_mi("https://magaza.com/urun/ekran-karti") is True


def test_her_sey_yasaksa_engellenir():
    k, _ = kapi("User-agent: *\nDisallow: /\n")
    assert k.izin_var_mi("https://magaza.com/urun/x") is False


def test_bize_ozel_kural_uygulanir():
    """Site sahibi yalnızca bizi engelleyebilmeli — bu yüzden ayrı bir
    bot adı taşıyoruz."""
    k, _ = kapi(f"User-agent: {BOT_ADI}\nDisallow: /\n\n"
                "User-agent: *\nAllow: /\n")
    assert k.izin_var_mi("https://magaza.com/urun/x") is False


def test_baskasina_yazilan_yasak_bizi_baglamaz():
    k, _ = kapi("User-agent: KotuBot\nDisallow: /\n")
    assert k.izin_var_mi("https://magaza.com/urun/x") is True


# ── durum kodu politikası (RFC 9309) ─────────────────────────────
# Bu blok gerçek bir hatadan doğdu. `RobotFileParser.read()` 401/403'te
# `disallow_all = True` yapıyor (1996 taslağı). RFC 9309 §2.3.1.3 ise 4xx'i
# "kısıtlama BEYAN EDİLMEMİŞ" sayar. Fark, ürünün yarısını sebepsiz kapatmak
# ile açık tutmak arasındaydı.

@pytest.mark.parametrize("kod", [401, 403, 404, 410, 451])
def test_dosya_alinamiyorsa_kisitlama_yok(kod):
    """4xx = beyan yok. 403 çoğu zaman WAF'ın bilinmeyen istemciyi elemesidir,
    sitenin taramaya dair bir kararı değil."""
    k, _ = kapi(kod=kod)
    assert k.izin_var_mi("https://hepsiburada.com/urun-p-HBCV0001") is True


@pytest.mark.parametrize("kod", [429, 500, 502, 503])
def test_gecici_hatada_izin_verilir_ama_kisa_onbelleklenir(kod):
    """Beş dakikalık bir sunucu arızası bir günlük veri kaybına dönüşmemeli."""
    k, istekler = kapi(kod=kod)
    assert k.izin_var_mi("https://magaza.com/urun/x") is True
    # Kısa önbellek: ömür dolduğunda yeniden denenmeli.
    import keepmoney.robots as modul
    modul.HATA_ONBELLEK_SN = 0
    try:
        k.izin_var_mi("https://magaza.com/urun/y")
    finally:
        modul.HATA_ONBELLEK_SN = 15 * 60
    assert len(istekler) >= 1


def test_ag_hatasinda_izin_verilir():
    k, _ = kapi(patlasin=True)
    assert k.izin_var_mi("https://magaza.com/urun/x") is True


def test_200_gelen_kurallar_AYNEN_uygulanir():
    """Politikanın sınırı: dosya OKUNABİLİYORSA yasak yasaktır.

    Bu test, 4xx esnekliğinin 'robots.txt'yi umursama'ya kaymadığını korur.
    """
    k, _ = kapi("User-agent: *\nDisallow: /urun\n", kod=200)
    assert k.izin_var_mi("https://magaza.com/urun/x") is False


# ── kimlik ───────────────────────────────────────────────────────

def test_kendimizi_durustce_tanitiyoruz():
    """Tarayıcı taklidi burada YANLIŞ olurdu: robots.txt okumanın bütün
    anlamı açık kimlikle davranmaktır. Ayrıca `Python-urllib/3.x` kimliği
    WAF'lı sitelerde 403 yiyor ve kuralları hiç okuyamıyorduk."""
    k, istekler = kapi("User-agent: *\nAllow: /\n")
    k.izin_var_mi("https://magaza.com/urun/x")
    ua = istekler[0]["headers"]["User-Agent"]
    assert BOT_ADI in ua
    assert "http" in ua              # iletişim adresi taşımalı
    assert "Mozilla" not in ua       # tarayıcı taklidi YOK


def test_robots_adresi_dogru_kuruluyor():
    k, istekler = kapi("User-agent: *\nAllow: /\n")
    k.izin_var_mi("https://magaza.com/derin/yol/urun?x=1")
    assert istekler[0]["url"] == "https://magaza.com/robots.txt"


# ── kararsızlıkta izin ver ───────────────────────────────────────

def test_bos_robots_izin_verir():
    k, _ = kapi("")
    assert k.izin_var_mi("https://magaza.com/urun/x") is True


def test_bozuk_robots_izin_verir():
    k, _ = kapi("bu geçerli bir robots.txt değil {{{ ]]]")
    assert k.izin_var_mi("https://magaza.com/urun/x") is True


@pytest.mark.parametrize("url", ["", "bu-url-değil", "/yalnizca/yol"])
def test_ayristirilamayan_url_izin_verir(url):
    k, _ = kapi("User-agent: *\nDisallow: /\n")
    assert k.izin_var_mi(url) is True


def test_ic_ag_adresi_robots_indirmeye_calismaz():
    """robots.txt de bir dış istektir; SSRF kapısından geçmeli. Asıl
    engelleme zaten çekim anında yapılıyor."""
    k, istekler = kapi("User-agent: *\nDisallow: /\n")
    assert k.izin_var_mi("http://169.254.169.254/latest/") is True
    assert istekler == []               # istek HİÇ yapılmamalı


# ── önbellek ─────────────────────────────────────────────────────

def test_ayni_host_bir_kez_indirilir():
    """Her fiyat okumasında robots.txt indirmek, azaltmaya çalıştığımız
    yükü ikiye katlardı."""
    k, istekler = kapi("User-agent: *\nAllow: /\n")
    for n in range(5):
        k.izin_var_mi(f"https://magaza.com/urun/{n}")
    assert len(istekler) == 1


def test_farkli_hostlar_ayri_indirilir():
    k, istekler = kapi("User-agent: *\nAllow: /\n")
    k.izin_var_mi("https://a.com/x")
    k.izin_var_mi("https://b.com/x")
    assert len(istekler) == 2


def test_onbellek_suresi_dolunca_yeniden_okunur():
    k, istekler = kapi("User-agent: *\nAllow: /\n", onbellek_omru=0)
    k.izin_var_mi("https://magaza.com/x")
    k.izin_var_mi("https://magaza.com/y")
    assert len(istekler) == 2

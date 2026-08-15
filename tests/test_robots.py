"""robots.txt kapısı testleri — gerçek ağ YOK.

`urllib.robotparser` ayrıştırmasını gerçek metinlerle sınıyoruz; indirme
adımı sahtelenmiş durumda.
"""
from __future__ import annotations

import urllib.robotparser

import pytest

from keepmoney.robots import BOT_ADI, RobotsKapisi


def kapi(robots_metni: str | None, **kw) -> RobotsKapisi:
    """robots.txt içeriği verilmiş bir kapı. None = indirilemedi."""
    k = RobotsKapisi(**kw)

    def sahte_oku(self, taban):
        if robots_metni is None:
            return None
        o = urllib.robotparser.RobotFileParser()
        o.parse(robots_metni.splitlines())
        return o

    k._oku = sahte_oku.__get__(k, RobotsKapisi)
    return k


# ── temel davranış ───────────────────────────────────────────────

def test_yasaklanan_yol_engellenir():
    k = kapi("User-agent: *\nDisallow: /sepet\n")
    assert k.izin_var_mi("https://magaza.com/sepet/ekle") is False


def test_serbest_yol_gecer():
    k = kapi("User-agent: *\nDisallow: /sepet\n")
    assert k.izin_var_mi("https://magaza.com/urun/ekran-karti") is True


def test_her_sey_yasaksa_engellenir():
    k = kapi("User-agent: *\nDisallow: /\n")
    assert k.izin_var_mi("https://magaza.com/urun/x") is False


def test_bize_ozel_kural_uygulanir():
    """Site sahibi yalnızca bizi engelleyebilmeli — bu yüzden ayrı bir
    bot adı taşıyoruz."""
    k = kapi(f"User-agent: {BOT_ADI}\nDisallow: /\n\n"
             "User-agent: *\nAllow: /\n")
    assert k.izin_var_mi("https://magaza.com/urun/x") is False


def test_baskasina_yazilan_yasak_bizi_baglamaz():
    k = kapi("User-agent: KotuBot\nDisallow: /\n")
    assert k.izin_var_mi("https://magaza.com/urun/x") is True


# ── kararsızlıkta izin ver ───────────────────────────────────────

def test_robots_okunamazsa_izin_verilir():
    """Sunucu hatası yüzünden taramayı durdurmak, geçici bir arızayı kalıcı
    veri kaybına çevirir. Beyan yoksa yasak da yoktur."""
    assert kapi(None).izin_var_mi("https://magaza.com/urun/x") is True


def test_bos_robots_izin_verir():
    assert kapi("").izin_var_mi("https://magaza.com/urun/x") is True


def test_bozuk_robots_izin_verir():
    k = kapi("bu geçerli bir robots.txt değil {{{ ]]]")
    assert k.izin_var_mi("https://magaza.com/urun/x") is True


@pytest.mark.parametrize("url", ["", "bu-url-değil", "/yalnizca/yol"])
def test_ayristirilamayan_url_izin_verir(url):
    assert kapi("User-agent: *\nDisallow: /\n").izin_var_mi(url) is True


def test_ic_ag_adresi_robots_indirmeye_calismaz():
    """robots.txt de bir dış istektir; SSRF kapısından geçmeli. Asıl
    engelleme zaten çekim anında yapılıyor."""
    k = kapi("User-agent: *\nDisallow: /\n")
    assert k.izin_var_mi("http://169.254.169.254/latest/") is True


# ── önbellek ─────────────────────────────────────────────────────

def test_ayni_host_bir_kez_indirilir():
    """Her fiyat okumasında robots.txt indirmek, azaltmaya çalıştığımız
    yükü ikiye katlardı."""
    sayac = []
    k = RobotsKapisi()

    def sahte_oku(self, taban):
        sayac.append(taban)
        o = urllib.robotparser.RobotFileParser()
        o.parse(["User-agent: *", "Allow: /"])
        return o

    k._oku = sahte_oku.__get__(k, RobotsKapisi)

    for n in range(5):
        k.izin_var_mi(f"https://magaza.com/urun/{n}")
    assert len(sayac) == 1


def test_farkli_hostlar_ayri_indirilir():
    sayac = []
    k = RobotsKapisi()

    def sahte_oku(self, taban):
        sayac.append(taban)

    k._oku = sahte_oku.__get__(k, RobotsKapisi)
    k.izin_var_mi("https://a.com/x")
    k.izin_var_mi("https://b.com/x")
    assert len(sayac) == 2


def test_onbellek_suresi_dolunca_yeniden_okunur():
    sayac = []
    k = RobotsKapisi(onbellek_omru=0)

    def sahte_oku(self, taban):
        sayac.append(taban)

    k._oku = sahte_oku.__get__(k, RobotsKapisi)
    k.izin_var_mi("https://magaza.com/x")
    k.izin_var_mi("https://magaza.com/y")
    assert len(sayac) == 2

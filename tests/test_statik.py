"""Derlenmiş arayüzün sunulması (`api/statik.py`).

NEDEN AYRI DOSYA: bu katmanın hiç birim testi yoktu — yalnızca uçtan uca
testlerde dolaylı olarak geçiyordu. Oysa burada üç ayrı güvenlik/doğruluk
kuralı var ve üçü de sessizce bozulabilir:

  1. SPA geri düşüşü `/api/*`yi GÖLGELEMEMELİ (JSON 404 dönmeli),
  2. yol geçişi (`../`) depo dışına ÇIKAMAMALI,
  3. bulunamayan bir DOSYA, index.html değil 404 dönmeli.

Üçü de "çalışıyor gibi görünen" hatalar üretir: ikincisi güvenlik açığı,
diğerleri istemcide anlamsız hata mesajları.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from keepmoney.api.statik import arayuzu_bagla


@pytest.fixture
def derleme(tmp_path: pathlib.Path) -> pathlib.Path:
    """Gerçek bir `npm run build` çıktısının minimum iskeleti."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>KM</title>",
                                         encoding="utf-8")
    (tmp_path / "assets" / "index-a1b2c3.js").write_text("//js", encoding="utf-8")
    (tmp_path / "sw.js").write_text("//servis calisani", encoding="utf-8")
    (tmp_path / "manifest.webmanifest").write_text('{"name":"KM"}',
                                                   encoding="utf-8")
    return tmp_path


@pytest.fixture
def istemci(derleme: pathlib.Path) -> TestClient:
    app = FastAPI()
    assert arayuzu_bagla(app, derleme) is True
    return TestClient(app)


def test_derleme_yoksa_baglanmaz(tmp_path):
    """Yerel geliştirmede `statik/` yoktur; mount edilmemeli."""
    app = FastAPI()
    assert arayuzu_bagla(app, tmp_path) is False


# ── SPA geri düşüşü ───────────────────────────────────────────────


@pytest.mark.parametrize("yol", ["/", "/setler", "/izleme/12", "/ayarlar",
                                 "/boyle-bir-sayfa-yok"])
def test_uygulama_yollari_index_dondurur(istemci, yol):
    """React Router istemcide yönlendiriyor: doğrudan yazılan adres 404
    değil index.html almalı."""
    yanit = istemci.get(yol)
    assert yanit.status_code == 200
    assert "<title>KM</title>" in yanit.text


def test_index_onbelleklenmez(istemci):
    """`index.html` önbelleğe alınırsa kullanıcı yeni sürümü günlerce görmez;
    hash'li varlıklar ise tam tersine uzun önbelleklenebilir."""
    assert istemci.get("/").headers["cache-control"] == "no-cache"


# ── Gerçek dosyalar ───────────────────────────────────────────────


def test_kokteki_dosyalar_dogrudan_sunulur(istemci):
    """`sw.js` ve `manifest.webmanifest` kökte durur; index.html'e düşerse
    servis çalışanı kaydı "unknown error" ile başarısız olur."""
    yanit = istemci.get("/sw.js")
    assert yanit.status_code == 200
    assert "servis calisani" in yanit.text
    assert istemci.get("/manifest.webmanifest").status_code == 200


def test_hashli_varlik_sunulur(istemci):
    assert istemci.get("/assets/index-a1b2c3.js").status_code == 200


# ── Bulunamayan dosya: 404, index.html DEĞİL ──────────────────────


@pytest.mark.parametrize("yol", [
    "/assets/index-ESKIHASH.js",     # dağıtımdan sonra kalan eski parça
    "/sw-eski.js",
    "/favicon.ico",
    "/logo.png",
])
def test_bulunamayan_dosya_404(istemci, yol):
    """index.html dönseydi tarayıcı JS yerine HTML alır ve hata
    "Unexpected token '<'" olarak görünürdü — yani asıl sebebi (dosya yok)
    hiç söylemezdi."""
    yanit = istemci.get(yol)
    assert yanit.status_code == 404
    assert "<title>KM</title>" not in yanit.text


def test_noktali_uygulama_yolu_yoksa_da_404(istemci):
    """Kural "adında nokta var" ölçütüne dayanıyor; uygulamanın rotalarında
    nokta yok (bkz. arayuz/src/App.tsx). Bu test o varsayımı kayda geçiriyor:
    noktalı bir yol eklenirse burası kırmızıya döner ve kural gözden geçirilir."""
    assert istemci.get("/surum-1.2.3").status_code == 404


# ── API gölgelenmemeli ────────────────────────────────────────────


@pytest.mark.parametrize("yol", ["/api/boyle-bir-uc-yok", "/saglik", "/metrics"])
def test_olmayan_api_ucu_404_json(istemci, yol):
    """SPA geri düşüşü API'yi gölgelerse, olmayan uç JSON yerine HTML 200
    döner ve istemci "beklenmeyen yanıt" hatası verir.

    (Bu testteki uygulama çıplak: gerçek API'de `/saglik` ve `/metrics`
    kayıtlıdır. Burada ölçülen, o yolların SPA'ya DÜŞMEMESİ.)"""
    yanit = istemci.get(yol)
    assert yanit.status_code == 404
    assert "<title>KM</title>" not in yanit.text


def test_openapi_semasi_spa_tarafindan_golgelenmez(istemci):
    """FastAPI'nin kendi ucu; SPA yakalarsa API dokümanı HTML'e dönerdi."""
    yanit = istemci.get("/openapi.json")
    assert yanit.status_code == 200
    assert yanit.headers["content-type"].startswith("application/json")


# ── Yol geçişi (güvenlik) ─────────────────────────────────────────


def test_yol_gecisi_engellenir(istemci, derleme):
    """`../` ile derleme dizininin DIŞINA çıkılamamalı."""
    gizli = derleme.parent / "gizli.txt"
    gizli.write_text("sır", encoding="utf-8")

    for yol in ("/../gizli.txt", "/%2e%2e/gizli.txt",
                "/assets/../../gizli.txt", "/..%2fgizli.txt"):
        yanit = istemci.get(yol)
        assert "sır" not in yanit.text, f"{yol} dizin dışına çıktı"

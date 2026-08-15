"""Site kuralları — her mağaza için nasıl okunacağı.

Kurallar koda değil YAML'a yazılır (`siteler/*.yaml`). Sebep: bir site HTML'ini
değiştirdiğinde düzeltme kod değişikliği değil, config değişikliği olmalı —
deploy gerektirmeden, ürünü bilmeyen biri tarafından da yapılabilmeli.

Bir site burada TANIMLI OLMAK ZORUNDA DEĞİL: tanımsız domain varsayılan
kurallarla (json-ld → genel seçiciler → meta → regex) okunur. Config yalnızca
varsayılanın yetmediği yerde gerekir.
"""
from __future__ import annotations

import functools
from pathlib import Path
from urllib.parse import urlparse

import yaml

SITELER_DIZINI = Path(__file__).resolve().parent / "siteler"

VARSAYILAN: dict = {
    "render": False,          # JS gerekiyor mu (Playwright)
    "bekleme_sn": 2,
    "toplayici": False,
}


def host_cikar(url: str) -> str:
    """URL'den normalize host: 'https://www.Amazon.com.tr/dp/X' → 'amazon.com.tr'"""
    try:
        host = (urlparse(url).netloc or "").lower()
    except ValueError:
        return "bilinmiyor"
    host = host.removeprefix("www.")
    return host or "bilinmiyor"


@functools.lru_cache(maxsize=1)
def _tum_kurallar() -> dict[str, dict]:
    """siteler/*.yaml → {domain: kural}. Süreç ömrü boyunca bir kez okunur."""
    out: dict[str, dict] = {}
    if not SITELER_DIZINI.is_dir():
        return out
    for yol in sorted(SITELER_DIZINI.glob("*.yaml")):
        if yol.name.startswith("_"):
            continue                      # _SABLON.yaml gibi örnekler atlanır
        try:
            kural = yaml.safe_load(yol.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        domain = str(kural.get("domain") or "").lower().replace("www.", "")
        if domain:
            out[domain] = kural
    return out


def kural(url_veya_host: str) -> dict:
    """Bir URL ya da host için site kuralı. Tanımsızsa varsayılan döner.

    Alt alan adları üst kurala düşer: 'magaza.trendyol.com' → 'trendyol.com'.
    """
    host = url_veya_host if "://" not in url_veya_host else host_cikar(url_veya_host)
    host = host.lower().removeprefix("www.")
    kurallar = _tum_kurallar()

    if host in kurallar:
        return {**VARSAYILAN, **kurallar[host]}

    for domain, k in kurallar.items():
        if host.endswith("." + domain):
            return {**VARSAYILAN, **k}

    return dict(VARSAYILAN)


def toplayici_mi(url: str) -> bool:
    """Karşılaştırma sitesi mi? Bunlar tek sayfada N satıcının en ucuzunu
    verdiği için tarama bütçesinde önceliklidir."""
    return bool(kural(url).get("toplayici"))


def tanimli_siteler() -> list[str]:
    return sorted(_tum_kurallar())

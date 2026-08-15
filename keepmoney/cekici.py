"""Sayfa çekme — HTTP zinciri.

Bilinçli olarak İNCE tutuldu: burada iş mantığı yok, sadece "URL ver, HTML al".
Tüm karar verme (fiyat güvenilir mi, alarm gitmeli mi) yukarıdaki saf
katmanlarda. Böylece worker, gerçek ağa çıkmadan sahte bir çekiciyle
uçtan uca test edilebiliyor.

ZİNCİR — ucuzdan pahalıya:
    requests       ~1 sn, ihmal edilebilir kaynak      ← siteler'in çoğu
    cloudscraper   ~2 sn, Cloudflare atlatma denemesi
    Playwright     ~8 sn + ~250 MB RAM                 ← SON ÇARE

Playwright oranı bu ürünün maliyetini belirleyen tek sayıdır. Bir siteyi
`render: true` yapmadan önce gerçekten gerekli mi diye bak — varsayılan
zincir çoğu Türk e-ticaret sitesinde JSON-LD sayesinde `requests` ile çalışır.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

VARSAYILAN_ZAMAN_ASIMI = 25

TARAYICI_IZLERI = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
]


@dataclass(frozen=True)
class Cekim:
    """Tek bir çekme denemesinin sonucu."""
    html: str | None = None
    http_kodu: int | None = None
    hata: str | None = None
    yontem: str = "yok"          # requests | cloudscraper | playwright

    @property
    def basarili(self) -> bool:
        return bool(self.html) and self.http_kodu not in (403, 429)

    @property
    def engellendi(self) -> bool:
        return self.http_kodu in (403, 429)


class Cekici(Protocol):
    """Worker'ın bağımlı olduğu tek arayüz. Test sahte bir uygulama verir."""

    def cek(self, url: str, kural: dict) -> Cekim: ...


def _basliklar(url: str) -> dict:
    from urllib.parse import urlparse
    h = {
        "User-Agent": random.choice(TARAYICI_IZLERI),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
    }
    try:
        netloc = urlparse(url).netloc
        if netloc:
            h["Referer"] = f"https://{netloc}/"
    except ValueError:
        pass
    return h


class HttpCekici:
    """Gerçek çekici. Ağır bağımlılıklar (cloudscraper, playwright) TEMBEL
    yüklenir — kurulu değillerse zincir sessizce kısalır, çökmez."""

    def __init__(self, zaman_asimi: int = VARSAYILAN_ZAMAN_ASIMI):
        self.zaman_asimi = zaman_asimi
        self._cloudscraper = None
        self._pw = None
        self._sayfa = None

    def cek(self, url: str, kural: dict | None = None) -> Cekim:
        kural = kural or {}

        if kural.get("render"):
            c = self._playwright(url, kural)
            if c.basarili:
                return c
            # Playwright başarısızsa yine de static dene — bazen JS gerekmiyordur
        c = self._requests(url)
        if c.basarili:
            return c

        if c.engellendi or not c.html:
            cs = self._cloudscraper_cek(url)
            if cs.basarili:
                return cs

        if not kural.get("render"):
            pw = self._playwright(url, kural)
            if pw.basarili:
                return pw

        return c

    # ── katmanlar ────────────────────────────────────────────────

    def _requests(self, url: str) -> Cekim:
        try:
            import requests
        except ImportError:
            return Cekim(hata="requests kurulu değil", yontem="requests")
        try:
            y = requests.get(url, headers=_basliklar(url), timeout=self.zaman_asimi)
            return Cekim(html=y.text, http_kodu=y.status_code, yontem="requests")
        except Exception as e:                       # ağ hatası ölümcül değil
            return Cekim(hata=f"{type(e).__name__}: {e}", yontem="requests")

    def _cloudscraper_cek(self, url: str) -> Cekim:
        try:
            import cloudscraper
        except ImportError:
            return Cekim(hata="cloudscraper kurulu değil", yontem="cloudscraper")
        try:
            if self._cloudscraper is None:
                self._cloudscraper = cloudscraper.create_scraper(
                    browser={"browser": "chrome", "platform": "windows",
                             "desktop": True})
            y = self._cloudscraper.get(url, headers=_basliklar(url),
                                       timeout=self.zaman_asimi)
            return Cekim(html=y.text, http_kodu=y.status_code, yontem="cloudscraper")
        except Exception as e:
            return Cekim(hata=f"{type(e).__name__}: {e}", yontem="cloudscraper")

    def _playwright(self, url: str, kural: dict) -> Cekim:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return Cekim(hata="playwright kurulu değil", yontem="playwright")
        try:
            self._playwright_baslat(sync_playwright)
            yanit = self._sayfa.goto(url, wait_until="domcontentloaded",
                                     timeout=self.zaman_asimi * 1000)
            self._sayfa.wait_for_timeout(int(kural.get("bekleme_sn", 2)) * 1000)
            return Cekim(html=self._sayfa.content(),
                         http_kodu=yanit.status if yanit else None,
                         yontem="playwright")
        except Exception as e:
            return Cekim(hata=f"{type(e).__name__}: {e}", yontem="playwright")

    def _playwright_baslat(self, sync_playwright) -> None:
        if self._sayfa is not None:
            return
        self._pw = sync_playwright().start()
        tarayici = self._pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"])
        baglam = tarayici.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=TARAYICI_IZLERI[0],
            locale="tr-TR",
            timezone_id="Europe/Istanbul",
        )
        self._sayfa = baglam.new_page()
        self._sayfa.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

    def kapat(self) -> None:
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
            self._sayfa = None

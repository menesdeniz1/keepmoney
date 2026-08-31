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
import re
from dataclasses import dataclass, replace
from typing import Protocol
from urllib.parse import urljoin

from .aglar import (
    MAKS_GOVDE_BAYT,
    MAKS_YONLENDIRME,
    GuvensizHedef,
    dogrula,
    guvenli_mi,
)
from .ayarlar import ayarlar
from .gunluk import log as _log

log = _log("keepmoney.cekici")
from .ayikla import engel_mi

VARSAYILAN_ZAMAN_ASIMI = 25

# Sabit beklemeden SONRA fiyat elemanı için tanınan ek süre (bkz.
# `_fiyati_bekle`). Üst sınır: yavaş bir sayfa uğruna tarama bütçesini
# tüketmeyelim — fiyatı GERÇEKTEN olmayan sayfa da var ve o durumda bu süre
# tamamen boşa gider. `render: true` olan sayfalarda en kötü senaryo
# bekleme_sn + bu değer.
FIYAT_EK_BEKLEME_SN = 6

# HTML gövdesinden karakter kodlaması sezme. requests, `Content-Type` başlığı
# charset taşımayan `text/*` yanıtlarında RFC 2616 gereği ISO-8859-1 varsayar;
# Türk e-ticaret sitelerinin çoğu UTF-8 ama charset'i yalnızca <meta> ile
# bildiriyor. Bu varsayıma uyulursa "Ekran Kartı" → "Ekran KartÄ±" olur ve
# bozuk ad kullanıcıya ürün adı diye gösterilir.
_META_KODLAMA = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""", re.IGNORECASE)

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
    # Zincirde DENENEN tüm katmanlar. `yontem` yalnızca döndürülen yanıtın
    # katmanını söylüyor; hiçbiri temiz değilken gövdesi olan İLK deneme
    # dönüyor, yani `yontem="requests"` görünüyor. Bu, "tarayıcı hiç
    # denenmedi" izlenimi veriyordu — tanı sırasında tam olarak bu yanlış
    # sonuca varıldı ve merdiven bozuk sanıldı. Gerçekte üçü de denenmişti.
    denenenler: tuple[str, ...] = ()

    @property
    def basarili(self) -> bool:
        return bool(self.html) and self.http_kodu not in (403, 429)

    @property
    def engellendi(self) -> bool:
        return self.http_kodu in (403, 429)


class Cekici(Protocol):
    """Worker'ın bağımlı olduğu tek arayüz. Test sahte bir uygulama verir."""

    def cek(self, url: str, kural: dict) -> Cekim: ...


def playwright_var_mi() -> bool:
    """Tarayıcı motoru bu süreçte kullanılabilir mi?

    AÇILIŞTA bilinmesi gerekiyor. `render: true` olan bir kural, Playwright
    yokken sessizce `requests`e düşer; o siteden hiç fiyat gelmez ama hiçbir
    yerde "eksik bağımlılık" yazmaz — yalnızca o kaynak hep boş döner.
    Toplayıcılar (akakçe, cimri) ve Trendyol bu kuralı kullanıyor, yani
    maliyeti düşüren bütün strateji sessizce devre dışı kalabiliyordu.
    """
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _kullanilabilir(cekim: Cekim) -> bool:
    """Bu yanıtla devam edilebilir mi — yoksa bir sonraki katmana mı geçilmeli?

    `basarili` yalnızca "gövde var ve kod 403/429 değil" demektir. BOT KORUMA
    SAYFALARI HTTP 200 ve dolu bir gövdeyle geliyor; yani `basarili` onları
    geçerli sayıyor ve zincir ilk basamakta duruyordu. Yükselme merdiveninin
    (cloudscraper → Playwright) VARLIK SEBEBİ tam da bu sayfaları aşmaktı —
    ve hiç devreye girmiyordu.

    Gerçek ölçümde görüldü: iki Shopify mağazası 0,7 saniyede "bot koruması"
    sonucu verdi. O süre tek bir `requests` çağrısıdır; Playwright denenmiş
    olsaydı saniyeler sürerdi. Yani hiç denenmemişti.

    MALİYET: engel tespiti sayfayı ayrıştırıyor. `engel_mi` önce ucuz yapısal
    imzalara bakıyor, ayrıştırma yalnızca onlar tutmazsa oluyor. Temiz bir
    sayfada bu ~100 ms ek yüktür — bot duvarını ürün sayfası sanıp fiyat
    geçmişine yazmanın bedeliyle kıyaslanamaz.
    """
    if not cekim.basarili:
        return False
    return not engel_mi(cekim.html or "")


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


def _pw_istek_suz(route) -> None:
    """Playwright istek süzgeci — iç ağa giden her isteği iptal eder.

    Tarayıcı yönlendirmeleri kendi takip ettiği için `goto` öncesi tek bir
    doğrulama SSRF'i kapatmaz. Bu süzgeç yönlendirme adımları ve sayfanın
    alt kaynakları dahil her isteği görür.
    """
    if guvenli_mi(route.request.url):
        route.continue_()
    else:
        route.abort()


class HttpCekici:
    """Gerçek çekici. Ağır bağımlılıklar (cloudscraper, playwright) TEMBEL
    yüklenir — kurulu değillerse zincir sessizce kısalır, çökmez."""

    def __init__(self, zaman_asimi: int = VARSAYILAN_ZAMAN_ASIMI):
        self.zaman_asimi = zaman_asimi
        self._cloudscraper = None
        self._pw = None
        self._sayfa = None

    def cek(self, url: str, kural: dict | None = None) -> Cekim:
        """Zinciri sırayla dener, İŞE YARAR ilk yanıtı döndürür.

        "İşe yarar" ile "başarılı" farkı kritik (bkz. `_kullanilabilir`):
        bot koruma sayfaları HTTP 200 ve dolu gövdeyle geliyor.
        """
        denemeler: list[Cekim] = []

        kural = kural or {}

        if kural.get("render"):
            c = self._playwright(url, kural)
            if _kullanilabilir(c):
                return c
            denemeler.append(c)
            # Playwright başarısızsa yine de static dene — bazen JS gerekmiyordur

        c = self._requests(url)
        if _kullanilabilir(c):
            return c
        denemeler.append(c)

        cs = self._cloudscraper_cek(url)
        if _kullanilabilir(cs):
            return cs
        denemeler.append(cs)

        if not kural.get("render"):
            pw = self._playwright(url, kural)
            if _kullanilabilir(pw):
                return pw
            denemeler.append(pw)

        # Hiçbiri temiz değil. Gövdesi OLAN ilk yanıtı döndür: yukarıdaki
        # katman engel/ölü sayfa ayrımını ancak HTML'e bakarak yapabilir.
        # Boş bir `Cekim` döndürmek, "engellendik" ile "ağ koptu" arasındaki
        # farkı silerdi — ikisi çok farklı tepkiler gerektiriyor.
        #
        # Denenen katmanların LİSTESİ de taşınıyor: dönen yanıt `requests`
        # olduğu için "tarayıcı hiç denenmedi" sanılıyordu (bkz. `denenenler`).
        tumu = tuple(d.yontem for d in denemeler)
        for d in denemeler:
            if d.html:
                return replace(d, denenenler=tumu)
        if denemeler:
            return replace(denemeler[0], denenenler=tumu)
        return Cekim(hata="hiçbir katman denenmedi")

    # ── katmanlar ────────────────────────────────────────────────

    def _yonlendirmeli_cek(self, getir, url: str, yontem: str) -> Cekim:
        """Yönlendirmeleri ELLE takip eder, her sıçramada SSRF kontrolü yapar.

        `allow_redirects=True` bırakılsaydı halka açık bir URL 302 ile
        169.254.169.254'e sapıp SSRF kontrolünü tamamen atlatabilirdi:
        yalnızca ilk adres doğrulanmış olurdu. Bu döngü `requests` ve
        `cloudscraper` tarafından PAYLAŞILIR — ikisi de `requests.Session`
        arayüzünü sunuyor ve korumanın iki ayrı kopyası olsaydı biri
        kaçınılmaz olarak geride kalırdı (nitekim kalmıştı).
        """
        for _ in range(MAKS_YONLENDIRME + 1):
            dogrula(url)
            y = getir(url, headers=_basliklar(url), timeout=self.zaman_asimi,
                      allow_redirects=False, stream=True)

            if y.is_redirect or y.is_permanent_redirect:
                kod, hedef = y.status_code, y.headers.get("location")
                y.close()
                if not hedef:
                    return Cekim(http_kodu=kod, yontem=yontem)
                url = urljoin(url, hedef)
                continue

            return Cekim(html=self._govde_oku(y), http_kodu=y.status_code,
                         yontem=yontem)

        return Cekim(hata="çok fazla yönlendirme", yontem=yontem)

    def _requests(self, url: str) -> Cekim:
        try:
            import requests
        except ImportError:
            return Cekim(hata="requests kurulu değil", yontem="requests")
        try:
            return self._yonlendirmeli_cek(requests.get, url, "requests")
        except GuvensizHedef as e:
            return Cekim(hata=f"guvensiz_hedef: {e}", yontem="requests")
        except Exception as e:                       # ağ hatası ölümcül değil
            return Cekim(hata=f"{type(e).__name__}: {e}", yontem="requests")

    @staticmethod
    def _kodlama_sec(yanit, ham: bytes) -> str:
        """Başlıkta charset varsa o; yoksa HTML <meta>'sından; o da yoksa UTF-8.

        requests, charset'siz `text/*` yanıtlarda ISO-8859-1 varsayar (RFC
        2616). Türkçe sayfalarda bu doğrudan mojibake demektir, o yüzden bu
        varsayılana güvenilmiyor.
        """
        from requests.utils import get_encoding_from_headers

        basliktan = get_encoding_from_headers(yanit.headers)
        if basliktan and basliktan.lower() != "iso-8859-1":
            return basliktan
        m = _META_KODLAMA.search(ham[:8192])
        if m:
            return m.group(1).decode("ascii", "ignore")
        return basliktan or "utf-8"

    def _govde_oku(self, yanit) -> str:
        """Gövdeyi SINIRLI okur.

        `y.text` tüm gövdeyi belleğe alır; tek bir dev sayfa (ya da sıkıştırma
        bombası) worker'ı düşürür. Sınırı aşan kısım atılır — fiyat sayfanın
        ilk megabaytlarındadır, kaybımız yok.
        """
        parcalar, toplam = [], 0
        for parca in yanit.iter_content(chunk_size=64 * 1024):
            parcalar.append(parca)
            toplam += len(parca)
            if toplam >= MAKS_GOVDE_BAYT:
                break
        yanit.close()
        ham = b"".join(parcalar)
        return ham.decode(self._kodlama_sec(yanit, ham), errors="replace")

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
            # `requests.Session` türevi olduğu için aynı yönlendirme
            # döngüsünü kullanır. Eskiden burada tek bir `dogrula(url)` vardı
            # ve gerisi kütüphaneye bırakılıyordu — yani yönlendirmeyle
            # atlatılabilen açık kapı.
            return self._yonlendirmeli_cek(
                self._cloudscraper.get, url, "cloudscraper")
        except GuvensizHedef as e:
            return Cekim(hata=f"guvensiz_hedef: {e}", yontem="cloudscraper")
        except Exception as e:
            return Cekim(hata=f"{type(e).__name__}: {e}", yontem="cloudscraper")

    def _playwright(self, url: str, kural: dict) -> Cekim:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return Cekim(hata="playwright kurulu değil", yontem="playwright")
        try:
            dogrula(url)
            self._playwright_baslat(sync_playwright)
            yanit = self._sayfa.goto(url, wait_until="domcontentloaded",
                                     timeout=self.zaman_asimi * 1000)
            self._sayfa.wait_for_timeout(int(kural.get("bekleme_sn", 2)) * 1000)
            self._fiyati_bekle(kural)
            return Cekim(html=self._sayfa.content(),
                         http_kodu=yanit.status if yanit else None,
                         yontem="playwright")
        except GuvensizHedef as e:
            return Cekim(hata=f"guvensiz_hedef: {e}", yontem="playwright")
        except Exception as e:
            # ÇÖKEN TARAYICI ATILIR. Tarayıcı süreç ömrü boyunca yeniden
            # kullanılıyor (`_playwright_baslat` `_sayfa` doluysa erken
            # dönüyor) — bu doğru, her sayfa için chromium açmak kabul
            # edilemez. AMA çöktüğünde kimse temizlemiyordu.
            #
            # ÖLÇÜLDÜ: tarayıcı dışarıdan kapatıldıktan sonra art arda üç
            # çekim de `TargetClosedError` verdi ve KENDİNİ TOPARLAMADI.
            # Üretimdeki karşılığı ağır: `render: true` isteyen siteler
            # (Amazon, Trendyol, akakçe, n11, Hepsiburada, cimri, tebilon —
            # yani pazarın çoğu) worker ELLE yeniden başlatılana kadar hiç
            # okunmaz. Süreç ölmediği için `restart: unless-stopped` da
            # devreye girmez: konteyner "sağlıklı" görünürken tarama durur.
            self._cokmusse_at()
            return Cekim(hata=f"{type(e).__name__}: {e}", yontem="playwright")

    def _fiyati_bekle(self, kural: dict) -> None:
        """Sabit beklemeden SONRA, fiyat elemanı hâlâ yoksa biraz daha bekler.

        SABİT SÜRE YETMİYOR. Gerçek bir vakada Amazon sayfası 1451 KB olarak
        geldi, başlık ve `#centerCol` yerindeydi, ama fiyat bloğu HENÜZ
        yerleşmemişti. Kanıt kesindi: ürün kolonunun metninde ad, puan, enerji
        sınıfı ve buybox'ın "güvenli işlem / iade politikası" DİPNOTU vardı —
        yani buybox render edilmeye BAŞLAMIŞ, fiyat satırı gelmemişti. Aynı
        koşuda aynı sitenin altı sayfası sorunsuz okundu; mesele seçici değil,
        ZAMANLAMA. Sabit bekleme "yavaş olan sayfa" diye bir şeyi hesaba
        katmıyor ve hatası da sessiz: sayfa dolu geliyor, fiyat yok.

        SABİT SÜRE KALDIRILMADI, ÜSTÜNE EKLENDİ. Bugün çalışan sayfaların
        davranışı birebir aynı kalmalı: akakçe'nin pazar derinliği seçicileri
        (`#PL > li`) o süre içinde yerleşiyor ve erken anlık görüntü onları
        sessizce kaybettirirdi — yani bir arızayı düzeltirken başka bir
        korumayı kapatırdık.

        Bulunamazsa SESSİZCE devam eder: fiyatı gerçekten olmayan sayfa da
        var (ürün tükenmiş). Burada hata yükseltmek, normal bir durumu arıza
        gibi gösterirdi.
        """
        secici = kural.get("fiyat_secici")
        if not secici:
            return
        try:
            # `state="attached"`: Amazon fiyatı `.a-offscreen` içinde, yani
            # ekran okuyucu için var ama GÖRÜNMEZ. "visible" beklemek her
            # Amazon sayfasında boşuna zaman aşımı demek olurdu.
            self._sayfa.wait_for_selector(secici, state="attached",
                                          timeout=FIYAT_EK_BEKLEME_SN * 1000)
        except Exception:
            pass

    def _playwright_baslat(self, sync_playwright) -> None:
        if self._sayfa is not None:
            return
        self._pw = sync_playwright().start()
        # Sistem chromium'u belirtilmişse onu kullan (bkz. ayarlar).
        secenekler: dict = {
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if yol := ayarlar().playwright_calistirilabilir:
            secenekler["executable_path"] = yol
        tarayici = self._pw.chromium.launch(**secenekler)
        baglam = tarayici.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=TARAYICI_IZLERI[0],
            locale="tr-TR",
            timezone_id="Europe/Istanbul",
        )
        self._sayfa = baglam.new_page()
        self._sayfa.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        # Yönlendirmeleri TARAYICI takip eder; `goto` öncesi tek doğrulama
        # bu yüzden yetmez — sayfa 302 ile iç ağa sapabilir. Ayrıca sayfanın
        # kendi alt istekleri (img/xhr/iframe) de keyfi hedeflere gidebilir.
        # Yönlendirme dahil HER istek burada süzülür.
        self._sayfa.route("**/*", _pw_istek_suz)

    def _cokmusse_at(self) -> None:
        """Tarayıcı hâlâ ayakta mı? Değilse kaynakları bırak — sonraki
        çağrı `_playwright_baslat` ile YENİSİNİ açar.

        Hata SINIFINA bakılmıyor (`TargetClosedError` gibi adlar Playwright
        sürümleri arasında değişiyor); doğrudan bağlantı DURUMU sorgulanıyor.
        Sorgunun kendisi patlıyorsa da cevap zaten "ölü".

        Sağlam tarayıcı ASLA atılmaz: zaman aşımı ya da tek bir bozuk sayfa
        yüzünden chromium'u yeniden başlatmak, düzelttiğinden çok maliyet
        getirirdi.
        """
        if self._sayfa is None:
            return
        try:
            tarayici = self._sayfa.context.browser
            if (tarayici is not None and tarayici.is_connected()
                    and not self._sayfa.is_closed()):
                return
        except Exception:
            pass
        log.warning("Tarayıcı çökmüş — kapatılıyor, sonraki çekimde yeniden açılacak")
        self.kapat()

    def kapat(self) -> None:
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
            self._sayfa = None

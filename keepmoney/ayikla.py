"""HTML'den veri çıkarma — fiyat, puan/yorum, başlık, engel/ölü sayfa tespiti.

GÜVEN ZİNCİRİ: fiyat dört yöntemle aranır ve HANGİSİYLE bulunduğu döner.
Güven seviyesi koruma katmanının (karar.py) girdisidir — düşük güvenli okuma
bildirime dönüşmeden önce ikinci okumayla doğrulanır.

    json-ld  → sitenin kendi yapılandırılmış verisi          EN GÜVENİLİR
    secici   → siteye özel CSS seçici (siteler/*.yaml)
    meta     → og:price / product:price meta etiketi
    regex    → gövdedeki ilk '12.345,67 TL' kalıbı           SON ÇARE

`regex` neden tehlikeli: sayfada ana fiyat yoksa (stok tükendi vb.) sponsorlu
ürün karuselinin fiyatını ana fiyat sanır. Bu yüzden site config'i `metin_alani`
ile regex'in bakacağı DOM alanını daraltabilir; alan sayfada yoksa regex adımı
tamamen ATLANIR — yanlış fiyat okumaktansa "fiyat yok" demek doğrudur.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .fiyat import parse_tl

# Bot koruması / captcha sayfası işaretleri (başlık + gövde başında aranır)
ENGEL_IZLERI = [
    "robot check", "captcha", "erişim engellendi", "access denied",
    "olağandışı trafik", "unusual traffic", "attention required",
    "checking your browser", "doğrulama gerekiyor", "just a moment",
    "güvenlik doğrulaması",
]

# YAPISAL engel imzaları — görünür metinde değil, HAM HTML'de aranır.
#
# Neden ayrı liste: Amazon'un captcha sayfasında görünen tek metin
# "Amazon.com.tr" başlığı ve birkaç satır yönergedir; dili hesabın bölgesine
# göre değişir ve ENGEL_IZLERI'ndeki hiçbir kelimeyi içermez. Sonuç, ilk
# gerçek link denemesinde görüldü: sistem engellendiğini anlamayıp "fiyat
# okunamadı" dedi. Bu YANLIŞ TEŞHİSTİR ve yanlış çözüme götürür — seçici
# yazmaya çalışırsın, oysa yapılması gereken geri çekilmektir. Ayrıca engel
# sayılmadığı için ne throttle cezası ne KAYNAK_BOZUK uyarısı devreye girer.
#
# Form hedefi ve sağlayıcı alan adları dile bağlı değildir; bu yüzden
# metinden çok daha güvenilir imzalardır.
ENGEL_YAPISAL = [
    "/errors/validatecaptcha",     # Amazon
    "captcha-delivery.com",        # DataDome (Trendyol vb.)
    "/cdn-cgi/challenge-platform",  # Cloudflare
    "g-recaptcha",                 # Google reCAPTCHA gömülü
]

# Kaldırılmış ürün sayfası işaretleri (HTTP 404/410'a ek olarak)
OLU_IZLERI = [
    "sayfa bulunamadı", "aradığınız sayfa", "ürün bulunamadı",
    "page not found", "satışta değil", "yayından kaldırıl",
]

GENEL_SECICILER = [
    ".product-price", "#product-price", ".price-value", "span.price",
    ".current-price", "[data-price-amount]", "span[itemprop=price]",
]

META_SECICILER = [
    ('meta[property="product:price:amount"]', "content"),
    ('meta[property="og:price:amount"]', "content"),
    ('meta[itemprop="price"]', "content"),
]

TL_KALIBI = re.compile(r"(\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+,\d{2})\s*(?:TL|₺)")

# JSON-LD içinde gezilecek iç içe anahtarlar. 'object' bilerek var: bazı
# siteler (mediamarkt vb.) Product'ı BuyAction.object içine gömüyor.
_LD_DALLAR = ("@graph", "mainEntity", "itemListElement", "item", "offers", "object")


@dataclass(frozen=True)
class Cikarim:
    """Bir sayfadan çıkarılan her şey."""
    fiyat: float | None = None
    guven: str = "yok"
    baslik: str | None = None
    puan: float | None = None
    yorum_sayisi: int | None = None
    engelli: bool = False
    olu: bool = False


def _corba(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _ld_dugumler(dugum):
    """JSON-LD ağacında gezinir: listeler, @graph, iç içe yapılar."""
    if isinstance(dugum, list):
        for x in dugum:
            yield from _ld_dugumler(x)
    elif isinstance(dugum, dict):
        yield dugum
        for anahtar in _LD_DALLAR:
            if anahtar in dugum:
                yield from _ld_dugumler(dugum[anahtar])


def _ld_bloklari(corba: BeautifulSoup) -> list:
    out = []
    for script in corba.find_all("script", type="application/ld+json"):
        ham = script.string or script.get_text() or ""
        if not ham.strip():
            continue
        try:
            out.append(json.loads(ham))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def _ld_fiyat(obj: dict) -> float | None:
    """Tek bir JSON-LD düğümünden fiyat. TRY dışı para birimini REDDEDER —
    bazı siteler USD fiyat da gömüyor ve 1.299 USD, 1.299 TL sanılıyordu."""
    for anahtar in ("price", "lowPrice"):
        ham = obj.get(anahtar)
        if ham is None:
            continue
        birim = str(obj.get("priceCurrency") or "").upper()
        if birim and birim not in ("TRY", "TL"):
            continue
        v = parse_tl(ham)
        if v:
            return v
    return None


def fiyat_ayikla(html: str, site_cfg: dict | None = None) -> tuple[float | None, str]:
    """Güven zinciri. Dönüş: (fiyat, guven)."""
    if not html:
        return None, "yok"
    site_cfg = site_cfg or {}
    corba = _corba(html)

    # 1) JSON-LD — sitenin kendi yapılandırılmış verisi.
    # Kapı bilerek geniş: fiyat çoğu zaman Product'ın KENDİSİNDE değil, onun
    # `offers` alt düğümündedir ve o düğümün @type'ı çoğu sitede boştur.
    # Yanlış düğüm yakalama riskini para birimi kontrolü (_ld_fiyat) kapatır.
    for blok in _ld_bloklari(corba):
        for obj in _ld_dugumler(blok):
            tip = str(obj.get("@type") or "")
            fiyatli = "price" in obj or "lowPrice" in obj
            if "Product" in tip or "Offer" in tip or "offers" in obj or fiyatli:
                v = _ld_fiyat(obj)
                if v:
                    return v, "json-ld"

    # 2) Siteye özel + genel CSS seçiciler
    seciciler = []
    if site_cfg.get("fiyat_secici"):
        seciciler.append(site_cfg["fiyat_secici"])
    seciciler += GENEL_SECICILER
    for secici in seciciler:
        try:
            for el in corba.select(secici)[:5]:
                v = parse_tl(el.get_text(strip=True)) or parse_tl(el.get("content"))
                if v:
                    return v, "secici"
        except Exception:
            continue

    # 3) Meta etiketleri
    for secici, nitelik in META_SECICILER:
        try:
            el = corba.select_one(secici)
            if el:
                v = parse_tl(el.get(nitelik))
                if v:
                    return v, "meta"
        except Exception:
            continue

    # 4) Son çare: gövde regex'i — DÜŞÜK GÜVEN.
    # Kapsam elementi tanımlıysa ve sayfada YOKSA bu adım atlanır (bkz. modül
    # docstring'i): fiyatsız sayfada yanlış fiyat okumaktansa "yok" demek doğru.
    kapsam_secici = site_cfg.get("metin_alani")
    if kapsam_secici:
        kapsam = corba.select_one(kapsam_secici)
        if kapsam is None:
            return None, "yok"
    else:
        kapsam = corba.body or corba

    eslesme = TL_KALIBI.search(kapsam.get_text(" ", strip=True))
    if eslesme:
        v = parse_tl(eslesme.group(1))
        if v:
            return v, "regex"

    return None, "yok"


def puan_ayikla(html: str) -> tuple[float | None, int | None]:
    """Mağaza puanı ve yorum sayısı (JSON-LD aggregateRating).

    Keepa'nın grafiğin yanında gösterdiği "bu ürün beğeniliyor mu" boyutu.
    Fiyat tek başına yeterli değil: 40.000 TL'lik dip fiyat, 2.1 puanlı bir
    üründe fırsat değildir.
    """
    if not html:
        return None, None
    for blok in _ld_bloklari(_corba(html)):
        for obj in _ld_dugumler(blok):
            agg = obj.get("aggregateRating")
            if not isinstance(agg, dict):
                continue
            puan = None
            try:
                puan = float(str(agg.get("ratingValue")).replace(",", "."))
            except (TypeError, ValueError):
                pass
            # 5'lik sisteme normalize et (bazı siteler 100 üzerinden verir)
            if puan is not None and puan > 5:
                puan = puan / 20 if puan <= 100 else None

            sayi = None
            ham = agg.get("reviewCount") or agg.get("ratingCount")
            try:
                sayi = int(str(ham).replace(".", "").replace(",", ""))
            except (TypeError, ValueError):
                pass

            if puan is not None:
                return puan, sayi
    return None, None


def baslik_ayikla(html: str) -> str | None:
    """Ürün adı: og:title → h1 → <title>. Site adı eki kırpılır."""
    if not html:
        return None
    corba = _corba(html)

    og = corba.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        return _baslik_temizle(og["content"])

    h1 = corba.find("h1")
    if h1 and h1.get_text(strip=True):
        return _baslik_temizle(h1.get_text(strip=True))

    if corba.title and corba.title.get_text(strip=True):
        return _baslik_temizle(corba.title.get_text(strip=True))
    return None


def _baslik_temizle(t: str) -> str:
    """'Ürün Adı | Mağaza' → 'Ürün Adı'. Ayraç ürün adının İÇİNDE de geçebilir
    (örn. 'RTX 4070 - 12GB'), bu yüzden sadece ayraçtan ÖNCEKİ kısım anlamlı
    uzunluktaysa kırpılır."""
    for ayrac in (" | ", "|", " – ", " — ", " - "):
        if ayrac in t:
            bas = t.split(ayrac)[0].strip()
            if len(bas) >= 15:
                t = bas
                break
    return " ".join(t.split()).strip()[:120]


def engel_mi(html: str) -> bool:
    """Bot koruması / captcha sayfası mı?"""
    if not html:
        return False
    # Yapısal imza ÖNCE: ucuz (ayrıştırma yok) ve dile bağlı değil.
    ham = html.lower()
    if any(iz in ham for iz in ENGEL_YAPISAL):
        return True
    corba = _corba(html)
    baslik = (corba.title.get_text(strip=True).lower() if corba.title else "")
    if any(iz in baslik for iz in ENGEL_IZLERI):
        return True
    govde = corba.get_text(" ", strip=True)[:3000].lower()
    return any(iz in govde for iz in ENGEL_IZLERI)


def olu_mu(html: str, http_kodu: int | None = None) -> bool:
    """Sayfa kaldırılmış mı? HTTP kodu veya başlıktaki işaretlerden."""
    if http_kodu in (404, 410):
        return True
    if not html:
        return False
    corba = _corba(html)
    baslik = (corba.title.get_text(strip=True).lower() if corba.title else "")
    return any(iz in baslik for iz in OLU_IZLERI)


def cikar(html: str, site_cfg: dict | None = None,
          http_kodu: int | None = None) -> Cikarim:
    """Tek geçişte her şeyi çıkarır. Tarama worker'ının çağırdığı fonksiyon."""
    if olu_mu(html, http_kodu):
        return Cikarim(olu=True, baslik=baslik_ayikla(html))
    if engel_mi(html):
        return Cikarim(engelli=True)

    fiyat, guven = fiyat_ayikla(html, site_cfg)
    puan, yorum = puan_ayikla(html)
    return Cikarim(fiyat=fiyat, guven=guven, baslik=baslik_ayikla(html),
                   puan=puan, yorum_sayisi=yorum)

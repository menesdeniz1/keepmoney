"""Toplayıcıda (akakçe) ürün arama — çoklu kaynak kurgusunun giriş kapısı.

NEDEN VAR: Kullanıcı tek bir mağaza linki yapıştırıyor ama asıl istediği "bu
ürün en ucuz nerede" cevabı. Toplayıcı sayfası bunu tek istekte veriyor:
onlarca satıcının fiyatı orada listeli. Öncül projede (tracker) bu kurgu
ürünün merkezindeydi — Akakçe linki kaynak listesinin BAŞINA konur, mağaza
linki yedek kalırdı.

İkinci faydası daha az görünür ama daha önemli: bot koruması sert olan
mağazaların (Hepsiburada, n11) fiyatına ulaşmanın en sağlam yolu toplayıcıdır.
Gerçek ölçümde o iki site gerçek tarayıcıyla bile 403 dönüyordu; aynı ürünün
fiyatı akakçe sayfasında sorunsuz okunuyor.

EŞLEŞTİRME OTOMATİK BAĞLANMAZ — KULLANICI SEÇER. Bu tasarımın en kritik
kararı. "RTX 5070 Ti Prime" ile "RTX 5070 Ti Prime OC" ayrı ürünlerdir ve
fiyatları %15 farklıdır; otomatik eşleştirme yanlış ürünün fiyatını
kullanıcının ürününe yazabilir. O hata SESSİZDİR: grafik çizilir, "dip
bölgesi" denir, kullanıcı yanlış ürüne bakarak alır. Öneri sunmak serbest,
sessizce yanlış veri yazmak değil.

AYRIŞTIRMA SAYFA YAPISINA DEĞİL, URL KALIBINA DAYANIR. Akakçe'nin ürün
sayfaları daima `...-fiyati,<id>.html` biçiminde; CSS sınıfları değişse de bu
kalıp değişmiyor. Öncül projede aylarca çalışan yaklaşım buydu.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin

from .ayikla import _corba
from .cekici import Cekici
from .gunluk import log

logger = log("keepmoney.toplayici")

TABAN = "https://www.akakce.com"
ARAMA_URL = TABAN + "/arama/?q={}"

# Akakçe ürün sayfası kalıbı. Sayfa yapısı değişse de bu değişmiyor.
URUN_KALIBI = re.compile(r"fiyati,\d+\.html")

MAKS_ONERI = 5

# Tarayıcı motoru ~250 MB RAM yiyor. Arama kullanıcı isteğiyle tetiklendiği
# için eşzamanlı çağrı sayısı SINIRLANMALI: on kullanıcı aynı anda arama
# yaparsa API süreci belleği tüketip ölür ve TARAMA DA durur. Sıra beklemek,
# çökmekten iyidir.
_ARAMA_SLOTU = threading.Semaphore(2)


@dataclass(frozen=True)
class Oneri:
    """Kullanıcıya sunulan aday. Onaylanmadan hiçbir yere yazılmaz."""
    ad: str
    url: str


def ara(cekici: Cekici, sorgu: str, limit: int = 3) -> list[Oneri]:
    """Toplayıcıda ürün adıyla arar. Hata durumunda BOŞ liste döner.

    Arama bir kolaylıktır, kritik yol değil: toplayıcı erişilemezse kullanıcı
    linki elle de ekleyebilir. Bu yüzden istisna fırlatmıyoruz — arama
    başarısız diye ürün ekleme akışı kırılmamalı.
    """
    sorgu = (sorgu or "").strip()
    if not sorgu:
        return []

    with _ARAMA_SLOTU:
        try:
            # `render` ZORLANMIYOR: arama sonuç sayfasındaki bağlantılar sunucu
            # HTML'inde geliyor. Toplayıcı bot duvarı çıkarırsa çekim zinciri
            # zaten kendiliğinden tarayıcıya yükseliyor (bkz. cekici.cek) —
            # yani pahalı yol yalnızca gerektiğinde ödeniyor.
            cekim = cekici.cek(ARAMA_URL.format(quote_plus(sorgu)), {})
        except Exception as e:
            logger.warning("toplayici_arama_hatasi", sorgu=sorgu, hata=str(e))
            return []

    if not cekim.html:
        logger.info("toplayici_arama_bos", sorgu=sorgu, kod=cekim.http_kodu)
        return []
    return _sonuclari_ayikla(cekim.html, limit)


def _sonuclari_ayikla(html: str, limit: int) -> list[Oneri]:
    corba = _corba(html)
    oneriler: list[Oneri] = []
    gorulen: set[str] = set()

    for a in corba.select("a[href]"):
        href = a.get("href") or ""
        if not URUN_KALIBI.search(href):
            continue
        url = urljoin(TABAN, href).split("?")[0]
        if url in gorulen:
            continue

        ad = " ".join((a.get_text(" ", strip=True) or "").split())
        if not ad:
            # Bağlantı metni boşsa görsel bağlantısıdır; ad nitelikte olur.
            ad = (a.get("title") or a.get("aria-label") or "").strip()
        if not ad:
            continue

        gorulen.add(url)
        oneriler.append(Oneri(ad=ad[:100], url=url))
        if len(oneriler) >= min(limit, MAKS_ONERI):
            break
    return oneriler

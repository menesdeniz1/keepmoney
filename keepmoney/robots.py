"""robots.txt saygısı.

NEDEN VAR: bu ürün başkalarının sitelerinden veri okuyor. `robots.txt`
teknik bir zorunluluk değil — kimse zorlamaz — ama site sahibinin açıkça
ifade ettiği iradedir. Yok saymak iki şeye mal olur: IP'nin kalıcı olarak
engellenmesi (ürünün tamamen çalışmaz hâle gelmesi) ve savunulabilir bir
konumun kaybı.

TASARIM:
  • Kuralları `urllib.robotparser` ÇÖZÜMLER ama İNDİRMEZ. İndirmeyi kendimiz
    yapıyoruz; sebebi aşağıda (bkz. "Neden kendi indirmemiz").
  • Sonuç host başına ÖNBELLEKLENİR: her fiyat okumasında robots.txt
    indirmek, korumaya çalıştığımız yükü ikiye katlardı. Başarısız denemeler
    KISA ömürlü önbelleklenir — geçici bir arıza bir günlük yasağa dönüşmesin.
  • İndirme SSRF kapısından geçer (`aglar.guvenli_mi`) — robots.txt de sonuçta
    kullanıcının verdiği bir adrese yapılan istektir.

NEDEN KENDİ İNDİRMEMİZ (gerçek bir hatadan öğrenildi):
  `RobotFileParser.read()` iki şeyi birden yanlış yapıyordu.

  1) İsteği `Python-urllib/3.x` kimliğiyle atıyor. Hepsiburada ve n11 gibi
     WAF'lı siteler bu kimliğe robots.txt için bile 403 dönüyor. Kendimizi
     dürüstçe tanıtmak (bot adı + iletişim adresi) hem nezaket kuralıdır hem
     de kuralları GERÇEKTEN okuyup uyabilmemizin tek yolu.

  2) 401/403 gördüğünde `disallow_all = True` yapıyor — yani "her şey yasak".
     Bu 1996 taslağının davranışı. RFC 9309 §2.3.1.3 bunun tersini söyler:
     robots.txt 4xx ile gelmiyorsa KISITLAMA BEYAN EDİLMEMİŞ demektir ve
     tarayıcı kaynaklara erişebilir.

  Sonuç, ilk gerçek link denemesinde görüldü: Türkiye'nin en büyük iki
  pazaryeri "robots.txt yasaklıyor" diye elendi. Oysa o siteler hiçbir şey
  yasaklamamıştı — WAF'ları robots.txt dosyasının kendisini vermemişti.
  Beyan edilmemiş bir yasağı varsaymak, ürünün yarısını sebepsiz kapatmaktı.

  BU, "robots.txt'yi umursama" DEMEK DEĞİLDİR: 200 ile gelen her kural
  aynen uygulanır. Sitenin gerçek iradesi ayrıca çekim anında da görülür —
  403/429 dönen kaynak `engel_mi` ile yakalanır, throttle cezası yer ve
  ısrar edilmez.
"""
from __future__ import annotations

import threading
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from .aglar import guvenli_mi
from .ayarlar import ayarlar
from .gunluk import log

logger = log("keepmoney.robots")

# Bot kimliğimiz. `robots.txt`te bize özel kural yazılabilsin diye ayrı bir
# ad taşıyoruz; site sahibi istediğinde yalnızca bizi engelleyebilmeli.
BOT_ADI = "KeepMoneyBot"

# Önbellek ömrü: robots.txt nadiren değişir, günde bir kez bakmak fazlasıyla
# yeterli ve site başına ek yükü ihmal edilebilir kılıyor.
ONBELLEK_OMRU_SN = 24 * 3600

# Okunamayan robots.txt KISA süre önbelleklenir. 24 saat beklemek, beş
# dakikalık bir sunucu arızasını bir günlük veri kaybına çevirirdi.
HATA_ONBELLEK_SN = 15 * 60

ZAMAN_ASIMI_SN = 10


def _kimlik() -> str:
    """Dürüst bot kimliği: kim olduğumuz ve nereden ulaşılacağı.

    Site sahibi logunda bizi görüp ya kural yazabilmeli ya da iletişime
    geçebilmeli. Tarayıcı taklidi yapmak burada YANLIŞ olurdu — robots.txt
    okumanın bütün anlamı açık kimlikle davranmaktır.
    """
    return f"{BOT_ADI}/1.0 (+{ayarlar().site_adresi})"


class RobotsKapisi:
    """Host başına robots.txt kuralları. Süreç ömrü boyunca tekil olmalı."""

    def __init__(self, onbellek_omru: int = ONBELLEK_OMRU_SN):
        self.onbellek_omru = onbellek_omru
        self._kilit = threading.Lock()
        # host → (okuyucu | None, ne zaman alındı, ömür). None = kural yok.
        self._onbellek: dict[str, tuple[object | None, float, float]] = {}

    def _oku(self, taban: str) -> tuple[object | None, float]:
        """robots.txt indirir.

        Dönüş: (okuyucu | None, önbellek ömrü). None = uygulanacak kural yok.
        """
        url = f"{taban}/robots.txt"
        try:
            yanit = requests.get(
                url, headers={"User-Agent": _kimlik()},
                timeout=ZAMAN_ASIMI_SN, allow_redirects=True)
        except Exception as e:
            logger.debug("robots_okunamadi", taban=taban, hata=str(e))
            return None, HATA_ONBELLEK_SN

        if yanit.status_code == 200:
            okuyucu = urllib.robotparser.RobotFileParser()
            okuyucu.parse(yanit.text.splitlines())
            return okuyucu, self.onbellek_omru

        if 400 <= yanit.status_code < 500:
            # RFC 9309 §2.3.1.3: dosya yoksa/erişilemiyorsa kısıtlama BEYAN
            # EDİLMEMİŞTİR. 403 çoğu zaman WAF'ın bilinmeyen istemciyi
            # elemesidir, sitenin taramaya dair bir kararı değil.
            logger.info("robots_beyan_yok", taban=taban,
                        kod=yanit.status_code)
            return None, self.onbellek_omru

        # 5xx / 429: geçici. Kısa önbellek, yakında yeniden dene.
        logger.warning("robots_gecici_hata", taban=taban,
                       kod=yanit.status_code)
        return None, HATA_ONBELLEK_SN

    def _okuyucu_getir(self, taban: str):
        simdi = time.monotonic()
        with self._kilit:
            girdi = self._onbellek.get(taban)
            if girdi and simdi - girdi[1] < girdi[2]:
                return girdi[0]

        okuyucu, omur = self._oku(taban)    # ağ çağrısı kilit DIŞINDA
        with self._kilit:
            self._onbellek[taban] = (okuyucu, simdi, omur)
        return okuyucu

    def izin_var_mi(self, url: str) -> bool:
        """Bu URL taranabilir mi?

        Kararsız kalınan her durumda True döner — robots.txt bir yasak
        beyanıdır; beyan yoksa yasak da yoktur.
        """
        p = urlparse(url)
        if not p.scheme or not p.hostname:
            return True
        taban = f"{p.scheme}://{p.netloc}"

        # robots.txt'nin kendisi de bir dış istektir: SSRF kapısından geçmeli.
        if not guvenli_mi(f"{taban}/robots.txt"):
            return True                     # asıl engelleme çekim anında

        okuyucu = self._okuyucu_getir(taban)
        if okuyucu is None:
            return True

        try:
            return bool(okuyucu.can_fetch(BOT_ADI, url))
        except Exception:
            return True

    def temizle(self) -> None:
        with self._kilit:
            self._onbellek.clear()

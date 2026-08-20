"""Derlenmiş arayüzün sunulması (SPA).

NEDEN VAR: `Dockerfile` arayüzü derleyip imaja `/uygulama/statik` altına
kopyalıyordu ama hiçbir yerde SUNULMUYORDU. Yani üretimde `docker compose up`
sonrası API ayaktaydı, `/api/*` çalışıyordu, ama web panosu hiç erişilemezdi:
ürünün yarısı deploy edilmiş görünüp yok hükmündeydi. CSP'nin
`default-src 'self'` olması ve `vite.config.ts`teki vekil ayarı da hep aynı
kaynaktan sunumu VARSAYIYORDU — varsayım vardı, uygulaması yoktu.

TEK KAYNAK (same-origin) TERCİHİ, ayrı bir statik sunucudan daha basit:
  • httpOnly oturum çerezi çapraz kaynak sorunları olmadan taşınır (K22),
  • CORS üretimde fiilen devre dışı kalır (saldırı yüzeyi küçülür),
  • CSP dar tutulabilir,
  • dağıtım tek konteyner.

SPA GERİ DÜŞÜŞÜ: React Router istemci tarafında yönlendirme yapıyor.
`/izleme/12` adresini tarayıcıya doğrudan yazan (ya da yenileyen) kullanıcıya
sunucunun `index.html` dönmesi gerekir; aksi halde 404 görür. Ama bu geri
düşüş `/api/*` gibi yollara UYGULANMAMALI — yoksa var olmayan bir API ucu
JSON 404 yerine HTML döner ve istemci "beklenmeyen yanıt" hatası verir.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..ayarlar import ayarlar
from ..gunluk import log

logger = log("keepmoney.api.statik")

# Dockerfile buraya kopyalıyor. Yerel geliştirmede Vite kendi sunucusunu
# çalıştırdığı için bu dizin genelde yoktur — o durumda mount edilmez.
VARSAYILAN_DIZIN = Path(__file__).resolve().parents[2] / "statik"

# Bu önekler ASLA index.html'e düşmez; API'nin kendi 404'ünü döndürmeli.
API_ONEKLERI = ("/api", "/saglik", "/metrics", "/docs", "/redoc", "/openapi.json")


def arayuzu_bagla(app: FastAPI, dizin: Path | None = None) -> bool:
    """Derlenmiş arayüzü uygulamaya bağlar. Dizin yoksa sessizce atlar.

    Dönen: bağlandı mı.
    """
    ayarli = ayarlar().arayuz_dizini
    kok = dizin or (Path(ayarli) if ayarli else VARSAYILAN_DIZIN)
    if not (kok / "index.html").is_file():
        logger.info("arayuz_bulunamadi", dizin=str(kok))
        return False

    # Hash'li varlıklar (index-a1b2c3.js) uzun süre önbelleklenebilir; adları
    # içeriğe bağlı olduğu için bayatlama riski yok. `index.html` ise ASLA
    # önbelleklenmemeli — yoksa kullanıcı yeni sürümü günlerce görmez.
    app.mount("/assets", StaticFiles(directory=kok / "assets"), name="assets")

    @app.get("/{yol:path}", include_in_schema=False)
    async def spa(istek: Request, yol: str):
        if istek.url.path.startswith(API_ONEKLERI):
            # Buraya düşmek, gerçekten var olmayan bir API ucu demektir.
            raise HTTPException(status_code=404, detail="Bulunamadı")

        # Kökteki gerçek dosyalar (favicon, manifest, sw.js …) doğrudan.
        aday = (kok / yol).resolve()
        if yol and kok in aday.parents and aday.is_file():
            return FileResponse(aday)

        # DOSYA GİBİ GÖRÜNÜP BULUNAMAYAN yol → 404, index.html DEĞİL.
        #
        # Aksi halde tarayıcı, istediği JavaScript'in yerine HTML alır ve
        # hata "Unexpected token '<'" olarak görünür — yani sorunun eksik
        # dosya olduğunu SÖYLEMEZ. Bu, dağıtım sonrası en sinsi arıza
        # türlerinden biri: kullanıcının önbelleğindeki eski `index.html`
        # artık var olmayan bir parça dosyasını ister, 200 + HTML alır ve
        # ekran bembeyaz kalır. `sw.js` eksikse servis çalışanı da aynı
        # sebeple "unknown error" der.
        #
        # Uygulamanın rotalarında nokta YOKTUR (/izleme/12, /setler, …), bu
        # yüzden "adında nokta var" ölçütü SPA yollarını yanlışlıkla
        # yakalamaz — `/assets` altı zaten StaticFiles'ta ve o da 404 döner.
        if yol and "." in PurePosixPath(yol).name:
            raise HTTPException(status_code=404, detail="Bulunamadı")

        return FileResponse(kok / "index.html",
                            headers={"Cache-Control": "no-cache"})

    logger.info("arayuz_baglandi", dizin=str(kok))
    return True

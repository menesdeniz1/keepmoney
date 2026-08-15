"""HTTP ölçüm ara katmanı.

`koruma.py`dan ayrı dosya: güvenlik başlıkları ile ölçüm toplamanın
değişme sebepleri farklıdır (SRP). Güvenlik politikası tehdit modeline,
ölçümler pano ihtiyacına göre değişir.
"""
from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from ..olcumler import http_istek, http_sure

# Kendi ölçüm ucumuzu ölçmeyiz: Prometheus saniyede bir çeker ve grafiği
# kendi trafiğiyle doldurur.
HARIC_YOLLAR = frozenset({"/metrics", "/saglik"})


def _rota_sablonu(istek: Request) -> str | None:
    """'/api/izlemeler/42' → '/api/izlemeler/{izleme_id}'.

    Şablon yoksa (404 — hiçbir rotaya uymadı) None döner ve istek HİÇ
    ölçülmez. Eşleşmeyen yolu ham hâliyle etiketlemek, rastgele URL deneyen
    bir tarayıcının Prometheus'a sınırsız zaman serisi yazdırması demektir.
    """
    rota = istek.scope.get("route")
    return getattr(rota, "path", None)


class OlcumAraKatmani(BaseHTTPMiddleware):
    async def dispatch(self, istek: Request, sonraki):
        if istek.url.path in HARIC_YOLLAR:
            return await sonraki(istek)

        baslangic = time.perf_counter()
        try:
            yanit = await sonraki(istek)
        except Exception:
            # İşlenmemiş hata da ölçülmeli — yoksa 500 dalgası panoda
            # "trafik düştü" gibi görünür.
            rota = _rota_sablonu(istek)
            if rota:
                http_istek.labels(
                    yontem=istek.method, rota=rota, durum="500").inc()
            raise

        rota = _rota_sablonu(istek)
        if rota:
            sure = time.perf_counter() - baslangic
            http_istek.labels(yontem=istek.method, rota=rota,
                              durum=str(yanit.status_code)).inc()
            http_sure.labels(yontem=istek.method, rota=rota).observe(sure)
        return yanit

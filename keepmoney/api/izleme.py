"""İstek kimliği ve merkezî hata yakalama.

İKİ EKSİĞİ KAPATIR:

1. KORELASYON KİMLİĞİ. Üretimde bir kullanıcı "saat 14:30'da hata aldım"
   dediğinde, o isteğe ait TÜM log satırlarını tek bir anahtarla toplamanın
   yolu olmalı. `gunluk.py` zaten `merge_contextvars` işlemcisini kuruyordu
   ama bağlama yazan kimse yoktu — altyapı vardı, kullanan yoktu.

2. İŞLENMEMİŞ İSTİSNALAR. Beklenmeyen bir hata Starlette'in varsayılan
   işleyicisine düşüyor, gövdesi düz metin "Internal Server Error" oluyor
   ve iz kaydı yapılandırılmamış biçimde stderr'e gidiyordu. Yani istemci
   JSON beklerken metin alıyor, biz de hatayı isteğe bağlayamıyorduk.

KULLANICIYA İZ KAYDI GÖSTERİLMEZ: yığın izi iç yapıyı (dosya yolları,
kütüphane sürümleri, sorgu parçaları) sızdırır. Kullanıcı yalnızca istek
kimliğini görür ve desteğe onu söyler; ayrıntı logda kalır.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..gunluk import log

logger = log("keepmoney.api.istek")

BASLIK = "X-Request-ID"


class IstekKimligi(BaseHTTPMiddleware):
    """Her isteğe bir kimlik bağlar; yanıt başlığında geri verir.

    Gelen istekte `X-Request-ID` varsa KORUNUR: ters vekil ya da çağıran
    servis zaten bir kimlik ürettiyse zincir kopmamalı. Yoksa üretilir.
    """

    async def dispatch(self, istek: Request, sonraki):
        kimlik = istek.headers.get(BASLIK) or uuid.uuid4().hex[:16]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            istek_kimligi=kimlik,
            yol=istek.url.path,
            yontem=istek.method,
        )
        istek.state.istek_kimligi = kimlik
        try:
            yanit = await sonraki(istek)
        finally:
            structlog.contextvars.clear_contextvars()
        yanit.headers[BASLIK] = kimlik
        return yanit


async def beklenmeyen_hata(istek: Request, hata: Exception) -> JSONResponse:
    """İşlenmemiş istisna → yapılandırılmış log + güvenli JSON yanıt."""
    kimlik = getattr(istek.state, "istek_kimligi", "-")
    logger.exception(
        "beklenmeyen_hata",
        istek_kimligi=kimlik,
        yol=istek.url.path,
        yontem=istek.method,
        hata_turu=type(hata).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Beklenmeyen bir hata oluştu. Sorun sürerse bu kodu "
                      f"destekle paylaş: {kimlik}",
            "istek_kimligi": kimlik,
        },
        headers={BASLIK: kimlik},
    )

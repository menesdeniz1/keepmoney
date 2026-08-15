"""FastAPI uygulaması — bileşim kökü (composition root).

Uygulamanın tek "kirli" katmanı burası: her şeyi birbirine bağlar. İş mantığı
YOK — rotalar servisleri, servisler alan katmanını çağırır. Bu dosyaya iş
kuralı sızmaya başlarsa katmanlama bozuluyor demektir.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..ayarlar import ayarlar
from ..db import init_db
from .rotalar import auth, izlemeler, setler, uyarilar

log = logging.getLogger("keepmoney.api")


@asynccontextmanager
async def yasam_dongusu(app: FastAPI):
    a = ayarlar()
    if not a.uretim_mi:
        # Geliştirmede tabloları otomatik kur. Üretimde şema DEĞİŞİKLİĞİ
        # Alembic'in işidir — `create_all` mevcut tabloları güncellemez ve
        # sessizce eski şemayla çalışmaya devam eder.
        init_db()
    log.info("KeepMoney API başladı (ortam=%s)", a.ortam)
    yield
    log.info("KeepMoney API kapandı")


def uygulama_olustur() -> FastAPI:
    a = ayarlar()
    app = FastAPI(
        title="KeepMoney API",
        version="0.2.0",
        summary="Kişisel fiyat takip ve alım zamanlaması",
        lifespan=yasam_dongusu,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=a.cors_kaynaklari,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for rota in (auth, izlemeler, setler, uyarilar):
        app.include_router(rota.router)

    @app.get("/saglik", tags=["sistem"])
    def saglik():
        return {"durum": "ayakta", "ortam": a.ortam}

    return app


app = uygulama_olustur()

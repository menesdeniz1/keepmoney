"""FastAPI uygulaması — bileşim kökü (composition root).

Uygulamanın tek "kirli" katmanı burası: her şeyi birbirine bağlar. İş mantığı
YOK — rotalar servisleri, servisler alan katmanını çağırır. Bu dosyaya iş
kuralı sızmaya başlarsa katmanlama bozuluyor demektir.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..ayarlar import ayarlar
from ..db import init_db
from ..gunluk import kur as gunluk_kur
from ..gunluk import log
from .koruma import GuvenlikBasliklari
from .olcum import OlcumAraKatmani
from .rotalar import auth, izlemeler, setler, sistem, uyarilar

logger = log("keepmoney.api")


@asynccontextmanager
async def yasam_dongusu(app: FastAPI):
    a = ayarlar()
    gunluk_kur()
    # SADECE geliştirmede tabloları otomatik kur.
    #  • Üretimde şema Alembic'in işi (K15) — `create_all` var olan tabloyu
    #    güncellemez, sessizce eski şemayla devam eder.
    #  • Testte de kurma: testler kendi bellek içi oturumlarını enjekte eder;
    #    burada dosya veritabanına dokunmak Alembic adımıyla çakışıyordu
    #    ("table domain_health already exists" — CI bunu yakaladı).
    if a.ortam == "gelistirme":
        init_db()
    logger.info("api_basladi", ortam=a.ortam)
    yield
    logger.info("api_kapandi")


def uygulama_olustur() -> FastAPI:
    a = ayarlar()
    app = FastAPI(
        title="KeepMoney API",
        version="0.2.0",
        summary="Kişisel fiyat takip ve alım zamanlaması",
        lifespan=yasam_dongusu,
    )

    # Sıra önemli: başlık ara katmanı en dışta olmalı ki CORS ön-uçuş
    # (preflight) yanıtları da güvenlik başlıklarını taşısın.
    app.add_middleware(GuvenlikBasliklari)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=a.cors_kaynaklari,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Ölçüm en içte: reddedilen CORS/ön-uçuş isteklerini değil, gerçekten
    # işlenen istekleri saysın.
    app.add_middleware(OlcumAraKatmani)

    for rota in (auth, izlemeler, setler, sistem, uyarilar):
        app.include_router(rota.router)

    return app


app = uygulama_olustur()

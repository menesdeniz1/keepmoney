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
from .izleme import IstekKimligi, beklenmeyen_hata
from .koruma import GuvenlikBasliklari
from .olcum import OlcumAraKatmani
from .rotalar import auth, disa_aktar, firsatlar, izlemeler, setler, sistem, uyarilar
from .statik import arayuzu_bagla

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

    # Sıra önemli — `add_middleware` ile eklenen SON katman EN DIŞTA çalışır.
    # İstek kimliği en dışta olmalı: güvenlik başlıkları ya da CORS
    # aşamasında oluşan bir hata bile kimlikli loglanabilsin.
    app.add_middleware(IstekKimligi)
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

    # İşlenmemiş istisnalar: yapılandırılmış log + kullanıcıya iz kaydı
    # SIZDIRMAYAN JSON yanıt (bkz. api/izleme.py).
    app.add_exception_handler(Exception, beklenmeyen_hata)

    for rota in (auth, disa_aktar, firsatlar, izlemeler, setler, sistem,
                 uyarilar):
        app.include_router(rota.router)

    # Derlenmiş arayüz EN SONDA bağlanır: yakalayıcı `/{yol:path}` rotası
    # daha önce eklenseydi tüm API uçlarını gölgelerdi. Dizin yoksa (yerel
    # geliştirme — Vite kendi sunucusunu çalıştırır) sessizce atlanır.
    arayuzu_bagla(app)

    return app


app = uygulama_olustur()

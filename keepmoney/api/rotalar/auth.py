"""Kimlik rotaları."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from ... import semalar
from ...ayarlar import ayarlar
from ...servisler import kullanici as svc
from ..deps import DB, Kullanici, oturum_cerezi_sil, oturum_cerezi_yaz

router = APIRouter(prefix="/api/auth", tags=["kimlik"])


def _yanit(k) -> dict:
    return {
        "id": k.id,
        "email": k.email,
        "telegram_bagli": bool(k.telegram_chat_id),
        "created_at": k.created_at,
    }


@router.post("/kayit", response_model=semalar.KullaniciYaniti,
             status_code=status.HTTP_201_CREATED)
def kayit(istek: semalar.KayitIstegi, db: DB):
    try:
        k = svc.kayit(db, istek.eposta, istek.parola)
    except svc.KimlikHatasi as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return _yanit(k)


@router.post("/giris", response_model=semalar.TokenYaniti)
def giris(istek: semalar.GirisIstegi, yanit: Response, db: DB):
    """Token'ı HEM httpOnly çerez olarak kurar HEM gövdede döner.

    Tarayıcı istemcisi gövdeyi yok sayar (token'a hiç dokunmaz); programatik
    istemciler gövdedeki token'ı Bearer olarak kullanır.
    """
    try:
        token = svc.giris(db, istek.eposta, istek.parola)
    except svc.KimlikHatasi as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(e),
            headers={"WWW-Authenticate": "Bearer"}) from e
    oturum_cerezi_yaz(yanit, token)
    return {"erisim_tokeni": token}


@router.post("/cikis", status_code=status.HTTP_204_NO_CONTENT)
def cikis(yanit: Response):
    """Çerezi siler. Token'ın kendisi süresi dolana kadar geçerli kalır —
    gerçek iptal için kara liste gerekir; kullanıcı sayısı anlamlı olunca
    eklenecek (şimdi kullanılmayan altyapı olurdu)."""
    oturum_cerezi_sil(yanit)


@router.get("/ben", response_model=semalar.KullaniciYaniti)
def ben(k: Kullanici):
    return _yanit(k)


@router.post("/telegram/baglanti", response_model=semalar.TelegramBaglamaYaniti)
def telegram_baglanti(k: Kullanici, db: DB):
    """Tek kullanımlık deep-link üretir. Kullanıcı chat ID kopyalamaz."""
    bot = ayarlar().telegram_bot_token
    if not bot:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Sunucuda Telegram botu yapılandırılmamış")
    # Token'ın ilk parçası bot kullanıcı adı değil, sayısal ID'dir; deep-link
    # için bot adı ayrı ayarlanmalı. Şimdilik ortam değişkeninden gelen adı
    # kullanmıyoruz — bot adı Faz 4'te bot modülüyle birlikte gelecek.
    baglanti, omur = svc.telegram_baglantisi(db, k, "KeepMoneyBot")
    return {"baglanti": baglanti, "gecerlilik_dk": omur}


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
def telegram_kaldir(k: Kullanici, db: DB):
    svc.telegram_kaldir(db, k)

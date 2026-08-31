"""FastAPI bağımlılıkları — oturum ve kimlik."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..ayarlar import ayarlar
from ..db import get_db
from ..guvenlik import jwt_kimlik
from ..models import User

# auto_error=False: eksik başlıkta FastAPI'nin varsayılan 403'ü yerine kendi
# 401'imizi üretelim — istemci "token yok" ile "yetkin yok"u ayırabilsin.
_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def mevcut_kullanici(
    istek: Request,
    db: DB,
    kimlik: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    """Oturumu İKİ kaynaktan kabul eder:

      1. httpOnly çerez — tarayıcı istemcisi (varsayılan yol). Token
         JavaScript'e hiç görünmez, XSS ile çalınamaz.
      2. `Authorization: Bearer` — programatik istemciler, CLI, testler.

    İkisini de desteklemek yaygın profesyonel kalıptır: web'e en güvenli
    yolu verir, entegrasyonlara standart yolu bırakır.

    Çerez YAPILANDIRILAN adla okunur. Eskiden imza `km_oturum` adını sabit
    yazıyordu ama çerezi kuran taraf `ayarlar().oturum_cerezi` kullanıyordu:
    `KEEPMONEY_OTURUM_CEREZI` değiştirildiği anda giriş başarılı oluyor,
    çerez kuruluyor, ama sonraki her istek 401 dönüyordu. Ayarın tek
    okuyucusu olmalı — yoksa "çalışıyor gibi görünen" bir ayar olur.
    """
    hata = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Geçersiz veya eksik oturum",
        headers={"WWW-Authenticate": "Bearer"},
    )

    cerez = istek.cookies.get(ayarlar().oturum_cerezi)
    token = (kimlik.credentials if kimlik and kimlik.credentials else cerez)
    if not token:
        raise hata

    kimlik = jwt_kimlik(token)
    if kimlik is None:
        raise hata
    kullanici_id, surum = kimlik

    kullanici = db.get(User, kullanici_id)
    if kullanici is None:
        raise hata           # hesap silinmiş ama token hâlâ geçerli

    # PAROLA DEĞİŞTİYSE ÖNCEKİ TOKEN'LAR GEÇERSİZ. JWT durumsuz olduğu için
    # bu kontrol olmadan parola sıfırlamak açık oturumları KAPATMIYORDU
    # (ölçüldü: sıfırlamadan sonra eski oturum /auth/ben'den 200 alıyordu).
    # TAM EŞİTLİK — zaman karşılaştırması DEĞİL: `iat` yalnızca saniye
    # taşıdığı için zaman damgası yaklaşımı aynı saniye içinde üretilmiş
    # token'lara delik bırakıyordu (testle yakalandı, bkz. models.py).
    if surum != (kullanici.oturum_surumu or 0):
        raise hata
    return kullanici


Kullanici = Annotated[User, Depends(mevcut_kullanici)]


def oturum_cerezi_yaz(yanit, token: str) -> None:
    """Girişte çerezi kurar. `secure` yalnızca üretimde: yerelde HTTP
    kullanıldığı için secure çerez tarayıcıya hiç ulaşmaz."""
    a = ayarlar()
    yanit.set_cookie(
        key=a.oturum_cerezi,
        value=token,
        max_age=a.jwt_omur_dk * 60,
        httponly=True,
        samesite="lax",
        secure=a.uretim_mi,
        path="/",
    )


def oturum_cerezi_sil(yanit) -> None:
    yanit.delete_cookie(ayarlar().oturum_cerezi, path="/")

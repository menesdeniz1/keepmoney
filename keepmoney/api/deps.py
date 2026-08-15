"""FastAPI bağımlılıkları — oturum ve kimlik."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..guvenlik import jwt_kullanici_id
from ..models import User

# auto_error=False: eksik başlıkta FastAPI'nin varsayılan 403'ü yerine kendi
# 401'imizi üretelim — istemci "token yok" ile "yetkin yok"u ayırabilsin.
_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def mevcut_kullanici(
    db: DB,
    kimlik: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    hata = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Geçersiz veya eksik oturum",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if kimlik is None or not kimlik.credentials:
        raise hata

    kullanici_id = jwt_kullanici_id(kimlik.credentials)
    if kullanici_id is None:
        raise hata

    kullanici = db.get(User, kullanici_id)
    if kullanici is None:
        raise hata           # hesap silinmiş ama token hâlâ geçerli
    return kullanici


Kullanici = Annotated[User, Depends(mevcut_kullanici)]

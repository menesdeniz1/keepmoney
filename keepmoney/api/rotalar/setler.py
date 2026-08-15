"""Set (bütçeli koleksiyon) rotaları."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ... import semalar
from ...servisler import setler as svc
from ..deps import DB, Kullanici

router = APIRouter(prefix="/api/setler", tags=["set"])


@router.get("", response_model=list[semalar.SetYaniti])
def listele(k: Kullanici, db: DB):
    return [svc.ozet(db, s) for s in svc.listele(db, k)]


@router.post("", response_model=semalar.SetYaniti,
             status_code=status.HTTP_201_CREATED)
def olustur(istek: semalar.SetIstegi, k: Kullanici, db: DB):
    s = svc.olustur(db, k, istek.ad, istek.hedef_butce, istek.sablon)
    return svc.ozet(db, s)


@router.get("/{set_id}", response_model=semalar.SetYaniti)
def getir(set_id: int, k: Kullanici, db: DB):
    try:
        return svc.ozet(db, svc.getir(db, k, set_id))
    except svc.SetHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.patch("/{set_id}", response_model=semalar.SetYaniti)
def guncelle(set_id: int, istek: semalar.SetIstegi, k: Kullanici, db: DB):
    try:
        s = svc.guncelle(db, k, set_id, **istek.model_dump(exclude_unset=True))
    except svc.SetHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    return svc.ozet(db, s)


@router.delete("/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def sil(set_id: int, k: Kullanici, db: DB):
    try:
        svc.sil(db, k, set_id)
    except svc.SetHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

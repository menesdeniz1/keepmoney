"""Bildirim merkezi rotaları."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ... import semalar
from ...servisler import uyari as svc
from ..deps import DB, Kullanici

router = APIRouter(prefix="/api/uyarilar", tags=["uyarı"])


@router.get("", response_model=list[semalar.UyariYaniti])
def listele(k: Kullanici, db: DB, sadece_okunmamis: bool = False):
    return svc.listele(db, k, sadece_okunmamis)


@router.get("/sayi")
def okunmamis_sayisi(k: Kullanici, db: DB):
    return {"okunmamis": svc.okunmamis_sayisi(db, k)}


@router.post("/{uyari_id}/okundu", status_code=status.HTTP_204_NO_CONTENT)
def okundu(uyari_id: int, k: Kullanici, db: DB):
    if not svc.okundu_isaretle(db, k, uyari_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uyarı bulunamadı")


@router.post("/hepsi-okundu")
def hepsi_okundu(k: Kullanici, db: DB):
    return {"isaretlenen": svc.hepsini_okundu_isaretle(db, k)}

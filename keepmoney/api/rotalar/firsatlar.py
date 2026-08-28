"""Fırsatlar ucu — Keepa'nın Deals'ının uyarlanmışı (BACKLOG D1).

Ayrı dosya: `izlemeler.py` zaten kalabalık ve bu ayrı bir kaynak — "kullanıcının
izlediği her şey" değil, "kullanıcının izlediklerinden şu an iyi fiyatta
olanlar".
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ... import semalar
from ...servisler import izleme as svc
from ..deps import DB, Kullanici

router = APIRouter(prefix="/api/firsatlar", tags=["firsatlar"])


@router.get("", response_model=list[semalar.IzlemeYaniti])
def firsatlar(
    k: Kullanici,
    db: DB,
    en_az_gun: int = Query(svc.FIRSAT_VARSAYILAN_EN_AZ_GUN, ge=1, le=365),
    sinyal: str | None = Query(
        None, description="Virgülle ayrılmış: dip,ucuz,pahali. Boşsa dip,ucuz."),
):
    if sinyal is None:
        sinyaller = svc.FIRSAT_VARSAYILAN_SINYALLER
    else:
        sinyaller = tuple(s.strip() for s in sinyal.split(",") if s.strip())
        gecersiz = set(sinyaller) - svc.FIRSAT_GECERLI_SINYALLER
        if gecersiz:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Geçersiz sinyal: {', '.join(sorted(gecersiz))}")

    return svc.firsatlar(db, k, en_az_gun, sinyaller)

"""Bildirim merkezi rotaları."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ... import semalar
from ...servisler import uyari as svc
from ..deps import DB, Kullanici

router = APIRouter(prefix="/api/uyarilar", tags=["uyarı"])


@router.get("", response_model=list[semalar.UyariYaniti])
def listele(
    k: Kullanici,
    db: DB,
    sadece_okunmamis: bool = False,
    # BACKLOG G2 — tekrarlanan parametre: `?tur=YUZDE&tur=DIP` gibi birden
    # çok türü BİRDEN süzebilmek için (arayüzdeki "düşüş" filtresi ikisini
    # birlikte gösterir). `list[UyariTuru]` FastAPI'ye her elemanı ayrı ayrı
    # doğrulatır — geçersiz bir değer OTOMATİK 422 döner.
    tur: list[semalar.UyariTuru] | None = Query(None),
    watch_id: int | None = Query(None),
    limit: int = Query(svc.VARSAYILAN_LIMIT, ge=1, le=svc.AZAMI_LIMIT),
    offset: int = Query(0, ge=0),
):
    """Sayfalı bildirim listesi (en yeniden eskiye).

    `limit` üst sınırı şemada zorlanıyor: sınırsız bırakmak, tek istekle
    tüm tablonun belleğe çekilmesine izin vermek olurdu.
    """
    return svc.listele(db, k, sadece_okunmamis, limit, offset, tur=tur, watch_id=watch_id)


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

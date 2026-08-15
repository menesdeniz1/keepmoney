"""İzleme rotaları — ürünün ana akışı."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ... import semalar
from ...servisler import izleme as svc
from ...servisler import urun as urun_svc
from ..deps import DB, Kullanici

router = APIRouter(prefix="/api/izlemeler", tags=["izleme"])


@router.get("", response_model=list[semalar.IzlemeYaniti])
def listele(k: Kullanici, db: DB):
    return svc.izlemeler(db, k)


@router.post("", response_model=semalar.IzlemeYaniti,
             status_code=status.HTTP_201_CREATED)
def ekle(istek: semalar.IzlemeEkleIstegi, k: Kullanici, db: DB):
    """Link yapıştır, izlemeye alsın.

    Fiyat okuma İSTEK İÇİNDE yapılmaz — kullanıcı 10 saniye beklemesin.
    Ürün sıraya alınır, tarama worker'ı ilk turda okur ve gerçek adı yazar.
    """
    try:
        return svc.ekle(db, k, str(istek.url), istek.hedef_fiyat,
                        istek.acil_fiyat, istek.set_id)
    except svc.KotaDoldu as e:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(e)) from e
    except svc.IzlemeHatasi as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.get("/{izleme_id}", response_model=semalar.IzlemeDetay)
def detay(izleme_id: int, k: Kullanici, db: DB):
    """Grafik + 'bu iyi fiyat mı' yorumu dahil tam detay."""
    try:
        w = svc.izleme_getir(db, k, izleme_id)
    except svc.IzlemeHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    return {
        "id": w.id,
        "hedef_fiyat": w.hedef_fiyat,
        "acil_fiyat": w.acil_fiyat,
        "aktif": w.aktif,
        "kilitli": w.kilitli,
        "kilitli_fiyat": w.kilitli_fiyat,
        "sustur_bitis": w.sustur_bitis,
        "set_id": w.set_id,
        "urun": urun_svc.detay(db, w.product),
    }


@router.patch("/{izleme_id}", response_model=semalar.IzlemeYaniti)
def guncelle(izleme_id: int, istek: semalar.IzlemeGuncelleIstegi,
             k: Kullanici, db: DB):
    try:
        return svc.guncelle(db, k, izleme_id,
                            **istek.model_dump(exclude_unset=True))
    except svc.IzlemeHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.delete("/{izleme_id}", status_code=status.HTTP_204_NO_CONTENT)
def sil(izleme_id: int, k: Kullanici, db: DB):
    try:
        svc.sil(db, k, izleme_id)
    except svc.IzlemeHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

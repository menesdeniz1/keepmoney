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
def guncelle(set_id: int, istek: semalar.SetGuncelleIstegi, k: Kullanici, db: DB):
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


@router.get("/{set_id}/gecmis", response_model=list[semalar.SetGecmisNoktasi])
def gecmis(set_id: int, k: Kullanici, db: DB):
    """Setin gün başına toplam geçmişi — bkz. `servisler/setler.py::gecmis`."""
    try:
        return svc.gecmis(db, k, set_id)
    except svc.SetHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post("/{set_id}/uyeler", response_model=semalar.UyelikSonucu)
def uyeleri_ekle(set_id: int, istek: semalar.UyelikIstegi,
                 k: Kullanici, db: DB):
    """Seçilen izlemeleri sete ekler — KISMİ BAŞARIYA izin verir.

    200 döner ve hangi kalemin alındığı, hangisinin neden atlandığı gövdede
    yazar. "Ya hep ya hiç" bilinçli olarak SEÇİLMEDİ: üyelikler birbirinden
    bağımsız, yarım kalan liste bozuk bir durum değil. Buna karşılık sekiz
    seçimin birini bayat diye reddedip sekizini birden geri çevirmek,
    kullanıcıya seçimi baştan yaptırırdı.
    """
    try:
        return svc.uyeleri_ekle(db, k, set_id, istek.izleme_idler)
    except svc.SetHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.delete("/{set_id}/uyeler/{izleme_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def uye_cikar(set_id: int, izleme_id: int, k: Kullanici, db: DB):
    """Ürünü setten çıkarır. İZLEME SİLİNMEZ — yalnızca gruplamadan çıkar."""
    try:
        varmis = svc.uye_cikar(db, k, set_id, izleme_id)
    except svc.SetHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    if not varmis:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Bu ürün bu sette değil")

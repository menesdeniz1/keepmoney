"""Set (bütçeli koleksiyon) use-case'leri.

Ürünün en ayırt edici özelliği: parçalar tek tek hedefte olmasa bile TOPLAM
bütçe yakalanınca haber verilir. Rakiplerde karşılığı yok.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import User, Watch, WatchSet


class SetHatasi(Exception):
    pass


def listele(db: Session, kullanici: User) -> list[WatchSet]:
    return (db.query(WatchSet)
            .filter(WatchSet.user_id == kullanici.id)
            .order_by(WatchSet.created_at)
            .all())


def getir(db: Session, kullanici: User, set_id: int) -> WatchSet:
    s = (db.query(WatchSet)
         .filter(WatchSet.id == set_id, WatchSet.user_id == kullanici.id)
         .one_or_none())
    if s is None:
        raise SetHatasi("Set bulunamadı")
    return s


def olustur(db: Session, kullanici: User, ad: str,
            hedef_butce: float | None = None,
            sablon: str | None = None) -> WatchSet:
    s = WatchSet(user_id=kullanici.id, ad=ad.strip(),
                 hedef_butce=hedef_butce, sablon=sablon)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def guncelle(db: Session, kullanici: User, set_id: int, **alanlar) -> WatchSet:
    s = getir(db, kullanici, set_id)
    for ad, deger in alanlar.items():
        if deger is not None and hasattr(s, ad):
            setattr(s, ad, deger)
    db.commit()
    db.refresh(s)
    return s


def sil(db: Session, kullanici: User, set_id: int) -> None:
    """Seti siler; ÜYELER SİLİNMEZ, sadece gruplamadan çıkar."""
    s = getir(db, kullanici, set_id)
    db.query(Watch).filter(Watch.set_id == s.id).update({"set_id": None})
    db.delete(s)
    db.commit()


def ozet(db: Session, s: WatchSet) -> dict:
    """Canlı toplam + hedefe durum.

    Kilitli üye için kilitli fiyat kullanılır ("bunu şu fiyata aldım/ayırdım").
    Fiyatı bilinmeyen üye varsa `hedefte` ASLA True dönmez — eksik toplamla
    'bütçeye girdin' demek kullanıcıyı yanlış yönlendirir.
    """
    toplam = 0.0
    eksik = 0
    uyeler = list(s.watches)

    for w in uyeler:
        fiyat = w.kilitli_fiyat if w.kilitli else (
            w.product.guncel_fiyat if w.product else None)
        if fiyat is None:
            eksik += 1
        else:
            toplam += fiyat

    return {
        "id": s.id,
        "ad": s.ad,
        "hedef_butce": s.hedef_butce,
        "toplam": round(toplam, 2),
        "eksik_uye": eksik,
        "uye_sayisi": len(uyeler),
        "hedefte": bool(s.hedef_butce and eksik == 0 and toplam <= s.hedef_butce),
    }

"""Set (bütçeli koleksiyon) use-case'leri.

Ürünün en ayırt edici özelliği: parçalar tek tek hedefte olmasa bile TOPLAM
bütçe yakalanınca haber verilir. Rakiplerde karşılığı yok.
"""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from ..models import User, Watch, WatchSet
from .ortak import alanlari_uygula

# PATCH ile değiştirilebilecek alanlar; gerekçe için bkz. `ortak`.
GUNCELLENEBILIR = frozenset({"ad", "hedef_butce", "sablon"})
# Bütçe kaldırılabilmeli — kullanıcı seti bütçesiz gruplamaya döndürebilir.
# `ad` burada YOK: isimsiz set anlamsız.
TEMIZLENEBILIR = frozenset({"hedef_butce", "sablon"})


class SetHatasi(Exception):
    pass


# Üyeler ve ürünleri birlikte yüklenir: `ozet()` her üyenin fiyatına bakıyor,
# tembel bırakılırsa set listesi set×üye kadar sorgu açar.
_UYELERLE = selectinload(WatchSet.watches).selectinload(Watch.product)


def listele(db: Session, kullanici: User) -> list[WatchSet]:
    return (db.query(WatchSet)
            .options(_UYELERLE)
            .filter(WatchSet.user_id == kullanici.id)
            .order_by(WatchSet.created_at)
            .all())


def getir(db: Session, kullanici: User, set_id: int) -> WatchSet:
    s = (db.query(WatchSet)
         .options(_UYELERLE)
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
    alanlari_uygula(s, alanlar, GUNCELLENEBILIR, TEMIZLENEBILIR, SetHatasi)
    if s.ad is not None:
        s.ad = s.ad.strip()
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

    BOŞ SET de hedefte SAYILMAZ, aynı sebeple: üye yokken `eksik == 0` ve
    `toplam (0) <= bütçe` sağlanıyordu, yani kullanıcı set kurar kurmaz
    ekranda yeşil "🎯 bütçe altında" görüyordu. Hiçbir şey almadan bütçenin
    altında olmak bir başarı değil, yalnızca boş bir listedir; rozet burada
    ölçtüğü şeyi yanlış bildiriyordu.
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
        "hedefte": bool(s.hedef_butce and uyeler and eksik == 0
                        and toplam <= s.hedef_butce),
    }

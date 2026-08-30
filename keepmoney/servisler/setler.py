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
    """Seti siler; ÜYELER SİLİNMEZ, sadece gruplamadan çıkar.

    Üyelik satırlarını veritabanı temizliyor (`set_uyeleri` üzerinde
    ON DELETE CASCADE). Eskiden burada elle `set_id = NULL` yazılıyordu;
    çoktan çoka modelde o sütun yok ve temizliği tek yerde (şemada) tutmak,
    yeni bir silme yolu eklendiğinde unutulmasını engelliyor.
    """
    s = getir(db, kullanici, set_id)
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
        "uyeler": [
            {
                "izleme_id": w.id,
                "ad": w.product.ad if w.product else "?",
                # Kilitli üyede kilitli fiyat gösterilir: toplam da onu
                # kullanıyor, ekranda başka bir sayı görmek kafa karıştırırdı.
                "fiyat": (w.kilitli_fiyat if w.kilitli
                          else (w.product.guncel_fiyat if w.product else None)),
                "kilitli": bool(w.kilitli),
                "sinyal": w.product.sinyal if w.product else None,
                "yuzdelik": w.product.yuzdelik if w.product else None,
                "gecmis_gun": w.product.gecmis_gun if w.product else None,
            }
            for w in uyeler
        ],
    }


def uyeleri_ekle(db: Session, kullanici: User, set_id: int,
                 izleme_idler: list[int]) -> dict:
    """Seçilen izlemeleri sete ekler. Döner: {"eklendi": [...], "atlandi": [...]}.

    YA HEP YA HİÇ DEĞİL — bilinçli. Üyelikler birbirinden bağımsız; yarım
    kalmış bir set "bozuk" bir durum değil, yalnızca eksik bir listedir.
    Buna karşılık hepsini reddetmek gerçekten zarar verir: kullanıcı sekiz
    ürün işaretler, biri başka bir sekmede silinmiş diye SEKİZİ birden
    kaybeder ve seçimi baştan yapar.

    Bu yüzden her kalem tek tek işlenir ve atlananlar SEBEBİYLE bildirilir —
    "bir şeyler oldu" demek yerine hangi ürünün neden alınmadığını söylemek
    (K56: boş/eksik cevabın tek ve anlaşılır bir anlamı olmalı).

    Zaten üye olan ürün hata değildir: sonuç aynı olduğu için sessizce
    atlanır ve `zaten_uye` olarak bildirilir.
    """
    s = getir(db, kullanici, set_id)
    mevcut = {w.id for w in s.watches}

    eklendi: list[int] = []
    atlandi: list[dict] = []

    for izleme_id in izleme_idler:
        if izleme_id in mevcut:
            atlandi.append({"id": izleme_id, "sebep": "zaten_uye"})
            continue
        w = (db.query(Watch)
             .filter(Watch.id == izleme_id, Watch.user_id == kullanici.id)
             .one_or_none())
        if w is None:
            # Başkasının izlemesi ya da silinmiş kayıt — ikisi de aynı cevabı
            # almalı: var olup olmadığını sızdırmak, listeyi taramaya yarar.
            atlandi.append({"id": izleme_id, "sebep": "bulunamadi"})
            continue
        s.watches.append(w)
        eklendi.append(izleme_id)

    db.commit()
    return {"eklendi": eklendi, "atlandi": atlandi}


def uye_cikar(db: Session, kullanici: User, set_id: int, izleme_id: int) -> bool:
    """Ürünü setten çıkarır. İZLEME SİLİNMEZ — yalnızca gruplamadan çıkar."""
    s = getir(db, kullanici, set_id)
    for w in list(s.watches):
        if w.id == izleme_id:
            s.watches.remove(w)
            db.commit()
            return True
    return False

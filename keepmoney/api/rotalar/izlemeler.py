"""İzleme rotaları — ürünün ana akışı."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ... import semalar, toplayici
from ...cekici import HttpCekici
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
                        istek.acil_fiyat, istek.set_idler)
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
        "set_idler": [s.id for s in w.setler],
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


# ── Çoklu kaynak: toplayıcıdan öneri, kullanıcı onayıyla ekleme ──
# Bu iki uç bilinçli olarak AYRI. Arama sonucu hiçbir şeyi değiştirmez;
# yalnızca kullanıcı bir adayı seçtiğinde kaynak eklenir. Otomatik
# eşleştirme yapılmıyor: "RTX 5070 Ti Prime" ile "Prime OC" ayrı ürünler ve
# yanlış eşleştirme, yanlış ürünün fiyatını doğru ürünün geçmişine yazar —
# sessiz, grafiğe işleyen, geri dönüşü olmayan bir veri hatası.

@router.get("/{izleme_id}/kaynak-onerileri",
            response_model=list[semalar.KaynakOnerisi])
def kaynak_onerileri(izleme_id: int, k: Kullanici, db: DB):
    """Bu ürünü satan başka mağazalar için toplayıcıda arar.

    YAVAŞ UÇ (~1-8 sn): dış siteye çıkıyor ve gerekirse gerçek tarayıcı
    açılıyor. Kullanıcının açıkça tetiklediği bir işlem olduğu için kabul
    edilebilir; arayüz bekleme durumu gösteriyor.

    BOŞ LİSTE = "sayfa okundu, eşleşme yok". Toplayıcıya ulaşılamazsa 503
    döner — arayüz ikisine de "eşleşme bulunamadı" diyordu ve ağ hatası,
    ürünün hiçbir yerde satılmadığı gibi görünüyordu.
    """
    try:
        w = svc.izleme_getir(db, k, izleme_id)
    except svc.IzlemeHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    # Ürün adı ilk taramada okunuyor; o ana kadar `ad` link kimliğidir
    # ("B0BSLHZKB6"). Onunla arama yapmak HER ZAMAN boş sonuç verir ve arayüz
    # bunu "eşleşme bulunamadı" diye gösterirdi — kullanıcı özelliğin
    # çalışmadığını sanır. Gerçek bir denemede tam olarak bu oldu: link
    # eklendi, hemen arandı, akakçe "B0BSLHZKB6" için hiçbir şey döndürmedi.
    # Boş liste yerine SEBEBİ söylüyoruz; toplayıcıya da gereksiz istek gitmez.
    if w.product.ad_gecici:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ürün adı henüz okunmadı — arama için önce ilk tarama gerekiyor. "
            "Birkaç dakika sonra tekrar dene.")

    cekici = HttpCekici()
    try:
        return toplayici.ara(cekici, w.product.ad)
    except toplayici.ErisimHatasi as e:
        # Kalıcı bir arıza değil; kullanıcı biraz sonra tekrar deneyebilir ya
        # da mağaza linkini elle ekleyebilir. Arayüz bunu böyle anlatıyor.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, str(e),
            headers={"Retry-After": "30"}) from e
    except toplayici.MesgulHata as e:
        # 503 + Retry-After: geçici bir doluluk, kalıcı bir hata değil.
        # Kuyruğa almak yerine hızlı reddediyoruz — bekleyen istek FastAPI'nin
        # iş parçacığı havuzunu tutar ve yeterince birikirse TÜM API durur.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, str(e),
            headers={"Retry-After": "5"}) from e
    finally:
        cekici.kapat()


@router.post("/{izleme_id}/kaynaklar", response_model=semalar.KaynakYaniti,
             status_code=status.HTTP_201_CREATED)
def kaynak_ekle(izleme_id: int, istek: semalar.KaynakEkleIstegi,
                k: Kullanici, db: DB):
    """Kullanıcının SEÇTİĞİ adayı bu ürüne kaynak olarak bağlar."""
    try:
        kaynak = svc.kaynak_ekle(db, k, izleme_id, str(istek.url))
    except svc.IzlemeHatasi as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    return urun_svc._kaynak(kaynak)

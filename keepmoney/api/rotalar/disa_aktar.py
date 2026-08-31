"""Dışa aktarma rotaları — CSV (BACKLOG H1)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from ...servisler import disa_aktar as svc
from ...servisler import izleme as izleme_svc
from ..deps import DB, Kullanici

# ÖNEK `/api`, `/api/izlemeler` DEĞİL. `izlemeler.py`nin router'ına
# eklenemezdi: yol `/api/izlemeler.csv` ve FastAPI/Starlette rota yolunun
# `/` ile başlamasını zorunlu tutuyor — `.csv` son ekli bir kardeş yol o
# önekle ifade edilemiyor. Ayrı bir router zaten doğru: dışa aktarma kendi
# ilgi alanı (BACKLOG Epik H) ve iki uç da aynı biçim kararlarını paylaşıyor.
router = APIRouter(prefix="/api", tags=["dışa aktarma"])

MEDYA_TURU = "text/csv; charset=utf-8"


def _csv_yaniti(icerik: str, dosya_adi: str) -> Response:
    """CSV'yi indirilebilir dosya olarak paketler.

    `attachment`: tarayıcı dosyayı GÖSTERMEK yerine indirsin. Bu olmadan
    Chrome `.csv`yi sekmede düz metin olarak açıyor — kullanıcı "indir"e
    basıp beyaz bir sayfa dolusu noktalı virgül görüyor.

    Dosya adı `servisler/disa_aktar.slug()` sayesinde HER ZAMAN ASCII ve
    yalnızca harf/rakam/tire içeriyor: ürün adı buraya kadar geliyor ve
    başlığa ham gelseydi tırnak ya da satır sonu içeren bir ad başlık
    enjeksiyonu olurdu.

    `no-store`: fiyat geçmişi kişisel veri. Ara belleklerde ve tarayıcı
    disk önbelleğinde kalmasının hiçbir faydası yok.
    """
    return Response(
        content=icerik,
        media_type=MEDYA_TURU,
        headers={
            "Content-Disposition": f'attachment; filename="{dosya_adi}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/izlemeler.csv", response_class=Response,
            responses={200: {"content": {"text/csv": {}}}})
def izlemeler_csv(k: Kullanici, db: DB):
    """Takip listesinin tamamı.

    Sahiplik süzgeci `izleme_svc.izlemeler()`in kendi `user_id` koşulu —
    burada ikinci bir süzgeç YAZILMIYOR. Yetki kuralının iki ayrı yerde
    yaşaması, birinin unutulduğu gün sessiz bir veri sızıntısıdır.
    """
    izlemeler = izleme_svc.izlemeler(db, k, kaynaklarla=True)
    return _csv_yaniti(svc.liste_csv(izlemeler), svc.liste_dosya_adi())


@router.get("/izlemeler/{izleme_id}/gecmis.csv", response_class=Response,
            responses={200: {"content": {"text/csv": {}}}})
def gecmis_csv(izleme_id: int, k: Kullanici, db: DB):
    """Tek ürünün ham fiyat geçmişi.

    `izleme_getir` başkasının izlemesinde `IzlemeHatasi` fırlatıyor ve
    burada 404'e çevriliyor — 403 DEĞİL: "yetkin yok" cevabı, o id'de bir
    kayıt OLDUĞUNU söyler. Uygulamanın geri kalanı da (bkz.
    `rotalar/izlemeler.py`) aynı kalıbı kullanıyor.
    """
    try:
        w = izleme_svc.izleme_getir(db, k, izleme_id)
    except izleme_svc.IzlemeHatasi as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    return _csv_yaniti(svc.gecmis_csv(db, w.product),
                       svc.gecmis_dosya_adi(w.product))

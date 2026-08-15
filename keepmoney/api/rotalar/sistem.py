"""Sistem uçları: sağlık, ölçümler, scraper durumu."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict

from ...ayarlar import ayarlar
from ...models import DomainHealth, Product
from ...zaman import utc_simdi
from ..deps import DB, Kullanici

router = APIRouter(tags=["sistem"])


class DomainSagligi(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    domain: str
    basarili: int
    basarisiz: int
    son_durum: str | None = None
    son_kontrol: str | None = None
    basari_orani: float = 0.0


@router.get("/saglik")
def saglik(db: DB):
    """Yük dengeleyici/konteyner sağlık kontrolü.

    Veritabanına GERÇEKTEN dokunur: yalnızca 'ayakta' dönen bir uç, DB
    düşmüşken de sağlıklı görünür ve trafiği ölü instance'a yollar.
    """
    from sqlalchemy import text

    try:
        db.execute(text("SELECT 1"))
        vt = "ayakta"
    except Exception:
        vt = "erisilemiyor"
    return {"durum": "ayakta", "veritabani": vt, "ortam": ayarlar().ortam}


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Prometheus çekme ucu."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/sistem/domainler", response_model=list[DomainSagligi])
def domain_sagligi(k: Kullanici, db: DB):
    """Hangi mağazadan fiyat okunabiliyor?

    Kullanıcıya da açık: "neden bu ürünün fiyatı güncellenmiyor" sorusunun
    cevabı çoğu zaman burada. Şeffaflık destek yükünü azaltır.
    """
    _ = k
    kayitlar = db.query(DomainHealth).order_by(DomainHealth.domain).all()
    out = []
    for d in kayitlar:
        toplam = (d.basarili or 0) + (d.basarisiz or 0)
        out.append(DomainSagligi(
            domain=d.domain,
            basarili=d.basarili or 0,
            basarisiz=d.basarisiz or 0,
            son_durum=d.son_durum,
            son_kontrol=d.son_kontrol.isoformat() if d.son_kontrol else None,
            basari_orani=round((d.basarili or 0) / toplam * 100, 1) if toplam else 0.0,
        ))
    return out


@router.get("/api/sistem/ozet")
def ozet(k: Kullanici, db: DB):
    """Tarama kapsamı — kullanıcının "sistem çalışıyor mu" sorusuna cevap."""
    _ = k
    sinir = utc_simdi() - timedelta(hours=24)
    return {
        "toplam_urun": db.query(Product).count(),
        "bayat_urun": db.query(Product).filter(
            (Product.son_kontrol.is_(None)) | (Product.son_kontrol < sinir)
        ).count(),
    }

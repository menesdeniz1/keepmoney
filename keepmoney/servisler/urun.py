"""Ürün use-case'leri: detay, fiyat geçmişi (grafik) ve bağlam/yorum."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import affiliate, analiz
from ..models import PriceReading, Product


def okumalar(db: Session, urun_id: int) -> list[analiz.Okuma]:
    satirlar = (db.query(PriceReading.ts, PriceReading.fiyat)
                .filter(PriceReading.product_id == urun_id)
                .order_by(PriceReading.ts)
                .all())
    return [analiz.Okuma(ts=ts, fiyat=f) for ts, f in satirlar if f]


def gunluk_seri(db: Session, urun_id: int) -> list[dict]:
    """Grafik verisi: gün başına TEK nokta (bkz. MIMARI K4).

    Ham okumaları göndermek grafiği de bozar: sık taranan ürün 48 nokta,
    seyrek taranan 2 nokta üretir ve çizgi yanıltıcı biçimde 'yoğun' görünür.
    """
    gunluk = analiz.gunluk_minimumlar(okumalar(db, urun_id))
    return [{"gun": g, "fiyat": f} for g, f in sorted(gunluk.items())]


def baglam(db: Session, urun: Product) -> dict | None:
    """'Bu iyi bir fiyat mı?' + insan cümlesi. Yeterli veri yoksa None."""
    if urun.guncel_fiyat is None:
        return None
    b = analiz.fiyat_baglami(okumalar(db, urun.id), urun.guncel_fiyat)
    if b is None:
        return None
    return {
        "sinyal": b.sinyal,
        "emoji": b.emoji,
        "yorum": analiz.yorum(b, urun.guncel_fiyat),
        "dip90": b.dip90,
        "medyan90": b.medyan90,
        "yuzdelik": b.yuzdelik,
        "tum_zamanlar_dibi": b.tum_zamanlar_dibi,
        "tum_zamanlar_dibi_tarih": b.tum_zamanlar_dibi_tarih,
        "en_dusuk_gun": b.en_dusuk_gun,
        "gun_sayisi": b.gun_sayisi,
        "sahte_indirim": b.sahte_indirim,
        "trend_yonu": b.trend_yonu,
        "iyi_firsat": b.iyi_firsat,
    }


def _kaynak(k) -> dict:
    """Kaynağı API biçimine çevirir; çıkış linkini burada üretir."""
    cikis, ortaklik_var = affiliate.cikis_linki(k.url)
    return {
        "id": k.id, "url": k.url, "host": k.host, "satici": k.satici,
        "son_fiyat": k.son_fiyat, "durum": k.durum,
        "son_kontrol": k.son_kontrol,
        "cikis_url": cikis, "ortaklik": ortaklik_var,
    }


def detay(db: Session, urun: Product) -> dict:
    """UrunDetay şemasına uyan sözlük — grafik + kaynaklar + yorum."""
    return {
        "id": urun.id,
        "ad": urun.ad,
        "kategori": urun.kategori,
        "guncel_fiyat": urun.guncel_fiyat,
        "guncel_satici": urun.guncel_satici,
        "puan": urun.puan,
        "yorum_sayisi": urun.yorum_sayisi,
        "son_kontrol": urun.son_kontrol,
        "kaynaklar": [_kaynak(k) for k in urun.sources],
        "gecmis": gunluk_seri(db, urun.id),
        "baglam": baglam(db, urun),
    }

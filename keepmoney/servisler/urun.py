"""Ürün use-case'leri: detay, fiyat geçmişi (grafik) ve bağlam/yorum."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .. import affiliate, analiz
from ..models import PriceReading, Product
from ..zaman import tr_gun


def okumalar(db: Session, urun_id: int) -> list[analiz.Okuma]:
    # `source_id` de çekilir (BACKLOG B2): `kaynak_serileri` bunu aynı
    # sonuçtan türetir, ikinci bir sorgu açmaz — "sorgu sayısı artmamış"
    # kabul ölçütü budur.
    satirlar = (db.query(PriceReading.source_id, PriceReading.ts, PriceReading.fiyat)
                .filter(PriceReading.product_id == urun_id)
                .order_by(PriceReading.ts)
                .all())
    return [analiz.Okuma(ts=ts, fiyat=f, source_id=source_id)
            for source_id, ts, f in satirlar if f]


def stok_yok_gunleri(db: Session, urun_id: int) -> dict[int, set[date]]:
    """BACKLOG B4 — kaynak başına, "tarandı ve stokta yoktu" günleri.

    `okumalar()`in `if f` süzgeci bu satırları (fiyat=None) zaten atıyor —
    doğru davranış, medyan/dip hesabı stok-yok satırlarını hiç görmemeli.
    Ama grafiğin "hiç taranmadı" ile "tarandı, stokta yoktu"yu ayırabilmesi
    için AYRI bir sorgu gerekiyor: ilki boşluk hiç göstermez, ikincisi
    çizgiyi keser (bkz. gunluk_seri/kaynak_serileri).
    """
    satirlar = (db.query(PriceReading.source_id, PriceReading.ts)
                .filter(PriceReading.product_id == urun_id,
                        PriceReading.stokta_var.is_(False))
                .all())
    out: dict[int, set[date]] = {}
    for source_id, ts in satirlar:
        out.setdefault(source_id, set()).add(tr_gun(ts))
    return out


def gunluk_seri(db: Session, urun_id: int,
                gecmis: list[analiz.Okuma] | None = None,
                stok_yok: dict[int, set[date]] | None = None) -> list[dict]:
    """Grafik verisi: gün başına TEK nokta (bkz. MIMARI K4).

    Ham okumaları göndermek grafiği de bozar: sık taranan ürün 48 nokta,
    seyrek taranan 2 nokta üretir ve çizgi yanıltıcı biçimde 'yoğun' görünür.

    BACKLOG B4 — bir gün yalnızca HİÇBİR kaynaktan fiyat gelmediyse VE en az
    bir kaynak o gün açıkça "stokta yok" dediyse boşluk sayılır
    (`fiyat: None, stokta: False`). Bir kaynak stokta yokken başka bir
    kaynaktan fiyat geldiyse ürün GERÇEKTEN alınabilir durumdaydı — o gün
    boşluk DEĞİL, gelen fiyatla gösterilir.
    """
    ham = okumalar(db, urun_id) if gecmis is None else gecmis
    fiyatlar = analiz.gunluk_minimumlar(ham)
    if stok_yok is None:
        stok_yok = stok_yok_gunleri(db, urun_id)
    boslukta: set[date] = set()
    for gunler in stok_yok.values():
        boslukta |= gunler
    boslukta -= fiyatlar.keys()
    return [{"gun": g, "fiyat": fiyatlar.get(g), "stokta": g not in boslukta}
            for g in sorted(fiyatlar.keys() | boslukta)]


def baglam(db: Session, urun: Product,
           gecmis: list[analiz.Okuma] | None = None) -> dict | None:
    """'Bu iyi bir fiyat mı?' + insan cümlesi. Yeterli veri yoksa None."""
    if urun.guncel_fiyat is None:
        return None
    ham = okumalar(db, urun.id) if gecmis is None else gecmis
    b = analiz.fiyat_baglami(ham, urun.guncel_fiyat)
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


def kaynak_serileri(urun: Product, gecmis: list[analiz.Okuma],
                    stok_yok: dict[int, set[date]] | None = None) -> list[dict]:
    """BACKLOG B2 — geçmişi kaynak bazında böler: grafikte mağaza başına
    ayrı çizgi çizilebilsin diye `PriceReading.source_id` zaten yazılıyordu
    (models.py yorumu) ama bu niyet hiç ürüne çıkmamıştı.

    TEK KAYNAKLI ÜRÜNDE BOŞ LİSTE döner: istemci fazladan bir "mağazalara
    ayır" düğmesi göstermemeli (B3) — birleşik `gecmis` zaten aynı çizgiyi
    çiziyor. `gecmis`, `detay()`'in `okumalar()`dan ZATEN çektiği liste —
    ikinci bir sorgu YOK.

    BACKLOG B4 — boşluk burada KAYNAK BAŞINA: `gunluk_seri`nin aksine
    "başka bir kaynaktan fiyat geldi mi" diye bakılmaz, HER ÇİZGİ KENDİ
    mağazasının o gün stokta olup olmadığını gösterir.
    """
    ham: dict[int, list[analiz.Okuma]] = {}
    for o in gecmis:
        ham.setdefault(o.source_id, []).append(o)

    if len(ham) < 2:
        return []

    stok_yok = stok_yok or {}
    host_map = {k.id: k.host for k in urun.sources}
    sonuc = []
    for source_id, okumalar in ham.items():
        fiyatlar = analiz.gunluk_minimumlar(okumalar)
        boslukta = stok_yok.get(source_id, set()) - fiyatlar.keys()
        sonuc.append({
            "kaynak_id": source_id,
            "host": host_map.get(source_id, "?"),
            "noktalar": [
                {"gun": g, "fiyat": fiyatlar.get(g), "stokta": g not in boslukta}
                for g in sorted(fiyatlar.keys() | boslukta)
            ],
        })
    return sonuc


def _kaynak(k) -> dict:
    """Kaynağı API biçimine çevirir; çıkış linkini burada üretir."""
    cikis, ortaklik_var = affiliate.cikis_linki(k.url)
    return {
        "id": k.id, "url": k.url, "host": k.host, "satici": k.satici,
        "son_fiyat": k.son_fiyat, "durum": k.durum,
        "son_kontrol": k.son_kontrol,
        "cikis_url": cikis, "ortaklik": ortaklik_var,
        "satici_sayisi": k.satici_sayisi, "ikinci_fiyat": k.ikinci_fiyat,
    }


def en_ucuz_magaza_url(urun: Product) -> str | None:
    """BACKLOG G3 — bildirimdeki "Mağazaya git" o an EN UCUZ kaynağa
    gitmeli, ilk eklenen kaynağa değil. Eleme kuralı `KaynakTablosu`nun
    `enUcuzKaynak`ıyla (arayuz/src/yardimcilar/kaynakDurumu.ts) BİREBİR
    aynı — durum OK ve fiyat bilinen: STOKTA_YOK ya da ENGELLİ bir kaynağın
    eski fiyatı "en ucuz" işaretlenirse kullanıcı satın alamayacağı bir
    mağazaya yönlenir.
    """
    adaylar = [k for k in urun.sources if k.durum == "OK" and k.son_fiyat is not None]
    if not adaylar:
        return None
    en_ucuz = min(adaylar, key=lambda k: k.son_fiyat)
    cikis, _ = affiliate.cikis_linki(en_ucuz.url)
    return cikis


def detay(db: Session, urun: Product) -> dict:
    """UrunDetay şemasına uyan sözlük — grafik + kaynaklar + yorum.

    Fiyat geçmişi BİR KEZ okunup hem grafiğe hem bağlama veriliyor. Eskiden
    `gunluk_seri` ve `baglam` ayrı ayrı sorguluyordu: her ürün detayında iki
    tam geçmiş taraması, üstelik bu uç arayüzde her ürün açılışında çağrılıyor.
    """
    gecmis = okumalar(db, urun.id)
    stok_yok = stok_yok_gunleri(db, urun.id)
    return {
        "id": urun.id,
        "ad": urun.ad,
        "kategori": urun.kategori,
        "guncel_fiyat": urun.guncel_fiyat,
        "guncel_satici": urun.guncel_satici,
        "puan": urun.puan,
        "yorum_sayisi": urun.yorum_sayisi,
        "son_kontrol": urun.son_kontrol,
        # BACKLOG A4 bu beşini UrunOzet'e ekledi ama bu sözlüğe YAZMAMIŞTI —
        # sonuç: UrunDetay'da hepsi sessizce None dönüyordu, DB'de değer
        # olsa bile (Pydantic eksik anahtarı alan varsayılanıyla dolduruyor).
        # BACKLOG A7'de gerçek tarayıcı ekran görüntüsüyle yakalandı: detay
        # sayfasında grafik veri gösterirken analiz kutusu "hiç fiyat
        # okunmadı" diyordu — çünkü `gecmis_gun` buradan hep None geliyordu.
        "sinyal": urun.sinyal,
        "dip90": urun.dip90,
        "medyan90": urun.medyan90,
        "yuzdelik": urun.yuzdelik,
        "gecmis_gun": urun.gecmis_gun,
        "kaynaklar": [_kaynak(k) for k in urun.sources],
        "gecmis": gunluk_seri(db, urun.id, gecmis, stok_yok),
        "seriler": kaynak_serileri(urun, gecmis, stok_yok),
        "baglam": baglam(db, urun, gecmis),
    }

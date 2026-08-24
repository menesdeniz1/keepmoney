#!/usr/bin/env python3
"""Ürün bağlam sütunlarını (sinyal/dip90/medyan90/yüzdelik) GERİYE DÖNÜK doldurur.

NEDEN VAR: bu sütunlar yalnızca worker'ın BİR SONRAKİ başarılı taramasında
dolar (bkz. `worker.py::urun_tara`). 35 ürünlük bir hesapta bu, aynı siteye
25 sn asgari aralık kuralı yüzünden ilk tur tamamlanana kadar (dakikalar)
panelin sinyalsiz kalması demek. Bu betik AĞA HİÇ ÇIKMADAN, veritabanında
zaten duran fiyat geçmişinden aynı hesabı yapıp sütunları doldurur —
worker'ın yapacağı işin görünür kısmını, taramayı beklemeden önden bitirir.

GÜVENLE TEKRAR ÇALIŞTIRILABİLİR: girdi (fiyat geçmişi) değişmediği sürece
sinyal/dip90/medyan90/yüzdelik/gecmis_gun için aynı sonucu üretir. Yalnızca
`baglam_ts` her çalıştırmada güncellenir — bu satırın "en son ne zaman
hesaplandığı" anlamına geldiği, `worker.py`deki A2 mantığıyla aynı.

KULLANIM
    python betikler/baglam_doldur.py
    python betikler/baglam_doldur.py --deneme   # yazmaz, ne olacağını gösterir
"""
from __future__ import annotations

import argparse
import contextlib
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

for _akis in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _akis.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(
        description="Ürün bağlam sütunlarını (sinyal, dip90, medyan90, "
                    "yüzdelik) fiyat geçmişinden geriye dönük doldurur.")
    ayristirici.add_argument("--deneme", action="store_true",
                             help="yazma, yalnızca ne olacağını göster")
    secim = ayristirici.parse_args(argv)

    from keepmoney import analiz
    from keepmoney.db import SessionLocal
    from keepmoney.models import PriceReading, Product
    from keepmoney.zaman import utc_simdi

    sinyalli = biriktiriyor = veri_yok = 0
    with SessionLocal() as db:
        urunler = db.query(Product).all()
        print(f"{len(urunler)} ürün taranıyor (veritabanından — ağa çıkılmıyor)\n")

        for urun in urunler:
            if not urun.guncel_fiyat:
                veri_yok += 1
                continue

            satirlar = (db.query(PriceReading.ts, PriceReading.fiyat)
                       .filter(PriceReading.product_id == urun.id)
                       .order_by(PriceReading.ts).all())
            gecmis = [analiz.Okuma(ts=ts, fiyat=f) for ts, f in satirlar if f]

            if not gecmis:
                veri_yok += 1
                continue

            gecmis_gun = len(analiz.gunluk_minimumlar(gecmis))
            baglam = analiz.fiyat_baglami(gecmis, urun.guncel_fiyat)

            if secim.deneme:
                durum = (f"sinyal={baglam.sinyal}" if baglam
                         else f"{gecmis_gun}/5 gün — henüz yetersiz")
                print(f"  ? {urun.ad[:52]:<52} {durum}")
                if baglam:
                    sinyalli += 1
                else:
                    biriktiriyor += 1
                continue

            # A2'deki YAZMA KURALIYLA BİREBİR AYNI: gecmis_gun/baglam_ts
            # MIN_GUN eşiğinden bağımsız güncellenir (A7'nin "N/7 gün"
            # göstergesi buna dayanıyor); sinyal ancak baglam hesaplanabildiyse
            # yazılır.
            urun.gecmis_gun = gecmis_gun
            urun.baglam_ts = utc_simdi()
            if baglam is not None:
                urun.sinyal = baglam.sinyal
                urun.dip90 = baglam.dip90
                urun.medyan90 = baglam.medyan90
                urun.yuzdelik = baglam.yuzdelik
                sinyalli += 1
            else:
                biriktiriyor += 1

        if not secim.deneme:
            db.commit()

    if secim.deneme:
        print(f"\n(deneme modu — hiçbir şey yazılmadı) "
              f"sinyal dolacaktı: {sinyalli} · geçmiş biriktiriyor: "
              f"{biriktiriyor} · veri yok: {veri_yok}")
        return 0

    print(f"\nSinyal dolduruldu: {sinyalli} · Geçmiş biriktiriyor: "
          f"{biriktiriyor} · Veri yok: {veri_yok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

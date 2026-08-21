#!/usr/bin/env python3
"""Bir link listesini bir hesabın takip listesine TOPLU ekler.

NEDEN VAR: ürünü tek tek arayüzden eklemek, 30-40 linklik bir liste için
(tipik "PC toplama" tablosu) yarım saatlik el işi. Bu araç aynı işi tek
komutta yapar ve — kritik nokta — **arayüzle AYNI servisi** çağırır:
`servisler/izleme.py::ekle`. Yani kota, kanonik URL birleştirme, SSRF
koruması ve "zaten izliyorsun" kontrolü birebir aynı çalışır (K13).

Doğrudan `INSERT` yazan ikinci bir yol AÇILMADI: o yol kanonik URL'yi
atlar ve aynı ürünü iki kez ekleyerek fiyat geçmişini böler — bu üründeki
en pahalı sessiz hata (K16).

KULLANIM
    python betikler/linkleri_ekle.py --dosya linkler.txt --eposta ben@ornek.com
    python betikler/linkleri_ekle.py --dosya linkler.txt --eposta ... --deneme

`--deneme`: hiçbir şey yazmaz, ne olacağını gösterir.

ÇIKIŞ KODU
    0 → her satır işlendi (eklendi ya da zaten vardı)
    1 → en az bir satır eklenemedi
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


def linkleri_oku(yol: pathlib.Path) -> list[str]:
    """`#` ile başlayan satırlar ve boşluklar atlanır (kaynak_dene.py ile
    aynı biçim — aynı dosya iki araca da verilebilsin)."""
    satirlar = []
    for ham in yol.read_text(encoding="utf-8").splitlines():
        satir = ham.strip()
        if satir and not satir.startswith("#"):
            satirlar.append(satir)
    return satirlar


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(
        description="Link listesini bir hesaba toplu ekler.")
    ayristirici.add_argument("--dosya", required=True, type=pathlib.Path)
    ayristirici.add_argument("--eposta", required=True,
                             help="hangi hesabın listesine eklenecek")
    ayristirici.add_argument("--deneme", action="store_true",
                             help="yazma, yalnızca ne olacağını göster")
    secim = ayristirici.parse_args(argv)

    if not secim.dosya.is_file():
        print(f"Dosya yok: {secim.dosya}", file=sys.stderr)
        return 2

    from keepmoney.db import SessionLocal
    from keepmoney.models import User
    from keepmoney.servisler import izleme as izleme_svc

    linkler = linkleri_oku(secim.dosya)
    print(f"{len(linkler)} link okundu: {secim.dosya}\n")

    eklendi = zaten = hata = 0
    with SessionLocal() as db:
        kullanici = (db.query(User)
                     .filter(User.email == secim.eposta).one_or_none())
        if kullanici is None:
            print(f"Hesap bulunamadı: {secim.eposta}", file=sys.stderr)
            mevcut = [k.email for k in db.query(User).all()]
            print(f"Kayıtlı hesaplar: {', '.join(mevcut) or '(yok)'}",
                  file=sys.stderr)
            return 2

        for url in linkler:
            if secim.deneme:
                # Kanonik biçimi GÖSTER: aynı ürünün farklı linkleri burada
                # tek satıra düşer ve kullanıcı bunu eklemeden görür.
                print(f"  ? {izleme_svc.url_normalize(url)}")
                continue
            try:
                w = izleme_svc.ekle(db, kullanici, url)
            except izleme_svc.KotaDoldu as e:
                print(f"  ! KOTA: {e}", file=sys.stderr)
                hata += 1
                break
            except izleme_svc.IzlemeHatasi as e:
                # "Zaten izliyorsun" bir hata DEĞİL: aynı ürünün ikinci
                # linki kanonik olarak aynı yere düşmüş demektir.
                if "zaten" in str(e).lower():
                    zaten += 1
                    print(f"  = zaten var: {url[:70]}")
                else:
                    hata += 1
                    print(f"  ! {e}: {url[:70]}", file=sys.stderr)
                continue
            eklendi += 1
            ad = w.product.ad if w.product else "?"
            print(f"  + {ad[:60]}")

    if secim.deneme:
        print("\n(deneme modu — hiçbir şey yazılmadı)")
        return 0

    print(f"\nEklendi: {eklendi} · Zaten vardı: {zaten} · Hata: {hata}")
    if eklendi:
        print("Fiyatlar ilk tarama turunda okunacak (worker çalışıyor olmalı).")
    return 1 if hata else 0


if __name__ == "__main__":
    raise SystemExit(main())

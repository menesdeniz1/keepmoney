#!/usr/bin/env python3
"""Yük ölçümü — "kaç kullanıcı kaldırır" sorusunun cevabı.

NEDEN VAR: Bu soru canlıya alma raporunda "ölçülmedi" diye duruyordu ve
ölçülmemiş bir kapasite, olmayan bir kapasitedir. İlk yüz kullanıcıda
çökmenin bedeli, ölçmenin bedelinden kat kat yüksek.

NE ÖLÇÜYOR: arayüzün EN SICAK iki yolu.
  • `GET /api/izlemeler`        — panel; her açılışta çağrılır
  • `GET /api/izlemeler/{id}`   — ürün detayı; tüm fiyat geçmişini okuyup
                                  analizden geçirir, yani asıl pahalı olan bu

VERİ GERÇEKÇİ SEÇİLDİ. Boş bir veritabanına yük bindirmek hiçbir şey
öğretmez: asıl risk geçmiş biriktikçe detay ucunun yavaşlaması. Varsayılan
kurgu ürün başına ~180 günlük okuma üretir.

KULLANIM
    python betikler/yuk_testi.py                       # varsayılan
    python betikler/yuk_testi.py --kullanici 50 --istek 2000 --es-zaman 32
    KEEPMONEY_VERITABANI_URL=postgresql+psycopg://... python betikler/yuk_testi.py

SINIRI: tek makinede, ağ gecikmesi olmadan ölçüyor. Gerçek dağıtımda
istemci gecikmesi ve TLS eklenir. Buradaki sayılar SUNUCU tarafının üst
sınırıdır, uçtan uca deneyim değil.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import pathlib
import random
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

for _akis in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _akis.reconfigure(encoding="utf-8", errors="replace")

import requests

KOK = pathlib.Path(__file__).resolve().parents[1]

# Ölçüm anahtarı ölçülen şeye ait olmalı: üretim anahtarıyla yük testi
# yapmak, onu süreç listesine ve loglara düşürmek demektir.
TEST_ANAHTARI = "yQ3vB8xK2mR7tL5nH9wZ4sJ6pD1gF0aC-eU8iO2kN7qT3rV5zX9yM4bW6hG1jS0d"


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def veri_uret(url: str, kullanici: int, urun: int, gun: int) -> list[tuple[str, str]]:
    """Doğrudan veritabanına yazar — HTTP üzerinden seed etmek dakikalar sürer.

    Dönen: (eposta, parola) listesi.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from keepmoney.guvenlik import parola_hashle
    from keepmoney.models import Base, PriceReading, Product, Source, User, Watch
    from keepmoney.zaman import utc_simdi

    motor = create_engine(url)
    Base.metadata.create_all(motor)
    oturum = sessionmaker(bind=motor)()

    parola = "yuktesti12345"
    hash_ = parola_hashle(parola)          # bcrypt pahalı: BİR kez hesapla
    simdi = utc_simdi()
    hesaplar: list[tuple[str, str]] = []

    for k in range(kullanici):
        eposta = f"yuk{k}@ornek.com"
        u = User(email=eposta, password_hash=hash_)
        oturum.add(u)
        oturum.flush()
        hesaplar.append((eposta, parola))

        for p in range(urun):
            urun_ = Product(ad=f"Ürün {k}-{p}", izleyen_sayisi=1,
                            guncel_fiyat=40000.0)
            oturum.add(urun_)
            oturum.flush()
            kaynak = Source(product_id=urun_.id, host="magaza.com",
                            url=f"https://magaza.com/{k}/{p}", son_fiyat=40000.0)
            oturum.add(kaynak)
            oturum.flush()
            oturum.add(Watch(user_id=u.id, product_id=urun_.id,
                             hedef_fiyat=38000.0))
            # Geçmiş: asıl maliyet burada. Günde bir okuma yeterli;
            # `gunluk_minimumlar` zaten güne indiriyor.
            oturum.bulk_save_objects([
                PriceReading(source_id=kaynak.id, product_id=urun_.id,
                             fiyat=38000 + random.random() * 6000,
                             ts=simdi - timedelta(days=g))
                for g in range(gun)])
        oturum.commit()

    oturum.close()
    motor.dispose()
    return hesaplar


def sunucu_baslat(url: str, port: int) -> subprocess.Popen:
    ortam = {
        **os.environ,
        "KEEPMONEY_ORTAM": "gelistirme",
        "KEEPMONEY_VERITABANI_URL": url,
        "KEEPMONEY_JWT_GIZLI_ANAHTAR": TEST_ANAHTARI,
        "KEEPMONEY_TELEGRAM_BOT_TOKEN": "",
        "KEEPMONEY_GIRIS_LIMITI": "100000",
        "KEEPMONEY_ARAYUZ_DIZINI": "",
    }
    ortam.pop("KEEPMONEY_TEST_VERITABANI_URL", None)
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "keepmoney.api.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        cwd=KOK, env=ortam)


def sunucuyu_bekle(taban: str, surec: subprocess.Popen) -> None:
    for _ in range(80):
        if surec.poll() is not None:
            raise SystemExit("sunucu açılmadı")
        try:
            requests.get(f"{taban}/saglik", timeout=1)
            return
        except requests.RequestException:
            time.sleep(0.25)
    raise SystemExit("sunucu zamanında ayağa kalkmadı")


def olc(ad: str, cagri, istek: int, es_zaman: int) -> dict:
    """Aynı çağrıyı N kez, M eşzamanlı iş parçacığıyla koşar."""
    sureler: list[float] = []
    hatalar = 0

    def tek(_):
        basla = time.perf_counter()
        try:
            kod = cagri()
        except Exception:
            return None
        gecen = time.perf_counter() - basla
        return gecen if kod == 200 else None

    basla = time.perf_counter()
    with ThreadPoolExecutor(max_workers=es_zaman) as havuz:
        for sonuc in havuz.map(tek, range(istek)):
            if sonuc is None:
                hatalar += 1
            else:
                sureler.append(sonuc)
    toplam = time.perf_counter() - basla

    if not sureler:
        return {"ad": ad, "hata": hatalar, "istek": istek}
    sirali = sorted(sureler)
    return {
        "ad": ad, "istek": istek, "hata": hatalar,
        "rps": len(sureler) / toplam,
        "p50": statistics.median(sirali) * 1000,
        "p95": sirali[int(len(sirali) * 0.95)] * 1000,
        "p99": sirali[min(int(len(sirali) * 0.99), len(sirali) - 1)] * 1000,
        "maks": sirali[-1] * 1000,
    }


def _yaz(s: dict) -> None:
    if "rps" not in s:
        print(f"  {s['ad']:<28} TAMAMEN BAŞARISIZ ({s['hata']}/{s['istek']})")
        return
    print(f"  {s['ad']:<28} {s['rps']:7.0f} rps   "
          f"p50 {s['p50']:6.1f} ms   p95 {s['p95']:6.1f} ms   "
          f"p99 {s['p99']:6.1f} ms   hata {s['hata']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="KeepMoney yük ölçümü")
    ap.add_argument("--kullanici", type=int, default=25)
    ap.add_argument("--urun", type=int, default=12, help="kullanıcı başına")
    ap.add_argument("--gun", type=int, default=180, help="ürün başına geçmiş")
    ap.add_argument("--istek", type=int, default=600)
    ap.add_argument("--es-zaman", type=int, default=16)
    args = ap.parse_args()

    gecici = tempfile.TemporaryDirectory()
    url = os.environ.get("KEEPMONEY_VERITABANI_URL",
                         f"sqlite:///{gecici.name}/yuk.sqlite")
    urun_toplam = args.kullanici * args.urun
    print(f"Veritabanı : {url.split('@')[-1]}")
    print(f"Kurgu      : {args.kullanici} kullanıcı × {args.urun} ürün "
          f"= {urun_toplam} ürün, ürün başına {args.gun} günlük geçmiş "
          f"({urun_toplam * args.gun:,} okuma)")

    basla = time.perf_counter()
    hesaplar = veri_uret(url, args.kullanici, args.urun, args.gun)
    print(f"Veri üretimi: {time.perf_counter() - basla:.1f} sn\n")

    port = _bos_port()
    taban = f"http://127.0.0.1:{port}"
    surec = sunucu_baslat(url, port)
    try:
        sunucuyu_bekle(taban, surec)

        oturumlar = []
        for eposta, parola in hesaplar:
            o = requests.Session()
            y = o.post(f"{taban}/api/auth/giris",
                       json={"eposta": eposta, "parola": parola}, timeout=30)
            y.raise_for_status()
            oturumlar.append(o)

        # Her istek RASTGELE bir kullanıcıyla: tek kullanıcının verisini
        # ısıtıp "hızlı" sonuç almak ölçümü değersiz kılardı.
        izlemeler = {}
        for o in oturumlar:
            izlemeler[o] = [w["id"] for w in
                            o.get(f"{taban}/api/izlemeler", timeout=30).json()]

        def panel():
            o = random.choice(oturumlar)
            return o.get(f"{taban}/api/izlemeler", timeout=30).status_code

        def detay():
            o = random.choice(oturumlar)
            wid = random.choice(izlemeler[o])
            return o.get(f"{taban}/api/izlemeler/{wid}", timeout=30).status_code

        print(f"Ölçüm      : {args.istek} istek, {args.es_zaman} eşzamanlı\n")
        for ad, cagri in (("panel (liste)", panel),
                          ("ürün detayı (grafik)", detay)):
            _yaz(olc(ad, cagri, args.istek, args.es_zaman))
    finally:
        surec.terminate()
        surec.wait(timeout=15)
        gecici.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

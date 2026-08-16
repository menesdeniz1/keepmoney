#!/usr/bin/env python3
"""Gerçek ürün linklerine karşı çekme + çıkarım denemesi.

NEDEN VAR: Bu üründe testlerin kapatamadığı TEK boşluk, site seçicilerinin
gerçek sayfalarda çalışıp çalışmadığıdır. Test paketi kayıtlı HTML'e karşı
koşar — yani "ayıklayıcı doğru yazılmış mı" sorusunu cevaplar, "trendyol.com
bugün hâlâ bu HTML'i mi veriyor" sorusunu değil. İkincisi ancak gerçek ağa
çıkarak ölçülür ve ölçülmeden canlıya alınırsa, ürün sessizce boş veriyle
çalışır: kullanıcı ekranda bir şey görür, arkada hiçbir fiyat yazılmamıştır.

Bu betik sistemin TAMAMINI ayağa kaldırmadan o ölçümü verir: veritabanı yok,
kullanıcı yok, worker yok. Tarama worker'ının kullandığı AYNI çekme zinciri
ve AYNI çıkarım fonksiyonu çağrılır (`HttpCekici` + `ayikla.cikar`), yani
buradaki sonuç canlıdaki sonuçtur — ayrı bir "test yolu" yazılmadı, çünkü
ayrı yol yazmak tam da ölçmek istediğimiz şeyi ölçmemek olurdu.

KULLANIM
    python betikler/kaynak_dene.py <url> [<url> ...]
    python betikler/kaynak_dene.py --dosya linkler.txt
    python betikler/kaynak_dene.py --dosya linkler.txt --html-kaydet hata_html/

`linkler.txt`: her satırda bir URL; `#` ile başlayan satırlar ve boş satırlar
atlanır.

ÇIKIŞ KODU
    0 → her URL'den fiyat okundu
    1 → en az bir URL'den okunamadı (CI'da eşik olarak kullanılabilir)

DİKKAT: Bu betik GERÇEK ağa çıkar ve gerçek sitelere istek atar. Host başına
gecikme uygulanır ve robots.txt'ye uyulur — worker'da olduğu gibi. Yüzlerce
link ile çalıştırmak nezaketsizliktir; site başına 5-10 link yeterlidir.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time
from collections import Counter
from dataclasses import dataclass

# Betik repo kökünden bağımsız çalışsın: `python betikler/kaynak_dene.py`
# çağrısında kök sys.path'te olmuyor.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from keepmoney import siteler
from keepmoney.ayikla import cikar
from keepmoney.cekici import HttpCekici
from keepmoney.fiyat import tl
from keepmoney.robots import RobotsKapisi
from keepmoney.servisler.izleme import url_normalize
from keepmoney.throttle import HostThrottle

# Güven zincirinin en zayıf halkası. Regex'ten gelen fiyat "okundu" sayılır
# ama SEVİNİLECEK bir sonuç değildir: sayfadaki herhangi bir sayıyı yakalamış
# olabilir (kargo bedeli, taksit tutarı, sponsorlu ürün). Payı yüksekse
# seçici yazılmalı — bu yüzden raporda ayrıca uyarı olarak gösteriliyor.
ZAYIF_GUVEN = {"regex"}


@dataclass
class Sonuc:
    url: str
    domain: str
    yontem: str = "yok"
    http_kodu: int | None = None
    fiyat: float | None = None
    guven: str = "yok"
    baslik: str | None = None
    sure_sn: float = 0.0
    sorun: str | None = None

    @property
    def basarili(self) -> bool:
        return self.fiyat is not None


def _linkleri_oku(args) -> list[str]:
    """Linkleri okur ve ÜRETİMDEKİ kanonik hâline çevirir.

    Kanoniklestirme burada yapılır, çekim anında değil: sistem linki önce
    normalize edip öyle saklıyor ve öyle çekiyor. Tarayıcıdan kopyalanan ham
    linki denemek, üretimin hiç uğramayacağı bir adresi ölçmek olurdu — ilk
    gerçek koşuda tam da bu fark etti (takip parametreli Hepsiburada linki
    robots.txt'ye takılıyordu, kanonik hâli takılmıyor).

    Tekilleştirme de kanonik hâl üzerinden: aynı ürüne giden iki farklı
    kampanya linki tek bir çekim etmeli.
    """
    linkler = list(args.url)
    if args.dosya:
        metin = pathlib.Path(args.dosya).read_text(encoding="utf-8")
        linkler += [s.strip() for s in metin.splitlines()
                    if s.strip() and not s.lstrip().startswith("#")]
    return list(dict.fromkeys(url_normalize(u) for u in linkler))


def _dene(cekici: HttpCekici, robots: RobotsKapisi, throttle: HostThrottle,
          url: str) -> tuple[Sonuc, str | None]:
    """Tek KANONİK URL'yi dener. HTML'i de döndürür — seçici yazarken lazım."""
    domain = siteler.host_cikar(url)
    s = Sonuc(url=url, domain=domain)

    if not robots.izin_var_mi(url):
        s.sorun = "robots.txt bu yolu yasaklıyor"
        return s, None

    # Worker'daki ile aynı nezaket: host başına aralık. Elle test ederken
    # atlamak cazip ama tam da bu betikle IP yasaklatmak istemeyiz.
    throttle.bekle(domain)

    kural = siteler.kural(url)
    basla = time.monotonic()
    cekim = cekici.cek(url, kural)
    s.sure_sn = time.monotonic() - basla
    s.yontem, s.http_kodu = cekim.yontem, cekim.http_kodu

    if cekim.hata:
        s.sorun = cekim.hata
        return s, None
    if cekim.engellendi:
        s.sorun = f"engellendi (HTTP {cekim.http_kodu})"
        return s, cekim.html
    if not cekim.html:
        s.sorun = f"boş gövde (HTTP {cekim.http_kodu})"
        return s, None

    c = cikar(cekim.html, kural, cekim.http_kodu)
    s.baslik, s.guven = c.baslik, c.guven
    if c.engelli:
        s.sorun = "bot koruması sayfası"
    elif c.olu:
        s.sorun = "ürün yok / sayfa ölü"
    elif c.fiyat is None:
        s.sorun = ("fiyat okunamadı — "
                   + ("`render: true` dene" if not kural.get("render")
                      else "`fiyat_secici` güncellenmeli"))
    else:
        s.fiyat = c.fiyat
    return s, cekim.html


def _satir_yaz(s: Sonuc) -> None:
    if s.basarili:
        isaret = "!" if s.guven in ZAYIF_GUVEN else "+"
        deger = f"{tl(s.fiyat)}  [{s.guven}]"
    else:
        isaret, deger = "-", s.sorun or "bilinmeyen"
    baslik = (s.baslik or "")[:48]
    print(f" {isaret} {s.domain:<24} {deger:<28} {s.yontem:<12} "
          f"{s.sure_sn:5.1f}sn  {baslik}")


def _rapor(sonuclar: list[Sonuc]) -> None:
    toplam = len(sonuclar)
    basarili = [s for s in sonuclar if s.basarili]
    zayif = [s for s in basarili if s.guven in ZAYIF_GUVEN]

    print("\n" + "─" * 78)
    oran = 100 * len(basarili) / toplam if toplam else 0
    print(f"OKUMA ORANI: {len(basarili)}/{toplam}  (%{oran:.0f})")

    # Site başına dökümü ayrıca ver: genel oran %80 iken tek bir sitenin
    # tamamen kırık olması ortalamada kaybolur ve düzeltilecek yer bulunamaz.
    print("\nSite başına:")
    for domain in sorted({s.domain for s in sonuclar}):
        grup = [s for s in sonuclar if s.domain == domain]
        ok = sum(1 for s in grup if s.basarili)
        durum = "TAMAM" if ok == len(grup) else ("KISMİ" if ok else "KIRIK")
        print(f"  {domain:<26} {ok}/{len(grup)}  {durum}")

    guvenler = Counter(s.guven for s in basarili)
    if guvenler:
        print("\nFiyat nereden geldi: "
              + ", ".join(f"{g}={n}" for g, n in guvenler.most_common()))
    if zayif:
        print(f"UYARI: {len(zayif)} fiyat regex ile bulundu — sayfadaki BAŞKA "
              "bir sayı olabilir. İlgili siteye `fiyat_secici` yaz.")

    kirik = [s for s in sonuclar if not s.basarili]
    if kirik:
        print("\nDüzeltilecekler:")
        for s in kirik:
            print(f"  {s.domain:<26} {s.sorun}")
            print(f"    {s.url}")
        print("\nSite kuralları: keepmoney/siteler/<domain>.yaml "
              "(şablon: _SABLON.yaml)")


def main() -> int:
    ayristirici = argparse.ArgumentParser(
        description="Gerçek ürün linklerine karşı çekme + fiyat çıkarımı dener.")
    ayristirici.add_argument("url", nargs="*", help="denenecek ürün linkleri")
    ayristirici.add_argument("--dosya", help="her satırda bir URL olan dosya")
    ayristirici.add_argument(
        "--html-kaydet", metavar="DIZIN",
        help="fiyat okunamayan sayfaların HTML'ini buraya yazar — seçici "
             "yazarken sayfayı elde tutmak gerekir")
    args = ayristirici.parse_args()

    linkler = _linkleri_oku(args)
    if not linkler:
        ayristirici.error("en az bir URL ver (ya da --dosya kullan)")

    kayit_dizini = pathlib.Path(args.html_kaydet) if args.html_kaydet else None
    if kayit_dizini:
        kayit_dizini.mkdir(parents=True, exist_ok=True)

    tanimli = set(siteler.tanimli_siteler())
    bilinmeyen = {siteler.host_cikar(u) for u in linkler} - tanimli
    if bilinmeyen:
        # Kural dosyası olmayan site HATA DEĞİLDİR — varsayılan zincir
        # (JSON-LD → meta → regex) çoğu sitede çalışır. Ama bilerek denendiğini
        # görmek gerekir, çünkü sonuç zayıf çıkarsa sebebi budur.
        print("Kural dosyası olmayan siteler (varsayılan zincir kullanılacak): "
              + ", ".join(sorted(bilinmeyen)) + "\n")

    cekici = HttpCekici()
    robots, throttle = RobotsKapisi(), HostThrottle()
    sonuclar: list[Sonuc] = []
    try:
        for url in linkler:
            s, html = _dene(cekici, robots, throttle, url)
            sonuclar.append(s)
            _satir_yaz(s)
            if kayit_dizini and not s.basarili and html:
                ad = f"{s.domain}-{abs(hash(url)) % 10**8}.html"
                (kayit_dizini / ad).write_text(html, encoding="utf-8")
                print(f"     HTML kaydedildi: {kayit_dizini / ad}")
    finally:
        # Playwright açıldıysa tarayıcı süreci kapanmalı — yoksa betik
        # bittiğinde arkada chromium kalır.
        cekici.kapat()

    _rapor(sonuclar)
    return 0 if all(s.basarili for s in sonuclar) else 1


if __name__ == "__main__":
    raise SystemExit(main())

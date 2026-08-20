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
import contextlib
import os
import pathlib
import sys
import time
from collections import Counter
from dataclasses import dataclass

# Betik repo kökünden bağımsız çalışsın: `python betikler/kaynak_dene.py`
# çağrısında kök sys.path'te olmuyor.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def _cikti_utf8() -> None:
    """Çıktıyı UTF-8'e sabitle.

    Bu aracın ÇIKTISININ TAMAMI Türkçe. Windows'ta Python, terminale
    yazmıyorsa (boru hattı, `> rapor.txt`) yerel kod sayfasını kullanıyor —
    genelde cp1252 — ve "ı, ş, ğ, —" gibi karakterler kodlanamıyor:

        UnicodeEncodeError: 'charmap' codec can't encode characters...

    Program o noktada ÇÖKÜYOR; hatta `--help` bile. Windows CI'da yakalandı.
    Etkileşimli PowerShell'de UTF-8 kullanıldığı için elle denemede
    görünmüyor — çıktıyı dosyaya yönlendiren ilk kullanıcıda patlıyor.

    `errors="replace"`: kodlanamayan bir karakter yüzünden RAPORU KAYBETMEK
    kabul edilemez; bozuk bir karakter göstermek her zaman daha iyidir.
    """
    for akis in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            akis.reconfigure(encoding="utf-8", errors="replace")


_cikti_utf8()


def _bagimlilik_uyarisi(hata: ImportError, windows: bool | None = None,
                       venv_var: bool | None = None) -> str:
    """Eksik bağımlılık için ÇALIŞTIRILABİLİR bir talimat üretir.

    Çıplak `ModuleNotFoundError: No module named 'yaml'` traceback'i,
    kullanıcıyı yanlış yöne gönderiyor: hata koddaymış gibi görünüyor, oysa
    sanal ortam etkin değil. Gerçek bir kullanımda tam olarak bu oldu —
    yeni bir PowerShell penceresinde `.venv` aktive edilmemişti ve ekranda
    yalnızca yığın izi vardı.

    Komutlar platforma göre değişiyor; Windows'ta `source` ve `python3` yok.

    Platform ve sanal ortam durumu PARAMETRE: testte `os.name`i global olarak
    değiştirmek `pathlib`i de bozuyor (o da `os.name`e bakıp WindowsPath
    seçiyor) — yani ortamı taklit etmenin bedeli süreci bozmaktı.
    """
    if windows is None:
        windows = os.name == "nt"
    if venv_var is None:
        venv_var = (pathlib.Path(__file__).resolve().parent.parent
                    / ".venv").is_dir()

    if windows:
        etkinlestir = r".\.venv\Scripts\Activate.ps1"
        kur = f"py -3 -m venv .venv ; {etkinlestir} ; pip install -r requirements.txt"
    else:
        etkinlestir = "source .venv/bin/activate"
        kur = f"python3 -m venv .venv && {etkinlestir} && pip install -r requirements.txt"

    adim = (f"  {etkinlestir}" if venv_var
            else f"  {kur}")
    return (
        f"\nBağımlılık eksik: {hata}\n\n"
        + ("Sanal ortam var ama ETKİN DEĞİL. Önce onu etkinleştir:\n"
           if venv_var else
           "Sanal ortam kurulu değil. Kur ve bağımlılıkları yükle:\n")
        + adim
        + "\n\nSonra bu komutu tekrar çalıştır. (Hata bir keepmoney modülünü "
          "gösteriyorsa sorun ortamda değil, kodda olabilir.)\n")


try:
    from keepmoney import siteler
    from keepmoney.ayikla import (
        _corba,
        _ld_bloklari,
        cikar,
        engel_mi,
        olu_mu,
        pazar_ayikla,
        stok_yok_mu,
    )
    from keepmoney.cekici import HttpCekici
    from keepmoney.fiyat import parse_tl, tl
    from keepmoney.robots import RobotsKapisi
    from keepmoney.servisler.izleme import url_normalize
    from keepmoney.throttle import HostThrottle
except ImportError as _hata:
    # Hatanın kendisi mesaja giriyor: gerçek bir kod hatasını gizlemeyelim.
    print(_bagimlilik_uyarisi(_hata), file=sys.stderr)
    raise SystemExit(2) from None

# Güven zincirinin en zayıf halkası. Regex'ten gelen fiyat "okundu" sayılır
# ama SEVİNİLECEK bir sonuç değildir: sayfadaki herhangi bir sayıyı yakalamış
# olabilir (kargo bedeli, taksit tutarı, sponsorlu ürün). Payı yüksekse
# seçici yazılmalı — bu yüzden raporda ayrıca uyarı olarak gösteriliyor.
ZAYIF_GUVEN = {"regex"}

# Fiyat adayı taramasının üst sınırları. `MAKS_ADAY_TARAMA` yalnızca dev
# sayfalarda işi bitirmek için; `GOSTERILEN_ADAY` ekranı boğmamak için.
# İKİSİ AYRI: sayım TÜM adaylar üzerinden yapılıyor, ekrana yalnızca bir
# kısmı yazılıyor. Eskiden tek sınır vardı ve hüküm de kesik listeye
# dayanıyordu — bu yüzden "bu ürünün fiyatı sayfada yok" demek KANITSIZDI.
MAKS_ADAY_TARAMA = 500
GOSTERILEN_ADAY = 8

# Sponsorlu / öneri kutusu izleri. Bu kapsayıcıların içindeki fiyat SAYFANIN
# ÜRÜNÜNE AİT DEĞİLDİR — başka bir ürünün reklamıdır.
#
# Neden bu uyarı var: gerçek bir Amazon sayfasında ana fiyat JS ile geliyordu
# ve HTML'deki tek fiyatlar `sp_detail_<ASIN>` kutularındaydı. Bu listeye
# bakıp seçici yazmak, 15.049 TL'lik bir reklamı 5.000 TL'lik kulaklığın
# fiyatı sanmak demekti. Hata SESSİZDİR: fiyat okunur, grafik çizilir,
# kullanıcı "dibe vurdu" uyarısı alır — hepsi yanlış üründen.
YABANCI_KUTU_IZLERI = (
    "sp_detail", "sponsored", "sp_atf", "sp_btf",   # Amazon sponsorlu
    "similarities", "recommend", "carousel", "oneri", "benzer",
    "also-viewed", "also-bought", "cross-sell", "upsell",
)


def _dosya_adi(domain: str, url: str) -> str:
    """Kaydedilecek HTML için GÜVENLİ dosya adı.

    Dış girdiden (host) doğrudan dosya adı üretmek platforma bağlı olarak
    sessizce bozuluyor. Windows CI'da yakalandı: `127.0.0.1:61749-...html`
    adındaki iki nokta NTFS'te "alternate data stream" ayracıdır, dolayısıyla
    içerik `127.0.0.1` adlı dosyanın gizli bir akışına yazılıyor — hata YOK,
    "kaydedildi" yazıyor, ama dosya ortada yok.

    Beyaz liste kullanılıyor (yasaklıları saymak yerine izinlileri saymak):
    platformların yasak karakter listeleri farklı ve zamanla değişiyor.

    ASCII'ye sabitlendi. `str.isalnum()` Unicode harfleri de geçirir ("ğ"
    alfanümeriktir) ama dosya adı taşınabilirliği okunabilirlikten önemli:
    alan adı burada yalnızca insana ipucu, ayırt ediciliği hash sağlıyor.
    """
    guvenli = "".join(
        c if (c.isascii() and c.isalnum()) or c in ".-_" else "_"
        for c in domain)
    return f"{guvenli[:60]}-{abs(hash(url)) % 10**8}.html"


def _baska_urun_mu(kimlik: str, atalar: list[str]) -> bool:
    """Bu fiyat sayfanın ürününe değil, bir reklam/öneri kutusuna mı ait?"""
    hepsi = " ".join([kimlik, *atalar]).lower()
    return any(iz in hepsi for iz in YABANCI_KUTU_IZLERI)


def _baslik_kaynaklari(corba) -> None:
    """`baslik_ayikla`nın baktığı üç kaynağı sırasıyla göster.

    Sıra önemli: og:title → h1 → <title>. İlk dolu olan kazanır, yani
    yanlış bir `h1` doğru `<title>`ı gölgeleyebilir.
    """
    print("\n── Ürün adı adayları (sırayla; ilk dolu olan kazanır) ──────")
    og = corba.select_one('meta[property="og:title"]')
    h1 = corba.find("h1")
    for etiket, deger in (
            ("og:title", og.get("content") if og else None),
            ("h1", h1.get_text(" ", strip=True) if h1 else None),
            ("<title>", corba.title.get_text(strip=True) if corba.title else None)):
        isaret = "→" if deger else " "
        print(f"   {isaret} {etiket:<10} {(deger or '(yok)')[:60]}")


@dataclass
class Sonuc:
    url: str
    domain: str
    yontem: str = "yok"
    # Zincirde denenen TÜM katmanlar. `yontem` yalnızca döndürülen yanıtınki;
    # hiçbiri temiz değilken gövdesi olan ilk deneme dönüyor ve satırda
    # "requests" görünüyor. Bu, "tarayıcı hiç denenmedi" izlenimi veriyordu:
    # gerçek bir koşuda iki Shopify mağazası için tam olarak bu yanlış sonuca
    # varıldı ve yükselme merdiveni bozuk sanıldı.
    denenenler: tuple[str, ...] = ()
    http_kodu: int | None = None
    fiyat: float | None = None
    guven: str = "yok"
    baslik: str | None = None
    sure_sn: float = 0.0
    sorun: str | None = None
    # Toplayıcı sayfalarında pazar derinliği. Normal koşuda GÖSTERİLİR:
    # bu seçiciler sessizce kırılırsa koruma katmanının "tek satıcı aykırı
    # ucuz" ölçütü devre dışı kalır ve geçmişi olmayan ürün savunmasız olur.
    # Yalnızca `--incele`de göstermek, kimsenin bakmadığı yere koymaktı.
    satici_adi: str | None = None
    satici_sayisi: int | None = None
    ikinci_fiyat: float | None = None

    @property
    def basarili(self) -> bool:
        return self.fiyat is not None

    @property
    def pazar_var(self) -> bool:
        return self.satici_sayisi is not None


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
    s.denenenler = cekim.denenenler

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
    s.satici_adi = c.satici_adi
    s.satici_sayisi = c.satici_sayisi
    s.ikinci_fiyat = c.ikinci_fiyat
    if c.engelli:
        s.sorun = "bot koruması sayfası"
    elif c.olu:
        s.sorun = "ürün yok / sayfa ölü"
    elif c.stok_yok:
        # Bu bir ARIZA DEĞİL. Ayırmazsak "seçici güncellenmeli" diyerek
        # asla tutmayacak bir seçici yazmaya gönderiyoruz.
        s.sorun = "stokta yok (sayfa sağlam, ürünün fiyatı yok)"
    elif c.fiyat is None:
        # `render` zaten açıkken SEBEBİ BİLMİYORUZ. Eskiden koşulsuz
        # "`fiyat_secici` güncellenmeli" deniyordu ve bu ÇOĞU ZAMAN YANLIŞTI:
        # gerçek bir koşuda Amazon'daki bir monitör böyle raporlandı, oysa
        # sayfadaki tüm fiyatlar sponsorlu kutulardaydı — yani ürünün kendi
        # fiyatı sayfada yoktu (satışta değil ya da JS ile geliyor) ve
        # yazılacak bir seçici yoktu. Tanı aracı bilmediği bir sebebi
        # SÖYLEMEMELİ; bilen komuta yönlendirmeli.
        s.sorun = ("fiyat okunamadı — "
                   + ("`render: true` dene" if not kural.get("render")
                      else "sebebi için `--incele` çalıştır"))
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

    # Başarısız satırda HANGİ KATMANLARIN denendiğini söyle. Satırdaki tek
    # "requests" kelimesi, tarayıcının hiç denenmediğini sandırıyordu.
    if not s.basarili and len(s.denenenler) > 1:
        print(f"     denenen katmanlar: {' → '.join(s.denenenler)}")

    # Seçicisi OLAN bir sitede fiyatın regex'ten gelmesi "okundu" gibi
    # görünür ama arızadır: altı seçicinin altısı da tutmamış demektir, yani
    # sayfa düzeni değişmiş ve okunan sayı sayfadaki ilk TL kalıbı — taksit
    # tutarı, kargo bedeli ya da başka bir satıcının fiyatı olabilir. Gerçek
    # bir koşuda aynı kulaklık için Amazon'dan 9.999,23 okunurken akakçe
    # 6.370 diyordu. Satırda tek bir "!" işareti bunu anlatmıyor.
    if s.basarili and s.guven in ZAYIF_GUVEN and \
            siteler.kural(s.domain).get("fiyat_secici"):
        print("     ! seçici tutmadı, fiyat gövde regex'inden — sayfadaki "
              "BAŞKA bir sayı olabilir; `--html-kaydet` ile incele")

    if s.pazar_var:
        parca = f"     🏪 {s.satici_sayisi} satıcı"
        if s.satici_adi:
            parca += f" · en ucuz: {s.satici_adi}"
        if s.ikinci_fiyat:
            parca += f" · 2.si {tl(s.ikinci_fiyat)}"
            if s.fiyat and s.ikinci_fiyat > s.fiyat * 1.5:
                parca += "  ⚠ TEK SATICI AYKIRI UCUZ"
        print(parca)
    elif siteler.kural(s.domain).get("toplayici") and s.basarili:
        # Toplayıcıdan fiyat geldi ama satıcı listesi okunamadı: koruma
        # ölçütü sessizce devre dışı demektir. Sessiz kalmak en kötüsü.
        print("     ! pazar derinliği OKUNAMADI — `saticilar_secici` kırık, "
              "koruma ölçütü devre dışı")


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
        # "TAMAM" yanıltıcı olabilir: hepsi okundu ama hepsi regex'ten
        # geldiyse hiçbirinin doğru olduğu belli değildir. Sessiz başarı
        # sessiz hatadan beter — özet satırında görünmeli.
        zayif_grup = sum(1 for s in grup if s.basarili and s.guven in ZAYIF_GUVEN)
        ek = f"   ({zayif_grup} zayıf okuma)" if zayif_grup else ""
        print(f"  {domain:<26} {ok}/{len(grup)}  {durum}{ek}")

    guvenler = Counter(s.guven for s in basarili)
    if guvenler:
        print("\nFiyat nereden geldi: "
              + ", ".join(f"{g}={n}" for g, n in guvenler.most_common()))
    if zayif:
        print(f"UYARI: {len(zayif)} fiyat regex ile bulundu — sayfadaki BAŞKA "
              "bir sayı olabilir.")
        # Bunlar İKİ AYRI arıza ve işleri de ayrı: seçicisi olmayan siteye
        # seçici yazılır; seçicisi OLAN sitede regex'e düşmek seçicinin
        # KIRILDIĞI anlamına gelir. İkincisi daha acil, çünkü sayfa düzeni
        # değişmiştir ve bu sessizce yanlış fiyat kaydeder. Tek bir "fiyat
        # seçici yaz" öğüdü, seçicisi zaten olan siteye yanlış iş gösteriyordu.
        kirik = sorted({s.domain for s in zayif
                        if siteler.kural(s.domain).get("fiyat_secici")})
        secicisiz = sorted({s.domain for s in zayif
                            if not siteler.kural(s.domain).get("fiyat_secici")})
        if kirik:
            print("  ! seçicisi VAR ama tutmadı (düzen değişmiş olabilir): "
                  + ", ".join(kirik))
        if secicisiz:
            print("  · `fiyat_secici` henüz yazılmamış: " + ", ".join(secicisiz))

    _basarisizlari_ayir([s for s in sonuclar if not s.basarili])


# Okunamayan her satır BİR ARIZA DEĞİL. Rapor hepsini "Düzeltilecekler"
# başlığı altında topluyordu ve 18 linklik bir denemede 5 satır çıkınca ürün
# beş yerinden bozukmuş gibi görünüyordu. Oysa gerçekte biri kullanıcının
# verdiği ÖLÜ bir linkti, üçü tasarım gereği toplayıcıya yönlendirilecek bot
# duvarıydı ve yalnızca biri gerçekten bakılacak bir işti.
#
# Yanlış önceliklendirme pahalı: düzeltilemeyecek şeylerle uğraşılırken
# düzeltilebilecek olan sırada bekliyor.
def _basarisizlari_ayir(kirik: list[Sonuc]) -> None:
    if not kirik:
        return

    olu = [s for s in kirik if s.sorun and "ölü" in s.sorun]
    duvar = [s for s in kirik if s.sorun
             and ("bot koruması" in s.sorun or "engellendi" in s.sorun)]
    stoksuz = [s for s in kirik if s.sorun and "stokta yok" in s.sorun]
    gercek = [s for s in kirik if s not in olu and s not in duvar
              and s not in stoksuz]

    if gercek:
        print("\n▸ DÜZELTİLECEK (gerçek iş):")
        for s in gercek:
            print(f"  {s.domain:<26} {s.sorun}")
            print(f"    {s.url}")
        print("  Site kuralları: keepmoney/siteler/<domain>.yaml "
              "(şablon: _SABLON.yaml)")

    if duvar:
        print("\n▸ BOT DUVARI — tasarım gereği toplayıcıya yönlendir:")
        print("  Bu siteler gerçek tarayıcıyla bile 403 dönüyor. Seçici "
              "yazmak ÇÖZMEZ.")
        print("  Ürünü akakçe kaynağına bağla — fiyat oradan okunuyor.")
        for s in duvar:
            print(f"  {s.domain:<26} {s.sorun}")

    if olu:
        print("\n▸ ÖLÜ LİNK — listeden çıkar:")
        print("  Sayfa kaldırılmış. Bizde düzeltilecek bir şey yok.")
        for s in olu:
            print(f"  {s.domain:<26} {s.url}")

    if stoksuz:
        print("\n▸ STOKTA YOK — arıza değil:")
        print("  Sayfa sağlam, ürünün o an fiyatı yok. Sistem bunu ayrı bir")
        print("  durum olarak kaydediyor.")
        for s in stoksuz:
            print(f"  {s.domain:<26} {s.url}")

    print(f"\n  Özet: {len(gercek)} gerçek iş · {len(duvar)} bot duvarı · "
          f"{len(olu)} ölü link · {len(stoksuz)} stokta yok")


def incele(yol: pathlib.Path, domain: str | None = None) -> int:
    """Kaydedilmiş HTML'i AĞA ÇIKMADAN çözümler: hangi adım neden tuttu/tutmadı.

    `--html-kaydet` ile bir sayfa diske alındıktan sonra soru şu olur:
    "seçici neden tutmadı?" Buna cevap vermek için elle regex çekmek yerine
    çıkarım zincirinin her basamağını tek tek raporluyoruz. Ağa çıkmadığı için
    istediğin kadar tekrar çalıştırabilirsin — seçici yazarken gereken tam
    olarak bu döngüdür.
    """
    html = yol.read_text(encoding="utf-8", errors="replace")
    # Dosya adı `<domain>-<hash>.html` biçiminde kaydediliyor; kuralı ondan bul.
    domain = domain or yol.name.rsplit("-", 1)[0]
    kural = siteler.kural(domain)

    print(f"Dosya : {yol}  ({len(html) // 1024} KB)")
    print(f"Site  : {domain}"
          + ("  (kural dosyası YOK — varsayılan zincir)" if not kural else ""))

    corba = _corba(html)
    baslik = corba.title.get_text(strip=True) if corba.title else "—"
    print(f"Başlık: {baslik}")

    # Ürün adı da yanlış okunabiliyor ve bu SESSİZ bir hatadır: fiyat doğru
    # olsa bile kullanıcı listede tanımadığı bir ad görür. Gerçek bir Amazon
    # sayfasında ad "Ürün özeti, temel ürün bilgilerini sunar…" diye
    # okunmuştu — sayfanın erişilebilirlik metni. Hangi kaynaktan geldiğini
    # görmeden düzeltilemez.
    _baslik_kaynaklari(corba)

    if engel_mi(html):
        print("\nSONUÇ: BOT KORUMASI SAYFASI. Seçici yazmanın anlamı yok —")
        print("       `render: true` dene, olmazsa siteyi listeden çıkar.")
        return 1
    if olu_mu(html):
        print("\nSONUÇ: ölü/kaldırılmış ürün sayfası.")
        return 1

    print("\n── Güven zinciri ──────────────────────────────────────────")
    print(f"1) JSON-LD bloğu    : {len(_ld_bloklari(corba))} adet")

    secici = kural.get("fiyat_secici")
    if secici:
        print(f"2) Site seçicisi    : {secici}")
        for parca in [p.strip() for p in secici.split(",")]:
            try:
                bulunan = corba.select(parca)
            except Exception as e:                       # geçersiz CSS
                print(f"   ! {parca}  → GEÇERSİZ SEÇİCİ: {e}")
                continue
            if not bulunan:
                print(f"   - {parca}  → 0 eşleşme")
                continue
            ornek = [el.get_text(strip=True)[:28] for el in bulunan[:3]]
            print(f"   + {parca}  → {len(bulunan)} eşleşme: {ornek}")
    else:
        print("2) Site seçicisi    : tanımsız")

    # `metin_alani` TEK BAŞINA iki korumanın kapsamı: regex son çaresinin ve
    # "stokta yok" serbest metin aramasının. Seçici sayfada tutmuyorsa ikisi de
    # SESSİZCE devre dışı kalır — ve sessiz devre dışı kalma bu üründeki en
    # pahalı hata sınıfı: fiyat okunamayan sayfa "ayıklayıcı bozuk" gibi
    # görünür, oysa ürün tükenmiş olabilir. Amazon düzeni A/B test ediyor,
    # yani `#centerCol` bir gün kaybolabilir; bunu ancak burada görürüz.
    kapsam_secici = kural.get("metin_alani")
    kapsam = corba.select_one(kapsam_secici) if kapsam_secici else None
    if not kapsam_secici:
        print("3) Metin alanı      : tanımsız — regex son çaresi TÜM sayfaya "
              "bakar, stok metni hiç aranmaz")
    elif kapsam is None:
        print(f"3) Metin alanı      : {kapsam_secici}  → 0 eşleşme "
              "(regex son çaresi ve stok metni DEVRE DIŞI)")
    else:
        uzunluk = len(kapsam.get_text(" ", strip=True))
        print(f"3) Metin alanı      : {kapsam_secici}  → var ({uzunluk} karakter)")

    # Stok kararı, "fiyat okunamadı" ile aynı görünen ama tamamen farklı bir
    # durum: biri arıza, diğeri normal. Hangisi olduğunu araç söylemezse
    # sağlam bir sayfa için boşuna seçici yazılır.
    stok_yok = stok_yok_mu(html, kural)
    print("4) Stok beyanı      : "
          + ("STOKTA YOK — sitenin kendi beyanı" if stok_yok
             else "stokta (ya da beyan bulunamadı)"))

    # Kapsayıcılar var mı ama içleri boş mu? Amazon gibi siteler düzeni
    # A/B test ediyor: id duruyor, fiyat başka bir kabuğa taşınıyor.
    # ÖNCE HEPSİNİ TOPLA, SONRA YAZ. Eskiden döngü 8'de kesiliyordu ve
    # "TÜM fiyatlar sponsorlu" hükmü O KESİK LİSTE üzerinden veriliyordu.
    # Amazon'da sponsorlu karusel DOM'da erken geldiği için sekiz yeri de o
    # dolduruyor; ürünün KENDİ fiyatı dokuzuncu sırada olsa listede hiç
    # görünmezdi ve araç yine de "bu ürünün fiyatı sayfada yok" diyordu.
    # Yani eksik kanıttan kesin hüküm — düzeltmeye çalıştığım hatanın ta
    # kendisi, kendi tanı aracımda.
    print("\n── Fiyat taşıyan elemanlar ────────────────────────────────")
    adaylar = corba.select("[class*=price], [id*=price], [id*=Price], "
                           "[class*=fiyat], [data-price-amount]")
    bulunanlar: list[tuple[float, str, list[str], bool]] = []
    for el in adaylar[:MAKS_ADAY_TARAMA]:
        deger = parse_tl(el.get_text(" ", strip=True)[:40])
        if not deger:
            continue
        kimlik = el.get("id") or ".".join(el.get("class") or []) or el.name
        ata = [a.get("id") for a in el.parents if a.get("id")][:2]
        bulunanlar.append((deger, kimlik, ata, _baska_urun_mu(kimlik, ata)))

    supheli = sum(1 for *_, yabanci in bulunanlar if yabanci)
    kendi = len(bulunanlar) - supheli

    # Yabancı OLMAYANLAR önce yazılır: aranan cevap onlar. Sponsorlu kutular
    # listeyi doldurup gerçek fiyatı ekrandan itmesin.
    sirali = sorted(bulunanlar, key=lambda s: s[3])
    for deger, kimlik, ata, yabanci in sirali[:GOSTERILEN_ADAY]:
        print(f"   {deger:>12,.2f}  ←  {kimlik[:34]:<34} "
              f"üst: {' < '.join(ata) or '—'}"
              + ("   ⚠ BAŞKA ÜRÜN" if yabanci else ""))

    yazilan = len(bulunanlar)
    if not yazilan:
        print("   (hiçbiri yok — fiyat büyük ihtimalle JS ile geliyor)")
    else:
        if yazilan > GOSTERILEN_ADAY:
            print(f"   … toplam {yazilan} aday "
                  f"({kendi} bu ürüne ait olabilir, {supheli} yabancı kutuda)")
        if supheli == yazilan:
            print("\n   ⚠ Sayfadaki TÜM fiyatlar sponsorlu/öneri kutularından")
            print(f"     ({yazilan} adayın {supheli}'i). Bu ürünün KENDİ fiyatı")
            print("     sayfada yok: ya stokta değil ya da JS ile geliyor. Bu")
            print("     kutulardan seçici YAZMA — sistem başka bir ürünün")
            print("     fiyatını bu ürüne yazar ve kimse fark etmez.")

    # Toplayıcıda pazar derinliği de doğrulanmalı: bu seçiciler çalışmazsa
    # koruma katmanının "tek satıcı aykırı ucuz" ölçütü sessizce devre dışı
    # kalır ve geçmişi olmayan ürün savunmasız olur (bkz. MIMARI K52).
    if kural.get("toplayici"):
        ad, sayi, ikinci = pazar_ayikla(html, kural)
        print("\n── Pazar derinliği (toplayıcı) ────────────────────────────")
        print(f"   en ucuz satıcı : {ad or '(okunamadı)'}")
        print(f"   satıcı sayısı  : {sayi if sayi is not None else '(okunamadı)'}")
        print(f"   2. en ucuz     : {tl(ikinci) if ikinci else '(okunamadı)'}")
        if sayi is None:
            print("   ! `saticilar_secici` tutmuyor — koruma ölçütü devre dışı.")

    c = cikar(html, kural)

    # FİYAT YOKSA KANIT GÖSTER: ürün kolonunun kendi metni.
    #
    # "Ürün tükenmiş" ile "fiyat JS ile gelmedi" ayrımı tam da bu metinde
    # duruyor ve tahmin etmeye gerek yok. Gerçek bir vakada (Amazon'da bir
    # monitör) araç şuraya kadar geliyordu: sayfa 1451 KB, başlık doğru,
    # `#centerCol` VAR — ama yalnızca 1134 karakter. Buybox'lı normal bir
    # sayfada orası binlerce karakterdir. Yani cevap o 1134 karakterin
    # içindeydi ve araç onu göstermediği için karar verilemedi; "ürün satışta
    # değil mi, yoksa bizim hatamız mı" sorusu açık kaldı.
    #
    # Stok kalıplarımız o metni tutmuyorsa eksik olan kalıptır ve eklenecek
    # ifadeyi ancak metni GÖREREK bulabiliriz.
    if c.fiyat is None and kapsam is not None:
        metin = " ".join(kapsam.get_text(" ", strip=True).split())
        print("\n── Ürün kolonunun metni (kanıt) ───────────────────────────")
        print("   " + (f"{metin[:800]}…" if len(metin) > 800
                       else metin or "(boş — buybox hiç render edilmemiş)"))

    print("\n── Sonuç ──────────────────────────────────────────────────")
    if c.stok_yok:
        print("   STOKTA YOK — sayfa sağlam, ürünün o an fiyatı yok.")
        print("   Seçici yazma: tutacak bir fiyat YOK. Sistem bunu ayrı bir")
        print("   durum olarak kaydediyor, arıza saymıyor.")
        return 1
    if c.fiyat is None:
        print("   Fiyat OKUNAMADI.")
        # ÖĞÜT YUKARIDAKİ LİSTEYLE ÇELİŞMEMELİ. Araç bir satır önce "bu
        # kutulardan seçici YAZMA" diye uyarıp hemen ardından "seçici yaz"
        # diyordu. Okuyan kişi doğal olarak sponsorlu kutudan seçici yazar,
        # sistem başka bir ürünün fiyatını bu ürüne kaydeder ve hata sessiz
        # kalır: grafik çizilir, "dibe vurdu" uyarısı gider. Bu yüzden öğüt
        # sayfanın gerçek durumuna göre ayrılıyor.
        yaml_yolu = f"keepmoney/siteler/{domain.replace('.', '_')}.yaml"
        if not yazilan or supheli == yazilan:
            if not yazilan:
                print("   Sayfada fiyat taşıyan HİÇBİR eleman yok.")
            else:
                print("   Sayfadaki fiyatların TAMAMI başka ürünlere ait; bu")
                print("   kutulardan seçici YAZMA.")
            if kural.get("render"):
                print("   `render: true` zaten açık — sayfa gerçek tarayıcıyla")
                print("   çekildi, yani eksik olan seçici değil. Geriye üç")
                print("   ihtimal kalıyor: ürün satışta değil, sayfa bot")
                print("   duvarının arkasında, ya da fiyat giriş/bölge")
                print("   gerektiriyor. Linki tarayıcıda aç ve gözünle doğrula.")
            else:
                print(f"   Önce {yaml_yolu} içine `render: true` koyup tekrar")
                print("   dene: fiyat büyük ihtimalle JS ile geliyor.")
        else:
            print("   Yukarıdaki listede doğru fiyatı görüyorsan, onun `üst:`")
            print("   sütunundaki id'yi kullanarak `fiyat_secici` yaz:")
            print(f"   {yaml_yolu}")
        return 1
    print(f"   {tl(c.fiyat)}  [{c.guven}]   {c.baslik or ''}")
    return 0


def main() -> int:
    ayristirici = argparse.ArgumentParser(
        description="Gerçek ürün linklerine karşı çekme + fiyat çıkarımı dener.")
    ayristirici.add_argument("url", nargs="*", help="denenecek ürün linkleri")
    ayristirici.add_argument("--dosya", help="her satırda bir URL olan dosya")
    ayristirici.add_argument(
        "--html-kaydet", metavar="DIZIN",
        help="fiyat okunamayan sayfaların HTML'ini buraya yazar — seçici "
             "yazarken sayfayı elde tutmak gerekir")
    ayristirici.add_argument(
        "--incele", metavar="DOSYA",
        help="kaydedilmiş bir HTML'i AĞA ÇIKMADAN çözümler: çıkarım "
             "zincirinin hangi adımı neden tuttu/tutmadı")
    ayristirici.add_argument(
        "--site", help="--incele ile: kural dosyası hangi site (dosya adından "
                       "bulunamazsa)")
    args = ayristirici.parse_args()

    if args.incele:
        return incele(pathlib.Path(args.incele), args.site)

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
                ad = _dosya_adi(s.domain, url)
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

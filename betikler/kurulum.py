#!/usr/bin/env python3
r"""Tek tık kurulum ve çalıştırma — `kur.bat` / `basla.bat` / `dur.bat`ın beyni.

NEDEN VAR: kurulum ve çalıştırma elle yapılıyordu ve GERÇEK kullanımda tam
burada takıldı. Kullanıcı iki ayrı PowerShell penceresi açmak, ikisinde de
doğru klasöre `cd` yapmak, sanal ortamı etkinleştirmek ve iki ayrı komut
çalıştırmak zorundaydı. Olan şu oldu: yeni pencere `C:\WINDOWS\system32`de
açıldı, `.\.venv\Scripts\Activate.ps1` bulunamadı, komutlar SİSTEM Python'ında
koştu ve tarama worker'ı TARAYICI MOTORU OLMADAN açıldı — ürünler tarandı,
hiçbirinden fiyat gelmedi (bkz. docs/DEVIR.md §5.12). Hata veren bir şey
yoktu; sistem çalışıyor görünüp boş dönüyordu.

Öncül projede (`menesdeniz1/tracker`) çift tıkla çalışan `kur.bat` ve
`calistir.bat` vardı; porta taşınmamıştı. Bu dosya onların karşılığıdır —
mantık `.bat` içinde değil BURADA, çünkü `.bat` test edilemez, Python edilir
(bkz. tests/test_kurulum.py).

── MODÜL DÜZEYİNDE YALNIZCA STDLIB IMPORT EDİLİR ────────────────────────
`kur` komutu `pip install`den ÖNCE, sistem Python'uyla çalışır: o anda ne
fastapi vardır ne pydantic. Buraya bir üçüncü parti import'u eklemek, kurulum
betiğini "kurulum yapılmadan çalışmaz" hale getirir — yani tam olarak çözmeye
çalıştığı sorunu üretir. Uygulama import'ları (`dogrula`, `basla`) FONKSİYON
İÇİNDE yapılır; o komutlar sanal ortamın Python'uyla çalışır.

── SANAL ORTAM ETKİNLEŞTİRİLMEZ ─────────────────────────────────────────
`Activate.ps1` PowerShell çalıştırma politikasına takılıyor ve bu tuzağa iki
kez düşüldü. Etkinleştirmenin tek yaptığı PATH'i değiştirmektir; biz zaten
`.venv\Scripts\python.exe`i TAM YOLUYLA çağırıyoruz. Aynı sonuç, sıfır tuzak.

KULLANIM
    python betikler/kurulum.py kur        # kur.bat çağırır (sistem python'u)
    .venv/.../python kurulum.py dogrula   # ortam eksiksiz mi (çıkış kodu 0/1)
    .venv/.../python kurulum.py basla     # API + worker + tarayıcı
    .venv/.../python kurulum.py dur       # ikisini de kapat
    python betikler/kurulum.py anahtar    # yeni JWT imza anahtarı bas
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import importlib.util
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass

KOK = pathlib.Path(__file__).resolve().parents[1]

# `python betikler/kurulum.py` çağrısında sys.path[0] `betikler/` oluyor ve
# `keepmoney` paketi BULUNAMIYOR. Ölçüldü: bu satır olmadan `dogrula` şema
# kontrolünde "No module named 'keepmoney'" veriyor ve — daha kötüsü — `.env`
# anahtar politikası kontrolü SESSİZCE atlanıyordu (docs/DEVIR.md §5.5).
# `kaynak_dene.py` aynı satırı aynı sebeple taşıyor.
sys.path.insert(0, str(KOK))


def _cikti_utf8() -> None:
    """Çıktıyı UTF-8'e sabitle.

    Bu betiğin çıktısının tamamı Türkçe. Windows'ta Python terminale
    yazmıyorsa (boru hattı, `> rapor.txt`) yerel kod sayfasına düşer ve
    "ı, ş, ğ, —" kodlanamayınca program ÇÖKER — `--help` bile.
    `betikler/kaynak_dene.py` aynı korumayı taşıyor; oradaki uzun açıklama
    burada da geçerli. `errors="replace"`: bozuk bir karakter göstermek,
    raporu tamamen kaybetmekten iyidir.

    `line_buffering=True` AYRI BİR SORUNU çözüyor ve gerçek koşuda görüldü:
    bu betik `pip`, `npm`, `alembic` alt süreçleriyle AYNI çıktıya yazıyor.
    Çıktı bir dosyaya/boruya yönlendirildiğinde Python blok tamponlamaya
    geçiyor, alt süreçler ise doğrudan yazıyor — sonuç, adımların yanlış
    sırada göründüğü bir kurulum günlüğü ("8/8 doğrulama" başlığı, kendi
    çıktısından SONRA basılıyordu). Kurulum günlüğü teşhis için okunur;
    sırası bozuksa yanlış adım suçlanır.
    """
    for akis in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            akis.reconfigure(encoding="utf-8", errors="replace",
                             line_buffering=True)


_cikti_utf8()

# ── Sabitler ──────────────────────────────────────────────────────
# `pyproject.toml`daki ruff target-version ve Dockerfile'daki
# python:3.12-slim ile aynı taban.
EN_AZ_PYTHON = (3, 12)

# JWT imza anahtarının bayt uzunluğu. `keepmoney/ayarlar.py`deki
# ONERILEN_ANAHTAR_BAYT ile AYNI olmak zorunda — burada tekrar yazılıyor
# çünkü bu dosya ayarlar.py'yi import EDEMEZ (pydantic henüz kurulu değil).
# İkisinin ayrışmasını bir test engelliyor.
ANAHTAR_BAYT = 48
ANAHTAR_ADI = "KEEPMONEY_JWT_GIZLI_ANAHTAR"

# Dinlenecek adres. VARSAYILAN 127.0.0.1 = YALNIZCA bu bilgisayar.
#
# Ev ağındaki telefondan bakmak için `KEEPMONEY_DINLEME=0.0.0.0` verilir.
# Bu bilinçli olarak ORTAM DEĞİŞKENİ, varsayılan değil: 0.0.0.0 demek
# "aynı ağdaki HERKES erişebilir" demektir. Ev ağında kabul edilebilir,
# ama kafede/otelde/ortak Wi-Fi'da değildir — ve hız sınırı vekil arkasında
# olmayı varsaydığı için (bkz. docs/MIMARI.md K24) doğrudan internete
# açılmamalıdır.
VARSAYILAN_HOST = "127.0.0.1"
API_HOST = os.environ.get("KEEPMONEY_DINLEME", "").strip() or VARSAYILAN_HOST

# Sağlık yoklaması HER ZAMAN yerel arayüzden yapılır: 0.0.0.0 bir hedef
# adres değil, "tüm arayüzler" demektir; ona bağlanmak platforma göre
# çalışmayabilir.
API_PORT = 8000
SAGLIK_URL = f"http://127.0.0.1:{API_PORT}/saglik"
ACILACAK_ADRES = f"http://localhost:{API_PORT}"

# API'nin ayağa kalkması için tanınan süre. Soğuk başlangıç (import zinciri +
# veritabanı bağlantısı) birkaç saniye; 60 sn cömert. Amaç yavaş makinede
# erken pes edip "açılmadı" dememek.
BASLAMA_ZAMAN_ASIMI_SN = 60

# Çalışan süreçlerin PID kaydı — `dur` bunu okur.
KAYIT_ADI = "calisan.json"

GEREKLI_PAKETLER: tuple[tuple[str, str], ...] = (
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("sqlalchemy", "SQLAlchemy"),
    ("alembic", "alembic"),
    ("pydantic", "pydantic"),
    ("pydantic_settings", "pydantic-settings"),
    ("jwt", "PyJWT"),
    ("bcrypt", "bcrypt"),
    ("yaml", "PyYAML"),
    ("bs4", "beautifulsoup4"),
    ("lxml", "lxml"),
    ("requests", "requests"),
    ("structlog", "structlog"),
    ("prometheus_client", "prometheus-client"),
    ("aiogram", "aiogram"),
)


class KurulumHatasi(Exception):
    """Kullanıcıya gösterilecek hata. `cozum` ÇALIŞTIRILABİLİR olmalı.

    Çıplak yığın izi kullanıcıyı yanlış yöne gönderiyor: hata koddaymış gibi
    görünüyor, oysa eksik olan ortamdır (aynı ders kaynak_dene.py'de de var).
    """

    def __init__(self, mesaj: str, cozum: str = "") -> None:
        super().__init__(mesaj)
        self.cozum = cozum


# ── Yollar ve sürümler ────────────────────────────────────────────


def venv_python(kok: pathlib.Path = KOK) -> pathlib.Path:
    """Sanal ortamın Python'u. Etkinleştirme yerine TAM YOL kullanılır."""
    if os.name == "nt":
        return kok / ".venv" / "Scripts" / "python.exe"
    return kok / ".venv" / "bin" / "python"


def python_surumu_sorunu(surum: tuple[int, ...]) -> str | None:
    """Sürüm yetersizse sebebi döner.

    Sürüm PARAMETRE: testte `sys.version_info`u global olarak değiştirmek
    süreci bozuyor (kaynak_dene.py'de platform aynı gerekçeyle parametre).
    """
    if tuple(surum[:2]) < EN_AZ_PYTHON:
        var = ".".join(str(p) for p in surum[:3])
        gerek = ".".join(str(p) for p in EN_AZ_PYTHON)
        return (f"Python {gerek}+ gerekli, bulunan {var}. "
                "https://www.python.org/downloads/ adresinden güncelle "
                "(kurulumda 'Add python.exe to PATH' işaretli olsun).")
    return None


# ── .env ve JWT anahtarı ──────────────────────────────────────────


def anahtar_uret() -> str:
    """CSPRNG çıktısı. Anahtar bir parola DEĞİL, rastgele bit dizisidir."""
    return secrets.token_urlsafe(ANAHTAR_BAYT)


_ATAMA = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def env_degeri(satirlar: list[str], ad: str) -> str | None:
    """`.env` içinden bir değeri okur. Değişken hiç yoksa None.

    Satır içi yorumu ATAR: bu depodaki `.env.example` gerçekten kullanıyor
    (`KEEPMONEY_SMTP_PORT=587   # 465 → doğrudan SSL`). python-dotenv de
    tırnaksız değerlerde aynısını yapıyor; burada farklı davranmak, dosyayı
    uygulamanın okuduğundan BAŞKA türlü okumak olurdu.
    """
    for satir in satirlar:
        eslesme = _ATAMA.match(satir)
        if not eslesme or eslesme.group(1) != ad:
            continue
        ham = eslesme.group(2).strip()
        if len(ham) >= 2 and ham[:1] in {'"', "'"} and ham[-1:] == ham[:1]:
            return ham[1:-1]
        return ham.split(" #")[0].strip()
    return None


def anahtar_satirini_doldur(satirlar: list[str],
                            anahtar: str) -> tuple[list[str], str]:
    """Anahtar satırı boşsa doldurur. Döner: (satırlar, 'yazildi'|'zaten_var'|'eklendi').

    VAR OLAN ANAHTARIN ÜZERİNE ASLA YAZILMAZ. Sebep iki:
      • anahtar değişirse dağıtılmış bütün oturum çerezleri geçersizleşir —
        herkes bir anda çıkış yapmış olur,
      • `kur.bat` onarım için tekrar tekrar çalıştırılabilen bir betiktir;
        her çalıştırmada kullanıcının yapılandırmasını bozamaz.
    """
    for i, satir in enumerate(satirlar):
        eslesme = _ATAMA.match(satir)
        if not eslesme or eslesme.group(1) != ANAHTAR_ADI:
            continue
        if eslesme.group(2).strip():
            return satirlar, "zaten_var"
        yeni = list(satirlar)
        yeni[i] = f"{ANAHTAR_ADI}={anahtar}"
        return yeni, "yazildi"
    return [*satirlar, f"{ANAHTAR_ADI}={anahtar}"], "eklendi"


def env_hazirla(kok: pathlib.Path = KOK, *, anahtar: str | None = None) -> str:
    """`.env` yoksa `.env.example`tan üretir, JWT anahtarı boşsa doldurur.

    Döner: yapılan işi anlatan kısa durum ('olusturuldu+yazildi' gibi).
    """
    env = kok / ".env"
    ornek = kok / ".env.example"
    durum = []

    if not env.is_file():
        if not ornek.is_file():
            raise KurulumHatasi(
                f"Ne {env.name} ne {ornek.name} var — depo eksik indirilmiş.",
                "git clone https://github.com/menesdeniz1/keepmoney")
        env.write_text(ornek.read_text(encoding="utf-8"), encoding="utf-8")
        durum.append("olusturuldu")

    try:
        metin = env.read_text(encoding="utf-8")
    except UnicodeDecodeError as hata:
        # Dosyayı yeniden yazmak bozuk kodlamayı KALICI hale getirirdi.
        raise KurulumHatasi(
            f".env UTF-8 olarak okunamadı ({hata.reason}).",
            "Dosyayı UTF-8 kaydet ya da sil; kur.bat yenisini üretir."
        ) from None

    satirlar, sonuc = anahtar_satirini_doldur(
        metin.splitlines(), anahtar or anahtar_uret())
    if sonuc != "zaten_var":
        env.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    durum.append(sonuc)
    return "+".join(durum)


# ── Arayüz derlemesi ──────────────────────────────────────────────


def npm_kurulum_gerekli_mi(node_modules: pathlib.Path,
                           kilit: pathlib.Path) -> bool:
    """`npm ci` gerekli mi?

    Her seferinde `npm ci` çalıştırmak DOĞRU ama pahalı: node_modules'ü silip
    baştan kuruyor, dakikalar sürüyor. `kur.bat` ise onarım amacıyla tekrar
    tekrar çalıştırılan bir betik. Uzlaşma: bağımlılıklar yoksa ya da kilit
    dosyası node_modules'ten YENİYSE kur, aksi halde yalnızca derle.

    Kilit karşılaştırması "package.json değişti ama kurulum eski" halini
    yakalar; atlanırsa derleme, olmayan bir paketi arayıp patlar.
    """
    if not node_modules.is_dir():
        return True
    if not kilit.is_file():
        return False
    return kilit.stat().st_mtime > node_modules.stat().st_mtime


def arayuzu_kopyala(dist: pathlib.Path, hedef: pathlib.Path) -> None:
    """Derlenmiş arayüzü `statik/` altına taşır (API oradan sunuyor).

    HEDEF ÖNCE TEMİZLENİR. Üzerine kopyalamak eski derlemenin dosyalarını
    bırakır: `sw.js` (PWA servis çalışanı) ve hash'li varlıklar birikir,
    tarayıcı eski sürümü sunmaya devam eder ve "derledim ama değişiklik
    görünmüyor" denir.

    Silme koruması: dizin doluysa ve içinde `index.html` YOKSA burası bizim
    ürettiğimiz bir çıktı olmayabilir — silmek yerine hata veriyoruz. Yanlış
    dizini silmek geri alınamaz.
    """
    if not (dist / "index.html").is_file():
        raise KurulumHatasi(
            f"Arayüz derlemesi bulunamadı: {dist}",
            "cd arayuz ; npm run build")
    if hedef.exists():
        if any(hedef.iterdir()) and not (hedef / "index.html").is_file():
            raise KurulumHatasi(
                f"{hedef} tanımadığımız dosyalar içeriyor; silmiyorum.",
                f"İçeriğini kontrol edip elle sil: {hedef}")
        shutil.rmtree(hedef)
    shutil.copytree(dist, hedef)


# ── Ortam kontrolü ────────────────────────────────────────────────


@dataclass
class Kontrol:
    ad: str
    tamam: bool
    detay: str = ""
    cozum: str = ""


def _k_saat_dilimi() -> Kontrol:
    """`tzdata` gerçekten çalışıyor mu.

    Windows'ta sistem tz veritabanı YOKTUR; paket eksikse uygulama import
    zincirinin en altında (`zaman.py`) patlar ve HİÇ açılmaz. Paketin kurulu
    olmasına değil ZoneInfo'nun AÇILMASINA bakıyoruz — ölçülmek istenen
    davranış bu (bkz. requirements.txt).
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo("Europe/Istanbul")
    except (ZoneInfoNotFoundError, KeyError) as hata:
        return Kontrol("saat dilimi", False,
                       f"Europe/Istanbul yüklenemedi: {hata}",
                       f'"{venv_python()}" -m pip install tzdata')
    return Kontrol("saat dilimi", True, "Europe/Istanbul")


def _k_paketler() -> Kontrol:
    eksik = []
    for modul, paket in GEREKLI_PAKETLER:
        try:
            var = importlib.util.find_spec(modul) is not None
        except (ImportError, ValueError):
            var = False
        if not var:
            eksik.append(paket)
    if eksik:
        return Kontrol("python paketleri", False, "eksik: " + ", ".join(eksik),
                       f'"{venv_python()}" -m pip install -r requirements.txt')
    return Kontrol("python paketleri", True, f"{len(GEREKLI_PAKETLER)} paket")


_CHROMIUM_SORGUSU = (
    "from playwright.sync_api import sync_playwright\n"
    "with sync_playwright() as p: print('YOL', p.chromium.executable_path)\n")


def _chromium_yolu() -> tuple[str, str]:
    """chromium'un yerini Playwright'a AYRI SÜREÇTE sorar. Döner: (yol, hata).

    NEDEN AYRI SÜREÇ: `sync_playwright()` bu sürümde kapanırken kendi asyncio
    görevini yarıda bırakıyor ve süreç sonunda ekrana yığın izi basıyor
    ("Task was destroyed but it is pending!" + TargetClosedError). ÖLÇÜLDÜ:
    sorgu BAŞARILIYKEN de basılıyor — yani kurulum betiği her çalıştığında
    sahte bir hata gösterirdi. "Her şey yerinde" diyen bir ekranın altındaki
    yığın izi, aracın kendisine olan güveni bitirir.

    Yolu KENDİMİZ HESAPLAMIYORUZ (PLAYWRIGHT_BROWSERS_PATH, sürüm numarası,
    platforma göre dizin adı…): o mantığın tek doğru sahibi Playwright.
    Kopyalanmış bir yol hesabı er ya da geç yanlış "chromium yok" hükmü verir.
    """
    sonuc = subprocess.run([sys.executable, "-c", _CHROMIUM_SORGUSU],
                           capture_output=True, text=True, check=False)
    for satir in sonuc.stdout.splitlines():
        if satir.startswith("YOL "):
            return satir[4:].strip(), ""
    # Başarısızlıkta sebebi GÖSTER: son satır genelde doğrudan ne yapılacağını
    # söylüyor ("Executable doesn't exist at …").
    satirlar = (sonuc.stderr or sonuc.stdout).strip().splitlines()
    return "", (satirlar[-1].strip() if satirlar
                else f"çıkış kodu {sonuc.returncode}")


def _k_tarayici_motoru() -> Kontrol:
    """Playwright VE chromium.

    Paketin kurulu olması YETMEZ: chromium indirilmemişse `render: true`
    isteyen bütün siteler (akakçe, Amazon, Trendyol, n11, cimri…) sessizce
    okunamaz hale gelir. Gerçek kurulumda tam olarak bu oldu — worker açıldı,
    tek satır uyarı verdi, hiçbir üründen fiyat gelmedi (docs/DEVIR.md §5.12).
    Bu yüzden ikisi AYRI kontrol ediliyor ve eksiklik `basla`yı durduruyor:
    sessiz boş çalışma, açık hatadan beterdir.
    """
    kur_komutu = (f'"{venv_python()}" -m pip install playwright ; '
                  f'"{venv_python()}" -m playwright install chromium')
    if importlib.util.find_spec("playwright") is None:
        return Kontrol("tarayıcı motoru", False, "playwright paketi yok",
                       kur_komutu)

    # Ayarlarda SİSTEM chromium'u gösterilmişse, Playwright'ın kendi indirdiği
    # sürüme bakmak yanlış cevap verir.
    with contextlib.suppress(Exception):
        from keepmoney.ayarlar import ayarlar
        elle = ayarlar().playwright_calistirilabilir
        if elle:
            var = pathlib.Path(elle).is_file()
            return Kontrol("tarayıcı motoru", var,
                           f"KEEPMONEY_PLAYWRIGHT_CALISTIRILABILIR={elle}",
                           "" if var else "Yolu düzelt ya da .env'de boş bırak")

    ham, hata = _chromium_yolu()
    if hata:
        return Kontrol("tarayıcı motoru", False, f"chromium sorulamadı: {hata}",
                       f'"{venv_python()}" -m playwright install chromium')
    yol = pathlib.Path(ham)
    if not yol.is_file():
        return Kontrol("tarayıcı motoru", False, f"chromium dosyası yok: {yol}",
                       f'"{venv_python()}" -m playwright install chromium')
    return Kontrol("tarayıcı motoru", True, f"chromium: {yol.parent.name}")


def _k_env(kok: pathlib.Path) -> Kontrol:
    """`.env` ve JWT anahtarının politikaya uygunluğu.

    Anahtarı burada denetlemek, uygulamanın açılışta reddetmesini ÖNCEDEN ve
    anlaşılır biçimde göstermek içindir; politikanın kendisi `ayarlar.py`de
    tekil kalıyor (K57) — kopyalansaydı ikisi ayrışırdı.
    """
    env = kok / ".env"
    if not env.is_file():
        return Kontrol(".env", False, "dosya yok", "kur.bat")
    deger = env_degeri(env.read_text(encoding="utf-8").splitlines(), ANAHTAR_ADI)
    if not deger:
        return Kontrol(".env", False, f"{ANAHTAR_ADI} boş",
                       f'"{venv_python()}" betikler\\kurulum.py anahtar')
    try:
        from keepmoney.ayarlar import anahtar_sorunu
    except ImportError as hata:
        # Sessizce "tamam" demek zayıf anahtarı görünmez kılardı; kontrolün
        # çalışmaması da bir eksikliktir ve söylenmeli.
        return Kontrol(".env", False, f"anahtar politikası okunamadı: {hata}",
                       f'"{venv_python()}" -m pip install -r requirements.txt')
    sorun = anahtar_sorunu(deger)
    if sorun:
        return Kontrol(".env", False, f"JWT anahtarı {sorun}",
                       f'"{venv_python()}" betikler\\kurulum.py anahtar')
    return Kontrol(".env", True, "JWT anahtarı yerinde")


def _k_sema(kok: pathlib.Path) -> Kontrol:
    """Veritabanı şeması göçlerle aynı sürümde mi.

    Yeni bir göç geldikten sonra eski şemayla açılan uygulama kullanıcıya
    "no such column" gibi anlaşılmaz bir hata verir — ya da daha kötüsü,
    yalnızca tek bir ekranda patlar. Açılıştan önce söylemek ucuz.
    """
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine

        from keepmoney.ayarlar import ayarlar
        from keepmoney.db import sqlite_dizinini_hazirla

        kafa = ScriptDirectory.from_config(
            Config(str(kok / "alembic.ini"))).get_current_head()
        url = ayarlar().veritabani_url
        sqlite_dizinini_hazirla(url)
        motor = create_engine(url)
        try:
            with motor.connect() as baglanti:
                surum = MigrationContext.configure(baglanti).get_current_revision()
        finally:
            motor.dispose()
    except Exception as hata:              # sebebi gizleme, kullanıcıya göster
        return Kontrol("veritabanı şeması", False, str(hata),
                       f'"{venv_python()}" -m alembic upgrade head')
    if surum != kafa:
        return Kontrol("veritabanı şeması", False,
                       f"şema {surum or 'kurulu değil'}, göçler {kafa}",
                       f'"{venv_python()}" -m alembic upgrade head')
    return Kontrol("veritabanı şeması", True, f"güncel ({kafa})")


def _k_arayuz(kok: pathlib.Path) -> Kontrol:
    """Derlenmiş arayüz `statik/` altında mı.

    Yoksa API arayüzü MOUNT ETMEZ (api/statik.py) ve `basla` tarayıcıda 404
    açardı: kullanıcı ürünün bozuk olduğunu sanır. Eksikliği söylemek, boş
    sayfa göstermekten iyidir.
    """
    if not (kok / "statik" / "index.html").is_file():
        return Kontrol("arayüz", False, "statik/index.html yok",
                       "kur.bat  (npm ci + npm run build yapar)")
    return Kontrol("arayüz", True, "statik/index.html")


def kontrolleri_calistir(kok: pathlib.Path = KOK) -> list[Kontrol]:
    """Sıra temelden yukarı: paketler yoksa gerisi zaten patlar."""
    return [
        _k_paketler(),
        _k_saat_dilimi(),
        _k_env(kok),
        _k_sema(kok),
        _k_tarayici_motoru(),
        _k_arayuz(kok),
    ]


def raporla(kontroller: list[Kontrol]) -> bool:
    """Kontrolleri ekrana basar. Döner: hepsi tamam mı."""
    genislik = max(len(k.ad) for k in kontroller)
    for k in kontroller:
        print(f"{' + ' if k.tamam else ' ! '}{k.ad.ljust(genislik)}  {k.detay}")
        if not k.tamam and k.cozum:
            print(f"{' ' * (genislik + 5)}çözüm: {k.cozum}")
    return all(k.tamam for k in kontroller)


# ── Süreç kaydı (basla / dur) ─────────────────────────────────────


def acilis_ani(simdi: float | None = None) -> float:
    """Makinenin açılış anı (epoch saniye). Bilinemiyorsa 0.

    NEDEN: `dur`, kayıttaki PID'leri öldürüyor. PID'ler yeniden kullanılır;
    makine yeniden başlatıldıysa kayıttaki 12345 artık BAŞKA bir sürecin
    numarasıdır. Yanlış süreci öldürmek, hiçbir şey öldürmemekten çok daha
    kötüdür — bu yüzden kayıt açılış anıyla birlikte tutuluyor ve açılış anı
    değişmişse kayıt bayat sayılır.
    """
    simdi = time.time() if simdi is None else simdi
    if os.name == "nt":
        with contextlib.suppress(Exception):
            return simdi - ctypes.windll.kernel32.GetTickCount64() / 1000
        return 0.0
    with contextlib.suppress(OSError, ValueError, IndexError),             open("/proc/uptime") as dosya:
        return simdi - float(dosya.read().split()[0])
    return 0.0


# Açılış anı iki ölçümde birebir aynı çıkmaz (sayaç çözünürlüğü, askıya alma).
# Yeniden başlatma bu değeri SAATLER kaydırır; tolerans o farkı değil,
# gürültüyü soğurmak için.
ACILIS_TOLERANS_SN = 300.0


def kayit_gecerli_mi(kayitli_acilis: float, simdiki_acilis: float) -> bool:
    """Kayıt bu açılış oturumuna mı ait?

    Açılış anı bilinmiyorsa (0) güvenilir bir şey söyleyemeyiz; kaydı geçerli
    sayıp kararı imaj adı kontrolüne bırakıyoruz.
    """
    if not kayitli_acilis or not simdiki_acilis:
        return True
    return abs(kayitli_acilis - simdiki_acilis) <= ACILIS_TOLERANS_SN


def kayit_yolu(kok: pathlib.Path = KOK) -> pathlib.Path:
    return kok / "data" / KAYIT_ADI


def kayit_yaz(surecler: list[dict], kok: pathlib.Path = KOK) -> None:
    yol = kayit_yolu(kok)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(
        json.dumps({"acilis": acilis_ani(), "surecler": surecler},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")


def kayit_oku(kok: pathlib.Path = KOK) -> dict | None:
    yol = kayit_yolu(kok)
    if not yol.is_file():
        return None
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def tasklist_imaji(cikti: str) -> str | None:
    """`tasklist /FO CSV /NH` çıktısından imaj adını alır. Eşleşme yoksa None.

    Eşleşme olmadığında tasklist CSV değil bir bilgi satırı basıyor
    ("INFO: No tasks are running..."); ayrıştırıcı buna hazırlıklı olmalı —
    yoksa "bulunamadı" ile "ilk sütun bilgi metni" karışır.
    """
    for satir in cikti.splitlines():
        satir = satir.strip()
        if satir.startswith('"'):
            return satir.split('","')[0].strip('"')
    return None


def surec_yasiyor_mu(pid: int, imaj: str = "") -> bool:
    """PID yaşıyor mu — ve (Windows'ta) beklediğimiz programa mı ait?

    İmaj adı kontrolü, PID yeniden kullanımına karşı ikinci savunma: kayıt
    bayatlamışsa bile öldürülecek şeyin en azından bizim python'umuz olduğunu
    doğrulamış oluruz.
    """
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return False
        return True
    sonuc = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=False)
    bulunan = tasklist_imaji(sonuc.stdout)
    if bulunan is None:
        return False
    return not imaj or bulunan.lower() == imaj.lower()


def surec_oldur(pid: int) -> bool:
    """Süreci ve ÇOCUKLARINI kapatır.

    `/T` şart: worker, Playwright üzerinden chromium süreçleri doğuruyor.
    Yalnızca ana süreci öldürmek arkada birkaç yüz MB'lık öksüz tarayıcı
    bırakır; bu da "kapattım ama bilgisayar yavaş" olarak geri döner.

    Nazik kapanma (SIGTERM / CTRL_BREAK) Windows'ta BAŞKA bir konsoldaki
    sürece gönderilemiyor. Kayıp sınırlı: yarım kalan tarama turu bir
    sonrakinde tekrarlanır, veritabanı işlemleri atomik.
    """
    if os.name != "nt":
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return False
        return True
    sonuc = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, text=True, check=False)
    return sonuc.returncode == 0


# ── Ağ ────────────────────────────────────────────────────────────


def port_bos_mu(port: int = API_PORT, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) != 0


def saglik_yanit_verdi_mi(url: str = SAGLIK_URL, zaman_asimi: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=zaman_asimi) as yanit:
            return 200 <= yanit.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


# ── Komutlar ──────────────────────────────────────────────────────


def _adim(no: int, toplam: int, baslik: str) -> None:
    print(f"\n── {no}/{toplam}  {baslik} " + "─" * max(3, 50 - len(baslik)))


def _komut(argv: list, *, cwd: pathlib.Path = KOK, ad: str = "",
           cozum: str = "") -> None:
    """Alt süreci çalıştırır; çıktısı DOĞRUDAN ekrana akar.

    Çıktı yutulmuyor: `pip`/`npm` hatalarının teşhisi tam da o metinde.
    """
    yazdirilan = " ".join(f'"{a}"' if " " in str(a) else str(a) for a in argv)
    print(f"   $ {yazdirilan}", flush=True)
    sonuc = subprocess.run([str(a) for a in argv], cwd=str(cwd), check=False)
    if sonuc.returncode != 0:
        raise KurulumHatasi(
            f"{ad or argv[0]} başarısız (çıkış kodu {sonuc.returncode}). "
            "Yukarıdaki çıktı sebebi söylüyor.", cozum)


def _arayuzu_derle(kok: pathlib.Path) -> None:
    arayuz = kok / "arayuz"
    # `npm` Windows'ta `npm.cmd`dir; PATH'ten tam yolunu bulmadan çağırmak
    # "WinError 2" veriyor ve hata, npm yokmuş gibi görünüyor.
    npm = shutil.which("npm")
    if npm is None:
        raise KurulumHatasi(
            "npm bulunamadı — arayüz derlenemez (web panosu açılmaz).",
            "Node.js 22+ kur: https://nodejs.org → sonra kur.bat'ı tekrar "
            "çalıştır.")
    if npm_kurulum_gerekli_mi(arayuz / "node_modules",
                              arayuz / "package-lock.json"):
        _komut([npm, "ci"], cwd=arayuz, ad="npm ci")
    else:
        print("   node_modules güncel, npm ci atlandı")
    _komut([npm, "run", "build"], cwd=arayuz, ad="npm run build")
    arayuzu_kopyala(arayuz / "dist", kok / "statik")
    print(f"   arayüz → {kok / 'statik'}")


def komut_kur(kok: pathlib.Path = KOK) -> int:
    toplam = 8
    print("KeepMoney kurulumu\n" + "=" * 62)
    print(f"Klasör : {kok}\nPython : {sys.executable}")

    sorun = python_surumu_sorunu(sys.version_info)
    if sorun:
        raise KurulumHatasi(sorun)

    _adim(1, toplam, "sanal ortam")
    py = venv_python(kok)
    if py.is_file():
        print(f"   zaten var: {py}")
    else:
        _komut([sys.executable, "-m", "venv", str(kok / ".venv")], ad="venv")
        if not py.is_file():
            raise KurulumHatasi(
                f"Sanal ortam kuruldu ama {py} yok.",
                "'.venv' klasörünü sil ve kur.bat'ı tekrar çalıştır.")

    _adim(2, toplam, "pip güncelleme")
    _komut([py, "-m", "pip", "install", "--upgrade", "pip"], ad="pip")

    _adim(3, toplam, "python paketleri")
    _komut([py, "-m", "pip", "install", "-r", str(kok / "requirements.txt")],
           ad="pip install")

    # Tarayıcı motoru requirements.txt'te DEĞİL (API onu kullanmıyor) ama
    # worker onsuz Türkiye'nin ana sitelerinin hiçbirinden fiyat okuyamaz.
    # Kurulumun isteğe bağlı adımı değil; buradaki en kritik adım.
    _adim(4, toplam, "tarayıcı motoru (playwright + chromium)")
    _komut([py, "-m", "pip", "install", "playwright"],
           ad="pip install playwright")
    _komut([py, "-m", "playwright", "install", "chromium"],
           ad="playwright install",
           cozum="Ağ/vekil sorunu olabilir; tekrar dene: "
                 f'"{py}" -m playwright install chromium')

    _adim(5, toplam, ".env ve JWT imza anahtarı")
    print(f"   {env_hazirla(kok)}")

    _adim(6, toplam, "veritabanı şeması")
    _komut([py, "-m", "alembic", "upgrade", "head"], ad="alembic")

    _adim(7, toplam, "arayüz derlemesi")
    _arayuzu_derle(kok)

    # Kurulumu "bitti" diye bildirmeden ÖNCE ölçüyoruz. Kontroller sanal
    # ortamın Python'uyla çalışmalı: fastapi, playwright ve ayarlar orada.
    _adim(8, toplam, "doğrulama")
    sonuc = subprocess.run(
        [str(py), str(pathlib.Path(__file__).resolve()), "dogrula"],
        cwd=str(kok), check=False)
    if sonuc.returncode != 0:
        print("\nKurulum tamamlanamadı — yukarıdaki eksikleri gider ve "
              "kur.bat'ı tekrar çalıştır.")
        return 1

    print("\n" + "=" * 62)
    print("KURULUM TAMAM.  Şimdi basla.bat dosyasına çift tıkla.")
    return 0


def komut_dogrula(kok: pathlib.Path = KOK) -> int:
    print("Ortam kontrolü\n" + "-" * 62)
    tamam = raporla(kontrolleri_calistir(kok))
    print("-" * 62)
    print("Her şey yerinde." if tamam
          else "EKSİK VAR — yukarıdaki çözümleri uygula ya da kur.bat çalıştır.")
    return 0 if tamam else 1


def komut_basla(kok: pathlib.Path = KOK) -> int:
    # `basla.bat` bunu zaten kontrol ediyor; betik elle çağrılırsa (ya da
    # `.venv` sonradan silinirse) çıplak FileNotFoundError yığın izi yerine
    # ne yapılacağını söyleyen bir mesaj görülsün.
    if not venv_python(kok).is_file():
        raise KurulumHatasi(f"Sanal ortam yok: {venv_python(kok)}",
                            "Önce kur.bat çalıştır.")

    if not port_bos_mu():
        # Aynı anda iki API açmak, ikincisinin sessizce ölmesi demektir.
        print(f"{API_PORT} portu dolu — KeepMoney zaten çalışıyor olabilir.")
        if saglik_yanit_verdi_mi():
            print(f"Evet, ayakta. Tarayıcı açılıyor: {ACILACAK_ADRES}")
            webbrowser.open(ACILACAK_ADRES)
            return 0
        print("Ama /saglik cevap vermiyor: portu başka bir program tutuyor.\n"
              "Önce dur.bat çalıştır; sürerse o programı kapat.")
        return 1

    print("Ortam kontrolü\n" + "-" * 62)
    if not raporla(kontrolleri_calistir(kok)):
        print("-" * 62)
        print("Eksik var; BAŞLATMIYORUM. Sebep: eksik ortamla açılan worker "
              "sessizce hiçbir fiyat okumaz —\nçalışıyor görünen boş bir "
              "sistem, açık bir hatadan beterdir. Önce kur.bat çalıştır.")
        return 1

    py = venv_python(kok)
    surecler = [
        ("api", [str(py), "-m", "uvicorn", "keepmoney.api.app:app",
                 "--host", API_HOST, "--port", str(API_PORT)]),
        ("tarayici", [str(py), "-m", "keepmoney.zamanlayici"]),
    ]
    # AYRI PENCERE: logları görebilmek için. Ayrıca yeni konsol, bu süreç
    # kapandığında çocukların hayatta kalmasını sağlıyor — `basla.bat`
    # penceresi kapanınca API ölmemeli.
    bayraklar = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    acilanlar = []
    kayit = []
    print("\nBaşlatılıyor (her biri kendi penceresinde):")
    for ad, argv in surecler:
        p = subprocess.Popen(argv, cwd=str(kok), creationflags=bayraklar)
        acilanlar.append((ad, p))
        kayit.append({"ad": ad, "pid": p.pid, "imaj": py.name})
        print(f"   {ad}  pid={p.pid}")
    kayit_yaz(kayit, kok)

    print(f"\nAPI'nin hazır olması bekleniyor ({SAGLIK_URL}) …")
    bitis = time.monotonic() + BASLAMA_ZAMAN_ASIMI_SN
    while time.monotonic() < bitis:
        if saglik_yanit_verdi_mi():
            print(f"Hazır. Tarayıcı açılıyor: {ACILACAK_ADRES}")
            webbrowser.open(ACILACAK_ADRES)
            print("\nKapatmak için: dur.bat")
            return 0
        # Beklemeye devam etmek, kullanıcıyı zaman aşımına kadar oyalar ve
        # asıl sebebi (kendi penceresindeki yığın izi) gizlerdi.
        olen = [ad for ad, p in acilanlar if p.poll() is not None]
        if olen:
            print(f"\n{', '.join(olen)} süreci kapandı. Kendi penceresindeki "
                  "hata mesajına bak.")
            return 1
        time.sleep(0.5)
    print(f"\nAPI {BASLAMA_ZAMAN_ASIMI_SN} sn içinde cevap vermedi. "
          "API penceresindeki mesajlara bak.")
    return 1


def komut_dur(kok: pathlib.Path = KOK) -> int:
    kayit = kayit_oku(kok)
    if not kayit:
        print(f"Çalışan kaydı yok (data/{KAYIT_ADI}).")
        print("Zaten kapalıysa sorun yok; değilse açık pencereleri kapat."
              if port_bos_mu() else
              f"AMA {API_PORT} portu dolu: elle başlatılmış olabilir, o "
              "pencereyi kapat.")
        return 0

    if not kayit_gecerli_mi(kayit.get("acilis", 0.0), acilis_ani()):
        # Yeniden başlatmadan sonra o PID'ler başkasının olabilir.
        print("Kayıt bu açılış oturumuna ait değil (makine yeniden "
              "başlatılmış).\nPID'lere dokunmuyorum — süreçler zaten kapalı.")
        kayit_yolu(kok).unlink(missing_ok=True)
        return 0

    kapandi = 0
    for s in kayit.get("surecler", []):
        pid, ad = int(s.get("pid", 0)), s.get("ad", "?")
        if not surec_yasiyor_mu(pid, s.get("imaj", "")):
            print(f"   {ad}  pid={pid}  zaten kapalı")
        elif surec_oldur(pid):
            print(f"   {ad}  pid={pid}  kapatıldı")
            kapandi += 1
        else:
            print(f"   {ad}  pid={pid}  KAPATILAMADI — pencereyi elle kapat")
    kayit_yolu(kok).unlink(missing_ok=True)
    print(f"\n{kapandi} süreç kapatıldı.")
    return 0


def komut_anahtar() -> int:
    print(anahtar_uret())
    return 0


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(
        prog="kurulum.py",
        description="KeepMoney kurulum ve çalıştırma yardımcısı "
                    "(kur.bat / basla.bat / dur.bat bunu çağırır).")
    altlar = ayristirici.add_subparsers(dest="komut", required=True)
    for ad, yardim in (
            ("kur", "sıfırdan kurulum (sistem Python'uyla çalıştırılır)"),
            ("dogrula", "ortam eksiksiz mi — çıkış kodu 0/1"),
            ("basla", "API ve tarama worker'ını başlat, tarayıcıyı aç"),
            ("dur", "başlatılan süreçleri kapat"),
            ("anahtar", "yeni JWT imza anahtarı üret ve bas")):
        altlar.add_parser(ad, help=yardim)

    secim = ayristirici.parse_args(argv)
    try:
        if secim.komut == "kur":
            return komut_kur()
        if secim.komut == "dogrula":
            return komut_dogrula()
        if secim.komut == "basla":
            return komut_basla()
        if secim.komut == "dur":
            return komut_dur()
        return komut_anahtar()
    except KurulumHatasi as hata:
        print(f"\nHATA: {hata}", file=sys.stderr)
        if hata.cozum:
            print(f"ÇÖZÜM: {hata.cozum}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nİptal edildi.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

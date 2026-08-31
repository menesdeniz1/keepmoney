"""Uçtan uca arayüz testleri — GERÇEK tarayıcı, GERÇEK sunucu.

Bu dosyanın varlık sebebi tek cümlede: *JSX'te bir düğmenin bulunması, o
düğmenin çalıştığının kanıtı değildir.* Diğer testler katmanları ayrı ayrı
doğruluyor; burada zincirin tamamı çalışıyor:

    tarayıcı → React → fetch → FastAPI → servis → veritabanı → yanıt → DOM

Ayağa kaldırılan şey ÜRETİMDEKİYLE aynı biçim: derlenmiş arayüz, API'nin
kendisi tarafından aynı kaynaktan sunuluyor (bkz. `api/statik.py`).

Atlama koşulları: playwright yoksa, chromium yoksa ya da arayüz
derlenmemişse. Test içinde tarayıcı İNDİRİLMEZ ve arayüz DERLENMEZ —
sessizce yanlış şeyi doğrulamaktansa açıkça atlamak doğrudur.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="playwright isteğe bağlı bağımlılık")

from playwright.sync_api import Page, expect, sync_playwright

KOK = Path(__file__).resolve().parents[1]
ARAYUZ_DIST = KOK / "arayuz" / "dist"

if not (ARAYUZ_DIST / "index.html").is_file():
    pytest.skip("arayüz derlenmemiş (arayuz/ içinde `npm run build`)",
                allow_module_level=True)

_CHROMIUM = os.environ.get("KEEPMONEY_PLAYWRIGHT_CALISTIRILABILIR", "").strip()
if not _CHROMIUM and os.path.exists("/opt/pw-browsers/chromium"):
    _CHROMIUM = "/opt/pw-browsers/chromium"


class _SunucuAdresi(str):
    """`sunucu` fixture'ının döndürdüğü değer.

    Normal bir URL dizgesi gibi davranır — `str` alt sınıfı olduğu için
    `f"{sunucu}/setler"` gibi MEVCUT tüm kullanımlar aynen çalışır. Ek
    olarak `.db_yolu` taşır: bazı senaryolar (BACKLOG A8 — sinyal sütunu
    yalnızca worker'ın GÜNLERCE çalışmasıyla dolar, bkz. DEVIR §4.1)
    tarayıcı etkileşimiyle KURULAMAZ; testin veritabanına doğrudan
    yazması gerekir — tıpkı worker testlerinde `PriceReading` satırlarının
    elle eklenmesi gibi (bkz. test_worker.py::_gecmis_ekle)."""
    db_yolu: pathlib.Path


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def sunucu(tmp_path_factory):
    """Gerçek uvicorn süreci + geçici veritabanı."""
    dizin = tmp_path_factory.mktemp("e2e")
    port = _bos_port()
    ortam = {
        **os.environ,
        "KEEPMONEY_ORTAM": "gelistirme",
        "KEEPMONEY_VERITABANI_URL": f"sqlite:///{dizin}/e2e.sqlite",
        "KEEPMONEY_JWT_GIZLI_ANAHTAR":
            "kQ7vZ2xR9tL4mB6nH1wY8sJ3pD5gF0aC-eU2iO7kN4qT9rV6zX1yM8bW3hG5jS0dA",
        "KEEPMONEY_ARAYUZ_DIZINI": str(ARAYUZ_DIST),
        # Testte gerçek Telegram/SMTP yok; uçların dürüst hata vermesi
        # de doğrulanan davranışın parçası.
        "KEEPMONEY_TELEGRAM_BOT_TOKEN": "",
        # Her test KENDİ hesabını açıyor ve hepsi 127.0.0.1'den geliyor.
        # Üretim limiti (saatte 5 kayıt/IP) burada testleri kilitler.
        # SINIR KAPATILMIYOR, yalnızca bu koşum için genişletiliyor —
        # 429 davranışının kendisi `test_api.py`de ayrıca doğrulanıyor.
        "KEEPMONEY_KAYIT_LIMITI": "500",
        "KEEPMONEY_GIRIS_LIMITI": "500",
    }
    ortam.pop("KEEPMONEY_TEST_VERITABANI_URL", None)

    # ── Sunucu çıktısı BORUYA DEĞİL DOSYAYA yazılır ──────────────
    #
    # Burası `stdout=subprocess.PIPE` idi ve borudan koşum boyunca HİÇ
    # okunmuyordu. Sonuç, teşhisi günler alabilecek bir arıza: uygulama
    # istek başına bir INFO satırı yazıyor, Windows'ta boru tamponu birkaç
    # on KB'de doluyor, dolduğu anda uvicorn'un log yazma çağrısı BLOKE
    # oluyor ve sunucu bütünüyle donuyor. Testler bunu "Page.goto ...
    # networkidle 30000ms" diye görüyordu — yani hata, sunucunun kilitli
    # olduğunu değil, sayfanın yüklenmediğini söylüyordu.
    #
    # ÖLÇÜLDÜ (bkz. docs/DEVIR.md §5.18): aynı akış boruyla 16. turda
    # kilitleniyor, `/saglik` dahil her istek ölüyor; çıktı dosyaya
    # yönlendirildiğinde 25 tur sorunsuz. Dosya hem bloke etmez hem
    # teşhis çıktısını KORUR — arıza anında altındaki `_sunucu_kaydi`
    # onu teste basıyor.
    kayit_yolu = dizin / "sunucu.log"
    kayit = kayit_yolu.open("w", encoding="utf-8")

    surec = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "keepmoney.api.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=KOK, env=ortam,
        stdout=kayit, stderr=subprocess.STDOUT,
    )

    def _sunucu_kaydi(sinir: int = 2000) -> str:
        kayit.flush()
        try:
            return kayit_yolu.read_text(encoding="utf-8", errors="replace")[-sinir:]
        except OSError:
            return "(sunucu kaydı okunamadı)"

    taban = _SunucuAdresi(f"http://127.0.0.1:{port}")
    taban.db_yolu = dizin / "e2e.sqlite"
    import urllib.error
    import urllib.request
    try:
        for _ in range(60):
            if surec.poll() is not None:
                pytest.fail(f"sunucu açılmadı:\n{_sunucu_kaydi()}")
            try:
                with urllib.request.urlopen(f"{taban}/saglik", timeout=1):
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)
        else:
            surec.kill()
            pytest.fail(f"sunucu zamanında ayağa kalkmadı:\n{_sunucu_kaydi()}")

        yield taban
    finally:
        surec.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            surec.wait(timeout=10)
        surec.kill()
        kayit.close()


@pytest.fixture(scope="module")
def tarayici():
    with sync_playwright() as pw:
        secenekler = {"headless": True}
        if _CHROMIUM:
            secenekler["executable_path"] = _CHROMIUM
        try:
            t = pw.chromium.launch(**secenekler)
        except Exception as e:                       # tarayıcı yok → atla
            pytest.skip(f"chromium başlatılamadı: {e}")
        yield t
        t.close()


@pytest.fixture
def sayfa(tarayici, sunucu):
    """Her test TEMİZ tarayıcı bağlamıyla başlar (çerez/önbellek paylaşılmaz)."""
    baglam = tarayici.new_context(viewport={"width": 1280, "height": 900},
                                  locale="tr-TR")
    s = baglam.new_page()
    # Beklenen 5xx'ler testin kendisi tarafından buraya eklenir. Örnek:
    # Telegram yapılandırılmamışken uç BİLEREK 503 döner (özellik gerçekten
    # kullanılamaz durumda) — bu bir kusur değil, doğrulanan davranıştır.
    s.beklenen_5xx = set()                           # type: ignore[attr-defined]
    s.sunucu_hatalari = []                           # type: ignore[attr-defined]

    def yakala(r):
        if r.status >= 500 and not any(
                p in r.url for p in s.beklenen_5xx):  # type: ignore[attr-defined]
            s.sunucu_hatalari.append(                 # type: ignore[attr-defined]
                f"{r.status} {r.request.method} {r.url}")

    s.on("response", yakala)
    yield s
    # Beklenmeyen HİÇBİR 5xx olmamalı: sunucu hatası, istemci hatasının
    # (4xx) aksine her zaman bizim kusurumuzdur.
    assert not s.sunucu_hatalari, s.sunucu_hatalari   # type: ignore[attr-defined]
    baglam.close()


def _kayit_ol(s: Page, taban: str) -> str:
    """Yeni hesap açar ve panele girer. Dönen: kullanılan e-posta."""
    eposta = f"e2e-{uuid.uuid4().hex[:10]}@ornek.com"
    s.goto(taban, wait_until="networkidle")
    s.get_by_text("Hesabım yok, oluştur").click()
    s.locator("input[type=email]").fill(eposta)
    s.locator("input[type=password]").fill("parola12345")
    # Kayıt onayı ZORUNLU (KVKK aydınlatma) — kutu işaretlenmeden düğme
    # kilitli. `check()` değil `click()`: kontrollü kutuda işaret ancak
    # React durumu güncellenince döner ve `check()` "durumu değişmedi" diye
    # patlar (bkz. BACKLOG §1'in bilinen tuzakları).
    s.locator("input[type=checkbox]").click()
    s.get_by_role("button", name="Hesap oluştur").click()
    s.wait_for_selector("text=Takip listem", timeout=15000)
    return eposta


def _urun_ekle(s: Page, url: str = "https://www.example.com/urun/ekran-karti",
               hedef: str = "45000") -> None:
    s.locator("input[type=url]").fill(url)
    if hedef:
        s.locator("input[type=number]").first.fill(hedef)
    s.get_by_role("button", name="Takibe al").click()


def _kullanicinin_urunu(db, eposta: str):
    """`sunucu` fixture'ı `scope="module"` — TEK bir DB, dosyadaki TÜM
    testler arasında PAYLAŞILIYOR ve hiç sıfırlanmıyor. `db.query(Product)
    .one()` bu yüzden YANLIŞ: bu testten ÖNCE çalışan başka testler zaten
    kendi ürünlerini eklemiş olabilir (birden fazla satır varsa `.one()`
    `MultipleResultsFound` fırlatır) — GERÇEKTEN ÖLÇÜLDÜ: tam paket içinde
    art arda koşunca bu yüzden kırıldı, tek başına çalıştırıldığında
    (pytest -k ile öncekiler deselect edilince) DB boş kaldığı için
    tesadüfen geçiyordu. Doğru sorgu kullanıcıya özgü olmalı."""
    from keepmoney.models import User, Watch

    kullanici = db.query(User).filter(User.email == eposta).one()
    izleme = db.query(Watch).filter(Watch.user_id == kullanici.id).one()
    return izleme.product


# ── Kimlik akışı ─────────────────────────────────────────────────

def test_acilista_giris_ekrani(sayfa, sunucu):
    sayfa.goto(sunucu, wait_until="networkidle")
    assert sayfa.locator("input[type=email]").count() == 1


def test_kayit_ve_panel(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    assert sayfa.get_by_role("heading", name="Takip listem").is_visible()
    # BACKLOG H2 — HENİZ HİÇ ÜRÜNÜ OLMAMIŞ kullanıcının boş paneli artık
    # tek satırlık "Henüz ürün eklemedin" kutusu değil, üç adımlı rehber.
    # O kısa satır KALDIRILMADI: rehber bir kez bittiğinde (ürün eklenip
    # sonra hepsi silindiğinde) geri geliyor — bkz.
    # `test_takipten_cikarma_onay_ister`, o test hâlâ o metni bekliyor.
    assert "Üç adımda başla" in sayfa.content()          # boş durum


def test_cikis_oturumu_gercekten_kapatir(sayfa, sunucu):
    """Çıkış bir dönem ÇALIŞMIYORDU: istemci yönlendirmesi, giriş yapılmış
    dalın `/giris → /` yönlendirmesiyle yarışıyor, kullanıcı panele geri
    atılıyor ve arka planda 401 yağıyordu."""
    _kayit_ol(sayfa, sunucu)
    sayfa.get_by_role("button", name="Çıkış yap").click()
    sayfa.wait_for_selector("input[type=email]", timeout=15000)
    assert sayfa.locator("input[type=email]").count() == 1

    # Korumalı sayfaya doğrudan gidiş de girişe düşmeli
    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    assert sayfa.locator("input[type=email]").count() == 1


def test_oturum_dolunca_giris_ekranina_dusulur(sayfa, sunucu):
    """Token uygulama açıkken dolabilir. Çerez silinip bir istek tetiklenince
    kullanıcı kırık hata kutularıyla değil, giriş ekranıyla karşılaşmalı."""
    _kayit_ol(sayfa, sunucu)
    sayfa.context.clear_cookies()                    # oturumun dolmasını taklit et
    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.wait_for_selector("input[type=email]", timeout=15000)
    assert sayfa.locator("input[type=email]").count() == 1


def test_parolami_unuttum_notr_cevap(sayfa, sunucu):
    sayfa.goto(sunucu, wait_until="networkidle")
    sayfa.get_by_text("Parolamı unuttum").click()
    sayfa.locator("input[type=email]").fill("herhangi@ornek.com")
    sayfa.get_by_role("button", name="Sıfırlama bağlantısı gönder").click()
    sayfa.wait_for_selector("text=kayıtlıysa", timeout=15000)


# ── Ana ürün akışı ───────────────────────────────────────────────

def test_urun_ekle_ve_detayini_ac(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa)
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    # BACKLOG C4: "İzlenen ürün" kutucuğu kaldırıldı — üst kutucuk satırının
    # gerçekten render olduğunun kanıtı artık "Dip bölgesinde" (aynı satır,
    # izlemeler.length > 0 olduğu sürece HER ZAMAN görünür).
    assert "Dip bölgesinde" in sayfa.content()

    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("text=Fiyat geçmişi", timeout=15000)
    assert "Kaynaklar" in sayfa.content()


def test_yeni_urunde_sinyal_degil_biriktiriliyor_gorunur(sayfa, sunucu):
    """BACKLOG A7 — gerçek çalıştırmada ölçüldü: worker 3 gün koştu, bir
    üründe %7,2 düşüş oldu ve hiç uyarı çıkmadı (yeterli geçmiş yoktu).
    Kullanıcı bunu görmeden "sistem bozuk mu" diye merak ediyordu.

    Yeni eklenen ürünün worker hiç taramadığı (bu test paketinde worker
    çalışmıyor, yalnızca API sunucusu var) için `sinyal`/`gecmis_gun` HER
    ZAMAN None — panel bunu renkli bir sinyal yerine nötr "geçmiş
    biriktiriliyor" ile göstermeli, "pahalı"/"ucuz"/"dibi" YAZMAMALI."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    # Panelde: kart nötr rozeti gösteriyor, panel üstünde toplu uyarı var.
    sayfa.wait_for_selector("text=geçmiş biriktiriliyor", timeout=15000)
    icerik = sayfa.content()
    assert "90 günün dibi" not in icerik
    assert "ucuz dönem" not in icerik
    assert "pahalı dönem" not in icerik
    assert "ürün için geçmiş biriktiriliyor" in icerik   # panel üstü banner

    # Detayda: aynı nötr mesaj, YorumKarti'nin baglam=null dalı.
    #
    # "text=Geçmiş biriktiriliyor" BURADA KULLANILAMAZ: Playwright'ın
    # `text=` eşleşmesi büyük/küçük harf duyarsız — panel kartındaki
    # (küçük harfle başlayan) SinyalRozeti metniyle de eşleşir ve
    # navigasyon tamamlanmadan test panel DOM'unda tatmin olabilir. Detaya
    # ÖZGÜ, panelde hiç geçmeyen "Fiyat geçmişi" başlığı bekleniyor.
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("text=Fiyat geçmişi", timeout=15000)
    assert "henüz hiç fiyat okunmadı" in sayfa.content()


def test_sinyalli_kartta_rozet_metni_ve_kivilcim_gorunur(sayfa, sunucu):
    """BACKLOG A8 — kartın "görünen sonucu": rozet + kıvılcım grafiği.

    Sinyal sütunu yalnızca worker'ın GÜNLERCE çalışmasıyla dolar (DEVIR
    §4.1) — tarayıcı etkileşimiyle kurulamaz. `test_worker.py::_gecmis_ekle`
    ile aynı ilkeyle (worker'ın normalde yazacağı veriyi testte elle
    kurmak) veritabanına doğrudan yazıyoruz — `sunucu.db_yolu` bunun için
    var (bkz. `_SunucuAdresi`).
    """
    from datetime import timedelta

    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import PriceReading, Source
    from keepmoney.zaman import utc_simdi

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    urun = _kullanicinin_urunu(db, eposta)
    kaynak = db.query(Source).filter(Source.product_id == urun.id).one()
    simdi = utc_simdi()
    for gun, fiyat in enumerate([1000, 950, 1100, 900, 850]):
        db.add(PriceReading(product_id=urun.id, source_id=kaynak.id,
                            fiyat=fiyat, ts=simdi - timedelta(days=4 - gun)))
    urun.guncel_fiyat = 850
    urun.sinyal = "dip"
    urun.dip90 = 850.0
    urun.medyan90 = 1000.0
    urun.yuzdelik = 92
    urun.gecmis_gun = 5
    db.commit()
    db.close()
    motor.dispose()

    # TanStack Query önbelleği eski (sinyalsiz) yanıtı tutuyor olabilir —
    # taze veri için sayfa yenileniyor (gerçek kullanıcının da yapacağı şey).
    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_selector("text=90 günün dibi", timeout=15000)
    assert sayfa.locator("svg[aria-label*='fiyat eğilimi']").count() >= 1


def test_ayni_urun_iki_kez_eklenince_hata_gosterilir(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa)
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("text=zaten izliyorsun", timeout=15000)


def test_ic_ag_adresi_arayuzde_reddedilir(sayfa, sunucu):
    """SSRF koruması sunucuda; kullanıcı ANLAMLI bir hata görmeli."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://127.0.0.1/gizli", hedef="")
    sayfa.wait_for_selector("text=izlenemez", timeout=15000)


def test_hedef_fiyat_ayarlanir_ve_kaldirilir(sayfa, sunucu):
    """BACKLOG E3'ten SONRA: "Hedef fiyat" artık kendi kutusu değil,
    `UyariKurulumu`nun bir onay kutusu — kutu işaretlenmeden girdi hiç
    görünmüyor (bkz. E3'ün "geçmiş yetersizken yüzde pasif" ilkesiyle aynı
    "önce aç, sonra doldur" deseni)."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("#hedef-fiyat-onay", timeout=15000)

    sayfa.locator("#hedef-fiyat-onay").check()
    sayfa.locator("#hedef-fiyat").fill("41000")
    sayfa.get_by_role("button", name="Kaydet").click()
    sayfa.wait_for_selector("text=41.000", timeout=15000)

    # Hedefi TEMİZLEME: kutuyu kaldırıp yeniden kaydetmek `hedef_fiyat: null`
    # gönderir (API'de açık `null` destekleniyor, arayüzde de olmalı).
    sayfa.locator("#hedef-fiyat-onay").uncheck()
    sayfa.get_by_role("button", name="Kaydet").click()
    sayfa.wait_for_timeout(1000)
    assert sayfa.locator("#hedef-fiyat").count() == 0
    assert "hedefin:" not in sayfa.content()


# ── Uyarı kurma arayüzü (BACKLOG E3) ──────────────────────────────

def _yeterli_gecmisli_urune_git(s: Page, sunucu, eposta: str) -> None:
    """Yüzde seçeneğinin AÇILABİLMESİ için worker'ın normalde günler
    içinde yazacağı `medyan90`/`gecmis_gun` sütunlarını elle kuruyoruz
    (bkz. A8 deseni) — bu paket içinde worker çalışmadığı için bunlar
    hiç dolmuyor, "geçmiş yetersiz" hâli SÜREKLİ olurdu."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    urun = _kullanicinin_urunu(db, eposta)
    urun.sinyal = "ucuz"
    urun.medyan90 = 1000.0
    urun.dip90 = 800.0
    urun.yuzdelik = 60
    urun.gecmis_gun = 30
    db.commit()
    db.close()
    motor.dispose()

    s.reload(wait_until="networkidle")


def test_yuzde_onizlemesi_yazarken_anlik_guncellenir(sayfa, sunucu):
    """Kabul ölçütü: önizleme yazarken anlık güncelleniyor — KAYDETMEYİ
    BEKLEMEZ, saf hesap her tuş vuruşunda çalışır."""
    eposta = _kayit_ol(sayfa, sunucu)
    # URL BİLEREK KENDİNE ÖZGÜ: varsayılan ("ekran-karti") başka testlerin
    # AYNI kanonik ürüne `gecmis_gun`/`medyan90` yazdığı, paylaşılan
    # `sunucu` DB'sinde çakışan bir üründü (bkz. C4/D3'teki aynı bulgu).
    _urun_ekle(sayfa, url="https://www.example.com/urun/e3-onizleme", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("#hedef-fiyat-onay", timeout=15000)

    _yeterli_gecmisli_urune_git(sayfa, sunucu, eposta)
    sayfa.wait_for_selector("#yuzde-dususu-onay", timeout=15000)

    sayfa.locator("#yuzde-dususu-onay").check()
    sayfa.locator("#yuzde-dususu").fill("15")
    # Hiçbir "Kaydet" tıklanmadı — önizleme yine de görünmeli.
    sayfa.wait_for_selector("#yuzde-onizleme", timeout=15000)
    assert "850,00" in sayfa.locator("#yuzde-onizleme").inner_text()

    sayfa.locator("#yuzde-dususu").fill("30")
    expect(sayfa.locator("#yuzde-onizleme")).to_contain_text("700,00", timeout=5000)


def test_gecmis_yetersizken_yuzde_secenegi_pasif(sayfa, sunucu):
    """Kabul ölçütü: geçmiş yetersizken yüzde seçeneği pasif ve sebebi
    yazıyor. Bu paket içinde worker çalışmadığı için YENİ eklenen ürünün
    `gecmis_gun`ü hep yetersiz (< 7)."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/e3-yetersiz-gecmis", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("#yuzde-dususu-onay", timeout=15000)

    kutu = sayfa.locator("#yuzde-dususu-onay")
    expect(kutu).to_be_disabled()
    assert "Yeterli geçmiş birikince kullanılabilir" in sayfa.content()
    # Girdi hiç görünmemeli — pasif seçenek doldurulamaz olmalı.
    assert sayfa.locator("#yuzde-dususu").count() == 0


def test_ozet_cumlesi_secili_kurallari_dogru_anlatir(sayfa, sunucu):
    """Kabul ölçütü: özet cümlesi seçili kuralları doğru anlatıyor —
    HEM hedef HEM yüzde seçilince 'ya da' ile birleşir (BACKLOG'un kendi
    örnek cümlesi)."""
    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/e3-ozet-cumlesi", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("#hedef-fiyat-onay", timeout=15000)

    _yeterli_gecmisli_urune_git(sayfa, sunucu, eposta)
    sayfa.wait_for_selector("#yuzde-dususu-onay", timeout=15000)

    # Önce hiçbiri seçili değil: yalnızca dip cümlesi.
    ozet = sayfa.locator("#uyari-ozet")
    expect(ozet).to_contain_text("dibini kırınca haber verilir", timeout=5000)

    sayfa.locator("#hedef-fiyat-onay").check()
    sayfa.locator("#hedef-fiyat").fill("5500")
    expect(ozet).to_contain_text("₺5.500,00 altına inince haber verilir", timeout=5000)
    assert "ya da" not in ozet.inner_text()

    sayfa.locator("#yuzde-dususu-onay").check()
    sayfa.locator("#yuzde-dususu").fill("15")
    expect(ozet).to_contain_text("₺5.500,00 altına inince ya da", timeout=5000)
    expect(ozet).to_contain_text("medyanın %15 altına düşünce", timeout=5000)


def test_susturma_ve_duraklatma(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("text=Bildirimler", timeout=15000)

    sayfa.get_by_role("button", name="7 gün sustur").click()
    sayfa.wait_for_timeout(1000)
    sayfa.get_by_role("button", name="Duraklat").click()
    sayfa.wait_for_selector("button:has-text('Devam ettir')", timeout=15000)


# ── Yeniden kurma / rearm (BACKLOG E4) ────────────────────────────

def _bildirim_gecmisi_kur(sunucu, eposta: str, *, gun_once: int, yeniden_kur_gun: int) -> None:
    """Worker'ın normalde bir alarm sonrası yazacağı `son_bildirim_ts`i
    elle kuruyoruz (bu paket içinde worker çalışmıyor) — `gun_once` gün
    önce bildirildi, `yeniden_kur_gun` gün sonra yeniden uyarır.

    Watch KULLANICIYA GÖRE bulunuyor (`_kullanicinin_urunu` ile AYNI
    User→Watch join), ürüne göre DEĞİL — `Watch.product_id == urun.id`
    ile aramak, ürün kimliği kullanıcılar arası PAYLAŞILDIĞI için (bkz.
    C4/D3/E3'teki AYNI bulgu) başka bir kullanıcının da aynı kanonik
    ürünü izlediği durumda `MultipleResultsFound` fırlatırdı — GERÇEKTEN
    ÖLÇÜLDÜ: bu iki test aynı varsayılan URL'yi kullanınca ikinci test
    tam bunu yaşadı."""
    from datetime import timedelta

    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import User, Watch
    from keepmoney.zaman import utc_simdi

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    w = db.query(Watch).filter(Watch.user_id == kullanici.id).one()
    w.son_bildirim_ts = utc_simdi() - timedelta(days=gun_once)
    w.son_bildirim_fiyat = 45000
    w.yeniden_kur_gun = yeniden_kur_gun
    db.commit()
    db.close()
    motor.dispose()


def test_kalan_sure_dogru_gosterilir(sayfa, sunucu):
    """Kabul ölçütü: kalan süre doğru gösteriliyor — hem kartta hem
    detayda (BACKLOG'un kendi örneği: "3 gün sonra yeniden uyarır")."""
    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/e4-kalan-sure", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    # 4 gün önce bildirildi, eşik 7 gün → kalan TAM 3 gün.
    _bildirim_gecmisi_kur(sunucu, eposta, gun_once=4, yeniden_kur_gun=7)
    sayfa.reload(wait_until="networkidle")

    sayfa.wait_for_selector("text=3 gün sonra yeniden uyarır", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("text=3 gün sonra yeniden uyarır", timeout=15000)


def test_simdi_yeniden_kur_butonu_bildirim_gecmisini_sifirlar(sayfa, sunucu):
    """Kabul ölçütü (dolaylı — E4'ün "tek tıkla" özelliği): buton
    `son_bildirim_ts`i sıfırlar, bekleme metni kaybolur."""
    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/e4-simdi-yeniden-kur", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    _bildirim_gecmisi_kur(sunucu, eposta, gun_once=1, yeniden_kur_gun=7)
    sayfa.reload(wait_until="networkidle")
    sayfa.locator("a[href^='/izleme/']").first.click()
    # ÖNCE detay sayfasına GERÇEKTEN geçildiğini doğrula ("Bildirimler"
    # yalnızca detayda var) — "gün sonra yeniden uyarır" metni PANEL
    # kartında da geçiyor (aynı `yenidenKurma.ts` çıktısı), bu yüzden
    # doğrudan onu beklemek geçiş TAMAMLANMADAN panel kartına karşı
    # tatmin olabilirdi (ÖLÇÜLDÜ: buton bulunamadı diye zaman aşımına
    # uğradı — hâlâ panelde bekleniyormuş).
    sayfa.wait_for_selector("text=Bildirimler", timeout=15000)
    sayfa.wait_for_selector("text=gün sonra yeniden uyarır", timeout=15000)

    sayfa.get_by_role("button", name="Şimdi yeniden kur").click()
    sayfa.wait_for_selector("text=gün sonra yeniden uyarır", state="detached", timeout=15000)
    assert sayfa.get_by_role("button", name="Şimdi yeniden kur").count() == 0


def test_takipten_cikarma_onay_ister(sayfa, sunucu):
    """Yıkıcı işlem onaysız çalışıyordu: yanlışlıkla tıklanan düğme aylarca
    biriken bir takibi geri alınamaz biçimde siliyordu."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("text=Takipten çıkar", timeout=15000)

    sayfa.get_by_role("button", name="Takipten çıkar").first.click()
    sayfa.wait_for_selector("dialog[open]", timeout=5000)

    sayfa.get_by_role("button", name="Vazgeç").click()
    sayfa.wait_for_timeout(500)
    assert sayfa.locator("dialog[open]").count() == 0
    assert "/izleme/" in sayfa.url                   # hâlâ duruyor

    sayfa.get_by_role("button", name="Takipten çıkar").first.click()
    sayfa.wait_for_selector("dialog[open]", timeout=5000)
    sayfa.locator("dialog[open]").get_by_role(
        "button", name="Takipten çıkar").click()
    sayfa.wait_for_selector("text=Henüz ürün eklemedin", timeout=15000)


# ── Set akışı (ürünün ayırt edici özelliği) ──────────────────────

def test_setin_icinden_coklu_urun_eklenir(sayfa, sunucu):
    """Ürün eklemenin TEK yolu her ürünün detay sayfasına ayrı ayrı gitmekti:
    8 parçalık bir PC için 8 sayfa. Kullanıcı set kurarken "bu sete hangi
    ürünler girer" diye düşünüyor; arayüz soruyu ters soruyordu.

    Bu test asıl akışı sürüyor: setin içinden listeden işaretle → tek kaydet.
    """
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/ekran-karti", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    _urun_ekle(sayfa, url="https://www.example.com/urun/islemci", hedef="")
    # `wait_for_function` BURADA KULLANILAMAZ: uygulamanın CSP'si `unsafe-eval`
    # vermiyor, Playwright dizgeyi sayfada eval edemiyor. Bu bir kısıt değil,
    # korumanın çalıştığının kanıtı — beklemeyi locator ile yapıyoruz.
    expect(sayfa.locator("a[href^='/izleme/']")).to_have_count(2, timeout=15000)

    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.locator("#set-adi").fill("PC Toplama")
    sayfa.locator("#set-butce").fill("84000")
    sayfa.get_by_role("button", name="Set kur").click()
    # "text=" DEĞİL: BACKLOG F4'ün şablon seçicisinde de aynı metinli bir
    # <option value="pc_toplama">PC Toplama</option> var — set adı BUNUNLA
    # çakışıyor (tesadüf, F4'ten önce yazılmış bir test). Başlık rolüyle
    # (<h3>) aramak <option>'ı (rolü "option") dışarıda bırakır.
    sayfa.get_by_role("heading", name="PC Toplama").wait_for(timeout=15000)
    assert "Boş." in sayfa.content()                 # boş set uyarısı

    sayfa.get_by_role("button", name="Ürün ekle").click()
    kutular = sayfa.locator("input[type=checkbox]")
    expect(kutular).to_have_count(2, timeout=15000)
    # İKİSİ BİRDEN tek kaydetmeyle — çoklu seçimin bütün amacı bu.
    kutular.nth(0).check()
    kutular.nth(1).check()
    sayfa.get_by_role("button", name="Ekle (2)").click()

    sayfa.wait_for_selector("text=2 ürün eklendi", timeout=15000)
    sayfa.get_by_role("button", name="Kapat").click()
    sayfa.wait_for_selector("text=2 ürün", timeout=15000)

    sayfa.get_by_role("button", name="Bütçeyi düzenle").click()
    sayfa.locator("input[id^='butce-']").fill("70000")
    sayfa.get_by_role("button", name="Kaydet").click()
    sayfa.wait_for_selector("text=70.000", timeout=15000)


def test_setin_icindekiler_gorunur_ve_cikarilabilir(sayfa, sunucu):
    """Set kartı yalnızca "1 ürün" yazıyordu — neyin toplandığı hiç
    görünmüyordu. Bütçe takibi yapılan bir listede bu eksikti."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.locator("#set-adi").fill("Kombin")
    sayfa.get_by_role("button", name="Set kur").click()
    sayfa.wait_for_selector("text=Kombin", timeout=15000)

    sayfa.get_by_role("button", name="Ürün ekle").click()
    sayfa.wait_for_selector("input[type=checkbox]", timeout=15000)
    sayfa.locator("input[type=checkbox]").first.check()
    sayfa.get_by_role("button", name="Ekle (1)").click()
    sayfa.wait_for_selector("text=1 ürün eklendi", timeout=15000)
    sayfa.get_by_role("button", name="Kapat").click()

    # "Ürün ekle" seti zaten açıyor: eklenen şeyi görmeden kapanması, az önce
    # ne olduğunu gizlerdi. Bu yüzden liste doğrudan görünür olmalı — ürünün
    # ADIYLA, sadece sayısıyla değil.
    sayfa.wait_for_selector("ul a[href^='/izleme/']", timeout=15000)
    assert sayfa.get_by_role("button", name="İçindekiler (1)").is_visible()

    sayfa.locator("button[aria-label*='setten çıkar']").first.click()
    sayfa.wait_for_selector("text=Boş.", timeout=15000)
    # ÜRÜN SİLİNMEZ: yalnızca gruplamadan çıkar.
    sayfa.goto(sunucu, wait_until="networkidle")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)


def test_ayni_urun_iki_sette_olabilir(sayfa, sunucu):
    """Bir ürün tek sete sıkışıyordu (`Watch.set_id`). Gerçekte aynı ekran
    kartı hem "PC Toplama" hem "Kara Cuma" listesinde olabilir."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    for ad in ("PC Toplama", "Kara Cuma"):
        sayfa.locator("#set-adi").fill(ad)
        sayfa.get_by_role("button", name="Set kur").click()
        # Başlık rolüyle: "PC Toplama" BACKLOG F4'ün şablon seçicisindeki
        # bir <option> metniyle de eşleşiyor, "text=" ikisini ayırt etmez.
        sayfa.get_by_role("heading", name=ad).wait_for(timeout=15000)

    sayfa.goto(sunucu, wait_until="networkidle")
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("legend", timeout=15000)
    # `check()` DEĞİL `click()`: bu kutular kontrollü — işaret ancak sunucu
    # cevabı gelip sorgu tazelenince dönüyor. `check()` anlık değişim bekleyip
    # "durumu değişmedi" diye patlıyordu; yanlış olan test, arayüz değil.
    kutular = sayfa.locator("fieldset input[type=checkbox]")
    kutular.nth(0).click()
    expect(kutular.nth(0)).to_be_checked(timeout=15000)
    kutular.nth(1).click()
    expect(kutular.nth(1)).to_be_checked(timeout=15000)

    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.wait_for_selector("text=1 ürün", timeout=15000)
    # İKİ set de aynı ürünü saymalı — eski modelde biri boş kalırdı.
    assert sayfa.get_by_text("1 ürün").count() == 2


def test_set_silme_onay_ister(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.locator("#set-adi").fill("Kombin")
    sayfa.get_by_role("button", name="Set kur").click()
    sayfa.wait_for_selector("text=Kombin", timeout=15000)

    sayfa.get_by_role("button", name="Seti sil (ürünler silinmez)").click()
    sayfa.wait_for_selector("dialog[open]", timeout=5000)
    sayfa.get_by_role("button", name="Vazgeç").click()
    sayfa.wait_for_timeout(400)
    assert "Kombin" in sayfa.content()


def test_set_butcesi_asinca_kirmizi_altindayken_yesil(sayfa, sunucu):
    """BACKLOG F1: "₺104.826 / bütçe ₺90.000" yazıyordu, ne kadar aştığı
    yoktu. Aşımda kırmızı + tutar/yüzde, altındayken yeşil, bütçesiz sette
    hiçbiri görünmüyor."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/f1-butce-asimi", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    # `db.close()` + `motor.dispose()`: kapatılmayan bağlantı SQLite'ın TEK
    # yazıcı kilidini gereksiz yere elinde tutabilir (bkz.
    # `test_sinyalli_kartta_rozet_metni_ve_kivilcim_gorunur` aynı desen).
    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    urun = _kullanicinin_urunu(db, eposta)
    urun.guncel_fiyat = 104826
    db.commit()
    db.close()
    motor.dispose()

    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.locator("#set-adi").fill("Aşan set")
    sayfa.locator("#set-butce").fill("90000")
    sayfa.get_by_role("button", name="Set kur").click()
    sayfa.wait_for_selector("text=Aşan set", timeout=15000)

    sayfa.get_by_role("button", name="Ürün ekle").click()
    sayfa.wait_for_selector("input[type=checkbox]", timeout=15000)
    sayfa.locator("input[type=checkbox]").first.check()
    sayfa.get_by_role("button", name="Ekle (1)").click()
    sayfa.wait_for_selector("text=1 ürün eklendi", timeout=15000)
    sayfa.get_by_role("button", name="Kapat").click()

    # 104.826 / 90.000 → 14.826 aşıyor, %16
    asan_kart = sayfa.locator("div.rounded-lg", has_text="Aşan set")
    asan_kart.get_by_text("aşıyor (%16)", exact=False).wait_for(timeout=15000)
    fark_metni = asan_kart.get_by_text("aşıyor (%16)", exact=False)
    assert "text-red-600" in fark_metni.get_attribute("class")
    assert "Sığması için" in asan_kart.inner_text()

    # Fiyat bütçenin altına inince aynı kart yeşile dönmeli.
    motor2 = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db2 = Session(motor2)
    urun2 = _kullanicinin_urunu(db2, eposta)
    urun2.guncel_fiyat = 50000
    db2.commit()
    db2.close()
    motor2.dispose()
    sayfa.reload(wait_until="networkidle")
    asan_kart = sayfa.locator("div.rounded-lg", has_text="Aşan set")
    asan_kart.get_by_text("bütçe altında", exact=False).wait_for(timeout=15000)
    altinda_metni = asan_kart.get_by_text("bütçe altında", exact=False)
    assert "text-green-600" in altinda_metni.get_attribute("class")

    # Bütçesiz sette hiçbiri görünmüyor.
    sayfa.locator("#set-adi").fill("Bütçesiz set")
    sayfa.get_by_role("button", name="Set kur").click()
    sayfa.wait_for_selector("text=Bütçesiz set", timeout=15000)
    bosuz_kart = sayfa.locator("div.rounded-lg", has_text="Bütçesiz set")
    govde = bosuz_kart.inner_text()
    assert "aşıyor" not in govde
    assert "bütçe altında" not in govde


def _iki_uyeli_set_gecmisiyle_kur(sayfa, sunucu, set_adi, hedef_butce):
    """BACKLOG F2 testleri için ortak kurulum: bütçeli set, 2 üye, ikisinin
    de en az 2 günlük fiyat geçmişi. `set_id`, iki `Watch.id` ve DB motorunu
    döner — çağıran ek geçmiş/temizlik için kullanabilir."""
    from datetime import timedelta

    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import PriceReading, Source, User, Watch, WatchSet
    from keepmoney.zaman import utc_simdi

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/f2-a", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    _urun_ekle(sayfa, url="https://www.example.com/urun/f2-c", hedef="")
    expect(sayfa.locator("a[href^='/izleme/']")).to_have_count(2, timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    kullanici_id = kullanici.id
    w_a, w_c = (db.query(Watch).filter(Watch.user_id == kullanici.id)
               .order_by(Watch.id).all())
    w_a_id, w_c_id = w_a.id, w_c.id
    simdi = utc_simdi()
    for w, satirlar in [(w_a, [(1000, 1), (900, 0)]), (w_c, [(2000, 1), (2200, 0)])]:
        kaynak = db.query(Source).filter(Source.product_id == w.product_id).one()
        for fiyat, gun_once in satirlar:
            db.add(PriceReading(product_id=w.product_id, source_id=kaynak.id,
                                fiyat=fiyat, ts=simdi - timedelta(days=gun_once)))
    db.commit()
    db.close()
    motor.dispose()

    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.locator("#set-adi").fill(set_adi)
    sayfa.locator("#set-butce").fill(str(hedef_butce))
    sayfa.get_by_role("button", name="Set kur").click()
    sayfa.wait_for_selector(f"text={set_adi}", timeout=15000)

    sayfa.get_by_role("button", name="Ürün ekle").click()
    sayfa.wait_for_selector("input[type=checkbox]", timeout=15000)
    kutular = sayfa.locator("input[type=checkbox]")
    kutular.nth(0).check()
    kutular.nth(1).check()
    sayfa.get_by_role("button", name="Ekle (2)").click()
    sayfa.wait_for_selector("text=2 ürün eklendi", timeout=15000)
    sayfa.get_by_role("button", name="Kapat").click()

    motor2 = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db2 = Session(motor2)
    set_id = (db2.query(WatchSet)
             .filter(WatchSet.user_id == kullanici_id, WatchSet.ad == set_adi)
             .one().id)
    db2.close()
    motor2.dispose()
    return set_id, w_a_id, w_c_id


def test_set_gecmis_grafigi_acilir_ve_butce_cizgisi_gorunur(sayfa, sunucu):
    """BACKLOG F2: 'Bütçe hedefi yatay çizgi olarak grafikte' — grafik
    açılıyor ve bütçe referans çizgisinin etiketi görünüyor."""
    _iki_uyeli_set_gecmisiyle_kur(sayfa, sunucu, "Geçmiş seti", 2800)

    sayfa.get_by_role("button", name="Geçmiş").click()
    sayfa.wait_for_selector("svg", timeout=15000)
    # Sayfada "bütçe" geçen başka metinler de var (girdi etiketi, "Bütçeyi
    # düzenle" düğmesi) — referans çizgisinin etiketi SVG İÇİNDE arandı.
    expect(sayfa.locator("svg").get_by_text("bütçe")).to_be_visible()


def test_set_gecmis_uye_cikarilinca_ucu_yeniden_hesaplanmis_veri_dondurur(sayfa, sunucu):
    """Kabul ölçütü: üye eklenip çıkarılınca geçmiş yeniden hesaplanıyor.
    Grafik canlı hesaplanan sunucu verisini çiziyor; burada asıl ölçülmesi
    gereken web ucunun ÇIKARMADAN SONRA GÜNCEL veriyi döndürmesi — grafiğin
    SVG'sini piksel piksel incelemek recharts'ın kendi davranışını test
    eder, bizim kodumuzu değil."""
    set_id, _izleme_a, _izleme_c = _iki_uyeli_set_gecmisiyle_kur(
        sayfa, sunucu, "Yeniden hesaplanan set", 5000)

    sayfa.get_by_role("button", name="Geçmiş").click()
    sayfa.wait_for_selector("svg", timeout=15000)

    once = sayfa.evaluate(
        f"() => fetch('/api/setler/{set_id}/gecmis').then(r => r.json())")
    # 1 gün önce: 1000 (a) + 2000 (c) = 3000 · bugün: 900 (a) + 2200 (c) = 3100
    once_toplam = sorted(n["toplam"] for n in once)
    assert once_toplam == [3000.0, 3100.0]

    # "Ürün ekle" seti zaten AÇIK bırakıyor (bkz. Setler.tsx — eklenen şeyi
    # görmeden kapanması az önce ne olduğunu gizlerdi), yani İçindekiler
    # listesi burada halihazırda görünür — tekrar tıklamak KAPATIRDI.
    # Hangi üyenin kaldırılacağı DOM sırasına bağlı (ilişki sırası garanti
    # değil) — bu yüzden ikisi de kabul edilebilir sonuç.
    sayfa.wait_for_selector("button[aria-label*='setten çıkar']", timeout=15000)
    sayfa.locator("button[aria-label*='setten çıkar']").first.click()
    sayfa.wait_for_timeout(600)                 # invalidate + refetch

    sonra = sayfa.evaluate(
        f"() => fetch('/api/setler/{set_id}/gecmis').then(r => r.json())")
    assert sonra != once
    # Tek üye kaldı — geçmiş artık YALNIZCA o üyenin fiyatlarını yansıtmalı.
    kalan_toplamlar = sorted(n["toplam"] for n in sonra if n["toplam"] is not None)
    assert kalan_toplamlar in ([900.0, 1000.0], [2000.0, 2200.0])


def test_sablonlu_sette_eksik_parcalar_listelenir(sayfa, sunucu):
    """BACKLOG F4: şablon kurarken seçilir, kontrol listesi hangi parçanın
    eksik olduğunu gösterir. `kategori` mağazadan otomatik çıkarılan serbest
    metin olduğu için doğrudan DB'ye yazılıyor — kullanıcı arayüzden bunu
    seçmiyor."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import Product, User, Watch

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/f4-cpu", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.locator("#set-adi").fill("Şablonlu set")
    sayfa.locator("#set-sablon").select_option("pc_toplama")
    sayfa.get_by_role("button", name="Set kur").click()
    sayfa.wait_for_selector("text=Şablonlu set", timeout=15000)

    kart = sayfa.locator("div.rounded-lg", has_text="Şablonlu set")
    kart.get_by_text("Kontrol listesi").wait_for(timeout=15000)
    govde = kart.inner_text()
    for parca in ("İşlemci", "Ekran kartı", "Bellek", "SSD", "Güç kaynağı",
                  "Kasa", "Monitör"):
        assert parca in govde
    assert govde.count("henüz eklenmedi") == 7

    # Ürünü sete ekle, sonra kategorisini "İşlemciler" yap — CPU satırı
    # kontrol listesinden düşmeli, diğer 6 parça hâlâ eksik kalmalı.
    sayfa.get_by_role("button", name="Ürün ekle").click()
    sayfa.wait_for_selector("input[type=checkbox]", timeout=15000)
    sayfa.locator("input[type=checkbox]").first.check()
    sayfa.get_by_role("button", name="Ekle (1)").click()
    sayfa.wait_for_selector("text=1 ürün eklendi", timeout=15000)
    sayfa.get_by_role("button", name="Kapat").click()

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    w = db.query(Watch).filter(Watch.user_id == kullanici.id).one()
    db.query(Product).filter(Product.id == w.product_id).update(
        {"kategori": "İşlemciler"})
    db.commit()
    db.close()
    motor.dispose()

    sayfa.reload(wait_until="networkidle")
    kart = sayfa.locator("div.rounded-lg", has_text="Şablonlu set")
    kart.get_by_text("Kontrol listesi").wait_for(timeout=15000)
    govde = kart.inner_text()
    assert "İşlemci (CPU) — henüz eklenmedi" not in govde
    assert govde.count("henüz eklenmedi") == 6


def test_sablonsuz_set_kontrol_listesi_gostermez(sayfa, sunucu):
    """BACKLOG F4 kabul ölçütü: şablonsuz set eskisi gibi çalışıyor —
    kontrol listesi hiç görünmüyor."""
    _kayit_ol(sayfa, sunucu)
    sayfa.goto(f"{sunucu}/setler", wait_until="networkidle")
    sayfa.locator("#set-adi").fill("Şablonsuz set")
    sayfa.get_by_role("button", name="Set kur").click()
    sayfa.wait_for_selector("text=Şablonsuz set", timeout=15000)

    kart = sayfa.locator("div.rounded-lg", has_text="Şablonsuz set")
    assert "Kontrol listesi" not in kart.inner_text()


# ── Bildirimler (BACKLOG G1) ───────────────────────────────────────

def test_bildirimler_gune_gore_gruplanir(sayfa, sunucu):
    """BACKLOG G1: düz liste uyarı biriktikçe okunmaz hâle geliyordu —
    "Bugün · Dün · Bu hafta · Daha eski" başlıkları altında bölümlenir,
    sıralama korunur (aynı gerekçeyle backend zaten `created_at DESC, id
    DESC` kullanıyor, bkz. uyari.py)."""
    from datetime import timedelta

    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import Alert, User
    from keepmoney.zaman import utc_simdi

    eposta = _kayit_ol(sayfa, sunucu)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    simdi = utc_simdi()
    kayitlar = [
        ("Bugünkü uyarı", 0),
        ("Dünkü uyarı", 1),
        ("Bu haftaki uyarı", 3),
        ("Eski uyarı", 20),
    ]
    for baslik, gun_once in kayitlar:
        db.add(Alert(user_id=kullanici.id, tur="HEDEF", baslik=baslik,
                     mesaj="m", created_at=simdi - timedelta(days=gun_once)))
    db.commit()
    db.close()
    motor.dispose()

    sayfa.goto(f"{sunucu}/uyarilar", wait_until="networkidle")
    sayfa.wait_for_selector("text=Eski uyarı", timeout=15000)

    # `.inner_text()` CSS'i hesaba katar — başlıklar `uppercase` stilinde,
    # yani DOM'daki "Bugün" değil, GÖRÜNEN "BUGÜN" döner. Bu doğru: kullanıcı
    # neyi görüyorsa onu doğrulamak istiyoruz.
    basliklar = sayfa.locator("h2").all_inner_texts()
    gorunen_gruplar = [b for b in basliklar
                       if b in ("BUGÜN", "DÜN", "BU HAFTA", "DAHA ESKİ")]
    assert gorunen_gruplar == ["BUGÜN", "DÜN", "BU HAFTA", "DAHA ESKİ"]

    icerik = sayfa.content()
    assert icerik.index("Bugünkü uyarı") < icerik.index("Dünkü uyarı") \
        < icerik.index("Bu haftaki uyarı") < icerik.index("Eski uyarı")


def test_bildirimler_ture_gore_suzulur(sayfa, sunucu):
    """BACKLOG G2: süzgeç: hedef · düşüş · set · bozuk kaynak · okunmamış.
    "Düşüş" YUZDE ve DIP'i BİRLİKTE gösterir."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import Alert, User

    eposta = _kayit_ol(sayfa, sunucu)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    for tur, baslik in [("HEDEF", "Hedef bildirimi"), ("YUZDE", "Yüzde bildirimi"),
                        ("DIP", "Dip bildirimi"), ("SET_HEDEF", "Set bildirimi")]:
        db.add(Alert(user_id=kullanici.id, tur=tur, baslik=baslik, mesaj="m"))
    db.commit()
    db.close()
    motor.dispose()

    sayfa.goto(f"{sunucu}/uyarilar", wait_until="networkidle")
    sayfa.wait_for_selector("text=Set bildirimi", timeout=15000)

    sayfa.get_by_role("button", name="Hedef", exact=True).click()
    sayfa.wait_for_selector("text=Hedef bildirimi", timeout=15000)
    govde = sayfa.locator("main").inner_text()
    assert "Yüzde bildirimi" not in govde
    assert "Dip bildirimi" not in govde
    assert "Set bildirimi" not in govde

    sayfa.get_by_role("button", name="Düşüş", exact=True).click()
    sayfa.wait_for_selector("text=Yüzde bildirimi", timeout=15000)
    sayfa.wait_for_selector("text=Dip bildirimi", timeout=15000)
    govde = sayfa.locator("main").inner_text()
    assert "Hedef bildirimi" not in govde
    assert "Set bildirimi" not in govde

    sayfa.get_by_role("button", name="Tümü", exact=True).click()
    sayfa.wait_for_selector("text=Set bildirimi", timeout=15000)
    govde = sayfa.locator("main").inner_text()
    assert all(b in govde for b in
              ("Hedef bildirimi", "Yüzde bildirimi", "Dip bildirimi", "Set bildirimi"))


def test_urunun_bildirimlerine_daraltilir(sayfa, sunucu):
    """BACKLOG G2: "Ürüne göre daraltma" — İzleme Detayı'ndaki bağlantı
    yalnızca o ürünün bildirimlerine süzülmüş Bildirimler sayfasına götürür."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import Alert, User, Watch

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/g2-a", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    _urun_ekle(sayfa, url="https://www.example.com/urun/g2-b", hedef="")
    expect(sayfa.locator("a[href^='/izleme/']")).to_have_count(2, timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    w_a, w_b = (db.query(Watch).filter(Watch.user_id == kullanici.id)
               .order_by(Watch.id).all())
    w_a_id, w_b_id = w_a.id, w_b.id
    db.add(Alert(user_id=kullanici.id, watch_id=w_a_id, tur="HEDEF",
                 baslik="A ürününün bildirimi", mesaj="m"))
    db.add(Alert(user_id=kullanici.id, watch_id=w_b_id, tur="HEDEF",
                 baslik="B ürününün bildirimi", mesaj="m"))
    db.commit()
    db.close()
    motor.dispose()

    sayfa.goto(f"{sunucu}/izleme/{w_a_id}", wait_until="networkidle")
    sayfa.get_by_role("link", name="Bu ürünün bildirimlerini gör").click()
    sayfa.wait_for_selector("text=A ürününün bildirimi", timeout=15000)

    assert f"watch_id={w_a_id}" in sayfa.url
    govde = sayfa.locator("main").inner_text()
    assert "B ürününün bildirimi" not in govde
    assert "yalnızca bu ürünün bildirimleri" in govde

    # Kaldırınca daraltma açılır, ikisi de görünür.
    sayfa.get_by_role("button", name="yalnızca bu ürünün bildirimleri ✕").click()
    sayfa.wait_for_selector("text=B ürününün bildirimi", timeout=15000)


def test_uyaridan_magazaya_git_en_ucuz_kaynaga_gider(sayfa, sunucu):
    """BACKLOG G3: "Mağazaya git" o an EN UCUZ kaynağa gitmeli, ilk eklenen
    kaynağa değil — burada ikinci eklenen (ve ucuz olan) kaynak doğru."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import Alert, Source, User, Watch

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/g3-magaza", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    w = db.query(Watch).filter(Watch.user_id == kullanici.id).one()
    w_id, product_id = w.id, w.product_id
    ilk_kaynak = db.query(Source).filter(Source.product_id == product_id).one()
    ilk_kaynak.durum = "OK"
    ilk_kaynak.son_fiyat = 2000
    db.add(Source(product_id=product_id, url="https://www.example.com/urun/g3-ucuz",
                  host="example.com", durum="OK", son_fiyat=1500))
    db.add(Alert(user_id=kullanici.id, watch_id=w_id, tur="HEDEF",
                 baslik="Fiyat düştü", mesaj="m"))
    db.commit()
    db.close()
    motor.dispose()

    sayfa.goto(f"{sunucu}/uyarilar", wait_until="networkidle")
    sayfa.wait_for_selector("text=Mağazaya git", timeout=15000)
    href = sayfa.get_by_role("link", name="Mağazaya git").get_attribute("href")
    assert href == "https://www.example.com/urun/g3-ucuz"


def test_uyaridan_sustur_calisir(sayfa, sunucu):
    """BACKLOG G3: "7 gün sustur" — ürüne gidip elle ayar değiştirmeden,
    tek tıkla izlemenin `sustur_bitis`ini ileri tarihe çeker."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import Alert, User, Watch
    from keepmoney.zaman import utc_simdi

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/g3-sustur", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    w = db.query(Watch).filter(Watch.user_id == kullanici.id).one()
    w_id = w.id
    assert w.sustur_bitis is None
    db.add(Alert(user_id=kullanici.id, watch_id=w_id, tur="HEDEF",
                 baslik="Fiyat düştü", mesaj="m"))
    db.commit()
    db.close()
    motor.dispose()

    sayfa.goto(f"{sunucu}/uyarilar", wait_until="networkidle")
    sayfa.get_by_role("button", name="7 gün sustur").click()
    sayfa.wait_for_selector("text=Susturuldu", timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    w = db.query(Watch).filter(Watch.id == w_id).one()
    assert w.sustur_bitis is not None
    assert w.sustur_bitis > utc_simdi()
    db.close()
    motor.dispose()


def test_uyaridan_takipten_cikar_onay_ister(sayfa, sunucu):
    """BACKLOG G3: yıkıcı olan (takipten çıkar) onay ister — bildirim
    satırındaki kısayol da IzlemeDetay'daki AYNI `Onay` dialogunu kullanır
    (bkz. `test_takipten_cikarma_onay_ister`). Onaylanınca izleme SET NULL
    olur, satır kalır ama eylem düğmeleri kaybolur."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import Alert, User, Watch

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/g3-cik", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    kullanici = db.query(User).filter(User.email == eposta).one()
    w = db.query(Watch).filter(Watch.user_id == kullanici.id).one()
    w_id = w.id
    db.add(Alert(user_id=kullanici.id, watch_id=w_id, tur="HEDEF",
                 baslik="Fiyat düştü", mesaj="m"))
    db.commit()
    db.close()
    motor.dispose()

    sayfa.goto(f"{sunucu}/uyarilar", wait_until="networkidle")
    sayfa.wait_for_selector("text=Fiyat düştü", timeout=15000)

    sayfa.get_by_role("button", name="Takipten çıkar").first.click()
    sayfa.wait_for_selector("dialog[open]", timeout=5000)
    sayfa.get_by_role("button", name="Vazgeç").click()
    sayfa.wait_for_timeout(500)
    assert sayfa.locator("dialog[open]").count() == 0

    sayfa.get_by_role("button", name="Takipten çıkar").first.click()
    sayfa.wait_for_selector("dialog[open]", timeout=5000)
    sayfa.locator("dialog[open]").get_by_role(
        "button", name="Takipten çıkar").click()
    # İzleme silinince `Alert.watch_id` `SET NULL` olur — satır kalır ama
    # eylem düğmeleri (Ürüne git dahil) artık gösterilmemeli.
    expect(sayfa.get_by_role("link", name="Ürüne git")).to_have_count(0, timeout=15000)


# ── Ayarlar ve hesap ─────────────────────────────────────────────

def test_ayarlar_dogrulama_uyarisi_gosterir(sayfa, sunucu):
    eposta = _kayit_ol(sayfa, sunucu)
    sayfa.goto(f"{sunucu}/ayarlar", wait_until="networkidle")
    assert eposta in sayfa.content()
    assert "doğrulanmadı" in sayfa.content()
    assert "Hesabı sil" in sayfa.content()


def test_telegram_yapilandirilmamissa_durust_hata(sayfa, sunucu):
    """Bozuk düğme bırakma: uç 503 dönüyor, kullanıcı sebebini görmeli.

    503 BİLEREK: özellik sunucuda yapılandırılmamış, yani gerçekten
    kullanılamaz durumda — 4xx demek istemciyi suçlamak olurdu.
    """
    sayfa.beklenen_5xx.add("/auth/telegram/baglanti")
    _kayit_ol(sayfa, sunucu)
    sayfa.goto(f"{sunucu}/ayarlar", wait_until="networkidle")
    sayfa.get_by_role("button", name="Telegram'a bağla").click()
    sayfa.wait_for_selector("text=yapılandırılmamış", timeout=15000)


def test_hesap_silme_parola_ister(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    sayfa.goto(f"{sunucu}/ayarlar", wait_until="networkidle")
    sayfa.get_by_role("button", name="Hesabımı silmek istiyorum").click()
    sayfa.locator("input[type=password]").fill("yanlisparola")
    sayfa.get_by_role("button", name="Kalıcı olarak sil").click()
    sayfa.wait_for_selector("text=Parola hatalı", timeout=15000)


def test_hesap_silinince_girise_dusulur(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    sayfa.goto(f"{sunucu}/ayarlar", wait_until="networkidle")
    sayfa.get_by_role("button", name="Hesabımı silmek istiyorum").click()
    sayfa.locator("input[type=password]").fill("parola12345")
    sayfa.get_by_role("button", name="Kalıcı olarak sil").click()
    sayfa.wait_for_selector("input[type=email]", timeout=15000)


# ── Gezinme, erişilebilirlik, duyarlılık ─────────────────────────

def test_tum_ana_sayfalar_geziliyor(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    for etiket, isaret in (("Fırsatlar", "Fırsatlar"),
                           ("Setler", "Setler"),
                           ("Bildirimler", "Bildirim"),
                           ("Ayarlar", "Ayarlar"),
                           ("Panel", "Takip listem")):
        sayfa.get_by_role("link", name=etiket).click()
        sayfa.wait_for_selector(f"text={isaret}", timeout=15000)


def test_besinci_sekme_mobilde_tasmiyor(sayfa, sunucu):
    """BACKLOG D2: "beşinci sekme 390px'te sığıyor mu kontrol et" —
    Fırsatlar eklenince gezinme çubuğu Panel/Fırsatlar/Setler/Bildirimler/
    Ayarlar diye BEŞ sekmeye çıktı.

    GENİŞLİK BİLEREK 390 DEĞİL 375: sorun ÖLÇÜLDÜ — bozuk hâlde header
    satırının içerik genişliği 389px'ti, yani BACKLOG'un yazdığı 390px'te
    TESADÜFEN sığıyordu (389 < 390) ve o genişlikte test kusuru YAKALAMAZDI.
    375 (yaygın bir gerçek cihaz genişliği, iPhone SE ailesi) kusuru
    ölçülebilir kıldı; 375'te geçen bir düzen 390'da da geçer (daha dar
    olan daha zor koşuldur), yani BACKLOG'un ölçütü GEVŞETİLMİYOR, SIKILAŞTIRILIYOR.

    GERÇEK TARAYICIDA (375px) ÖLÇÜLDÜ: `nav`'ın KENDİ `scrollWidth`'i
    (`nav.scrollWidth - nav.clientWidth`) bu tuzağı YAKALAMAZ — nav'ın
    içeriği taşmıyordu (kendi içinde 0), asıl sorun nav'ı SIĞDIRAN HEADER
    SATIRININ nav'ı küçültememesiydi (`flex` item'ların varsayılan
    `min-width: auto`'su — A8'in CSS Grid'teki aynı ailedeki tuzağı):
    header satırı 389px'e taşıyor, viewport 375px, ve nav'ın sağındaki
    çıkış düğmesi viewport DIŞINA itiliyordu. Bu yüzden BELGE genişliği
    ölçülmeli (`test_mobil_gorunumde_yatay_kaydirma_yok` ile aynı ilke),
    nav'ın kendi iç taşması DEĞİL — `Duzen.tsx`'teki `min-w-0` düzeltmesi
    bu ölçümle doğrulandı.
    """
    _kayit_ol(sayfa, sunucu)
    sayfa.set_viewport_size({"width": 375, "height": 812})
    sayfa.wait_for_timeout(300)
    tasma = sayfa.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert tasma <= 1, f"sayfa {tasma}px taşıyor"

    nav = sayfa.locator("header nav")
    baglantilar = nav.locator("a")
    assert baglantilar.count() == 5
    # Beş bağlantının BEŞİ de gerçekten görünür (0 genişliğe sıkışmamış) VE
    # viewport İÇİNDE (nav taşmasa da sağdaki çıkış düğmesi dışarı itilirse
    # nav'ın kendisi hâlâ "tam" görünür ama komşusu kaybolurdu).
    for i in range(5):
        kutu = baglantilar.nth(i).bounding_box()
        assert kutu is not None and kutu["width"] > 0 and kutu["x"] + kutu["width"] <= 375

    cikis = sayfa.get_by_role("button", name="Çıkış yap")
    cikis_kutu = cikis.bounding_box()
    assert cikis_kutu is not None and cikis_kutu["x"] + cikis_kutu["width"] <= 375

    # "Yapılacak": Fırsatlar Panel'den SONRA İKİNCİ sırada.
    yollar = baglantilar.evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert yollar[:2] == ["/", "/firsatlar"], yollar


def test_firsatlar_satirina_tiklayinca_detaya_gidiyor(sayfa, sunucu):
    """Kabul ölçütü: satıra tıklayınca ürün detayına gidiyor."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    # Worker'ın normalde yazacağı sütunları elle kuruyoruz (bkz. A8 deseni)
    # — bu paket içinde worker çalışmadığı için `sinyal` hiç dolmuyor,
    # dolayısıyla ürün D1'in `/api/firsatlar` süzgecinden hiç geçmezdi.
    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    urun = _kullanicinin_urunu(db, eposta)
    urun.sinyal = "dip"
    urun.yuzdelik = 90
    urun.gecmis_gun = 10
    urun.guncel_fiyat = 500
    db.commit()
    db.close()
    motor.dispose()

    sayfa.get_by_role("link", name="Fırsatlar").click()
    sayfa.wait_for_selector("text=ürün şu an iyi fiyatta", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("text=Fiyat geçmişi", timeout=15000)


# ── Fırsatlar boş durumları (BACKLOG D3) ──────────────────────────
# Kabul ölçütü: üç durum üç ayrı metin veriyor. Üçü de aynı boş kutuya
# çıkıyor olsaydı kullanıcı "hiç ürün eklemedim" ile "ürünlerim var ama
# hiçbiri iyi fiyatta değil" arasındaki farkı ayırt edemezdi.

def test_firsatlar_hic_urun_yokken_panele_yonlendirir(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    sayfa.get_by_role("link", name="Fırsatlar").click()
    sayfa.wait_for_selector("text=Önce", timeout=15000)
    icerik = sayfa.content()
    assert "panelden" in icerik
    assert "geçmiş biriktiriliyor" not in icerik
    assert "dip bölgesinde ürün yok" not in icerik


def test_firsatlar_gecmis_yetersizken_biriktiriliyor_mesaji(sayfa, sunucu):
    """Ürün VAR ama worker hiç taramadı (bu paket içinde worker çalışmıyor)
    — sinyal hep null, "hiç ürün yok" mesajıyla KARIŞTIRILMAMALI.

    URL BİLEREK KENDİNE ÖZGÜ: varsayılan `_urun_ekle` URL'si ("ekran-
    karti") bu dosyadaki BAŞKA testlerin (aynı paylaşılan `sunucu` DB'sinde
    — bkz. C4'teki aynı bulgu) ZATEN `sinyal` yazdığı ürünle AYNI KANONİK
    ÜRÜNE karşılık geliyordu (ürün kimliği kullanıcılar arası PAYLAŞILIR),
    "hiç taranmamış" varsayımını yanlış kılıyordu."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/d3-gecmis-yetersiz", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.get_by_role("link", name="Fırsatlar").click()
    sayfa.wait_for_selector("text=geçmiş biriktiriliyor", timeout=15000)
    icerik = sayfa.content()
    assert "1 ürün için geçmiş biriktiriliyor" in icerik
    assert "panelden" not in icerik
    assert "dip bölgesinde ürün yok" not in icerik


def test_firsatlar_iyi_fiyat_yokken_normal_aralik_mesaji(sayfa, sunucu):
    """Ürünün YETERLİ geçmişi var (sinyal='pahali' — worker karar vermiş)
    ama hiçbiri dip/ucuz değil. "Biriktiriliyor" mesajıyla KARIŞTIRILMAMALI
    — bu ürünler için biriktirme zaten BİTTİ, sonuç iyi fiyat değil."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/d3-iyi-fiyat-yok", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    urun = _kullanicinin_urunu(db, eposta)
    urun.sinyal = "pahali"
    urun.yuzdelik = 5
    urun.gecmis_gun = 30
    db.commit()
    db.close()
    motor.dispose()

    # TanStack Query önbelleği `useIzlemeler()`i Panel ziyaretinden (yukarı-
    # daki `_urun_ekle`) eski (sinyalsiz) hâliyle tutuyor — istemci tarafı
    # gezinme (nav linkine tıklama) bunu ZORLA tazelemez, tıpkı A8'in
    # `test_sinyalli_kartta_...`daki aynı bulgusu gibi: taze veri için
    # sayfa yenileniyor (gerçek kullanıcının da yapacağı şey).
    sayfa.reload(wait_until="networkidle")
    sayfa.get_by_role("link", name="Fırsatlar").click()
    sayfa.wait_for_selector("text=dip bölgesinde ürün yok", timeout=15000)
    icerik = sayfa.content()
    assert "Hepsi normal aralıkta" in icerik
    assert "geçmiş biriktiriliyor" not in icerik
    assert "panelden" not in icerik


def test_ikon_dugmelerinin_erisilebilir_adi_var(sayfa, sunucu):
    """Çıkış düğmesi yalnızca SVG içeriyordu ve `title` kullanıcının
    e-postasıydı: ekran okuyucu düğmenin ne yaptığını hiç duyurmuyordu."""
    _kayit_ol(sayfa, sunucu)
    adsiz = sayfa.evaluate("""() =>
        [...document.querySelectorAll('button')]
          .filter(b => !(b.innerText || '').trim()
                    && !b.getAttribute('aria-label')
                    && !b.querySelector('.sr-only'))
          .length""")
    assert adsiz == 0, f"{adsiz} adet erişilebilir adı olmayan düğme var"


def test_mobil_gorunumde_yatay_kaydirma_yok(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa)
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    sayfa.set_viewport_size({"width": 390, "height": 844})
    sayfa.wait_for_timeout(400)
    assert not sayfa.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth")


def test_klavye_ile_gezinilebiliyor(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    sayfa.keyboard.press("Tab")
    assert sayfa.evaluate("document.activeElement.tagName") not in ("BODY", "HTML")


def test_bilinmeyen_yol_panele_dusuyor(sayfa, sunucu):
    """SPA geri düşüşü: doğrudan yazılan adres 404 vermemeli."""
    _kayit_ol(sayfa, sunucu)
    sayfa.goto(f"{sunucu}/boyle-bir-sayfa-yok", wait_until="networkidle")
    sayfa.wait_for_selector("text=Takip listem", timeout=15000)


def test_api_404u_json_doner(sayfa, sunucu):
    """SPA geri düşüşü API'yi GÖLGELEMEMELİ: olmayan uç HTML değil JSON
    404 dönmeli, yoksa istemci "beklenmeyen yanıt" hatası verir."""
    yanit = sayfa.request.get(f"{sunucu}/api/boyle-bir-uc-yok")
    assert yanit.status == 404
    assert "application/json" in yanit.headers.get("content-type", "")


# ── Grafik zaman aralığı (BACKLOG B1) ─────────────────────────────

def _uzun_gecmisli_urune_git(s: Page, sunucu, gun_sayisi: int) -> None:
    """`gun_sayisi` FARKLI güne yayılan okuma ekler, sonra detay sayfasına
    gider. Worker'ın normalde günlerce çalışarak biriktireceği geçmişi
    testte elle kurma deseni — bkz. A8'in `test_sinyalli_kartta_...`."""
    from datetime import timedelta

    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import PriceReading, Source
    from keepmoney.zaman import utc_simdi

    eposta = _kayit_ol(s, sunucu)
    _urun_ekle(s, hedef="")
    s.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    urun = _kullanicinin_urunu(db, eposta)
    kaynak = db.query(Source).filter(Source.product_id == urun.id).one()
    simdi = utc_simdi()
    for gun in range(gun_sayisi, 0, -1):
        db.add(PriceReading(product_id=urun.id, source_id=kaynak.id,
                            fiyat=1000 + gun, ts=simdi - timedelta(days=gun)))
    db.commit()
    db.close()
    motor.dispose()

    s.locator("a[href^='/izleme/']").first.click()
    s.wait_for_selector("text=Fiyat geçmişi", timeout=15000)


def test_grafik_araligi_varsayilan_90g_ve_secim_degistirilebilir(sayfa, sunucu):
    """Kabul ölçütü: varsayılan 90g. Aralık değişince y ekseni yeniden
    ölçekleniyor — bunu piksel piksel doğrulamak yerine grafiğin GERÇEKTEN
    yeniden çizildiğini (SVG path'inin değiştiğini) ölçüyoruz; recharts y
    eksenini `domain` prop'undan hesaplıyor ve `veri` değişince path de
    değişir, bu da dolaylı ama gerçek bir kanıt."""
    _uzun_gecmisli_urune_git(sayfa, sunucu, gun_sayisi=120)

    grup = sayfa.get_by_role("group", name="Grafik zaman aralığı")
    grup.wait_for(timeout=15000)
    varsayilan = grup.get_by_role("button", name="90g", exact=True)
    assert varsayilan.get_attribute("aria-pressed") == "true"

    onceki_path = sayfa.locator(".recharts-line-curve").get_attribute("d")

    yedi_gun = grup.get_by_role("button", name="7g", exact=True)
    yedi_gun.click()
    sayfa.wait_for_timeout(300)

    assert yedi_gun.get_attribute("aria-pressed") == "true"
    assert varsayilan.get_attribute("aria-pressed") == "false"
    sonraki_path = sayfa.locator(".recharts-line-curve").get_attribute("d")
    assert sonraki_path != onceki_path              # grafik gerçekten değişti


def test_grafik_araligi_secimi_yenilemede_korunur(sayfa, sunucu):
    """Kabul ölçütü: sayfa yenilendiğinde son seçim korunuyor (localStorage)."""
    _uzun_gecmisli_urune_git(sayfa, sunucu, gun_sayisi=120)

    grup = sayfa.get_by_role("group", name="Grafik zaman aralığı")
    grup.get_by_role("button", name="30g", exact=True).click()
    sayfa.wait_for_timeout(300)

    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_selector("text=Fiyat geçmişi", timeout=15000)
    grup2 = sayfa.get_by_role("group", name="Grafik zaman aralığı")
    assert grup2.get_by_role("button", name="30g", exact=True).get_attribute(
        "aria-pressed") == "true"


def test_grafik_araligi_yetersiz_veride_pasif(sayfa, sunucu):
    """Kabul ölçütü: veri seçilen aralıktan kısaysa düğme pasif — burada
    yalnızca 5 günlük veriyle "1y" test ediliyor (365 günden KISA olduğu
    kesin). "Tümü" ASLA pasif olmamalı; o da burada doğrulanıyor."""
    _uzun_gecmisli_urune_git(sayfa, sunucu, gun_sayisi=5)

    grup = sayfa.get_by_role("group", name="Grafik zaman aralığı")
    grup.wait_for(timeout=15000)
    assert grup.get_by_role("button", name="1y", exact=True).is_disabled()
    assert not grup.get_by_role("button", name="Tümü", exact=True).is_disabled()


# ── Panel sıralaması (BACKLOG C1) ──────────────────────────────────

def _uc_urun_farkli_fiyatla_kur(s: Page, sunucu):
    """Üç ürün ekler, DB'ye doğrudan yazarak FARKLI fiyat verir — worker
    bu paket içinde çalışmadığı için `guncel_fiyat` normalde hep None
    kalırdı (bkz. `_uzun_gecmisli_urune_git`, aynı desen)."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    eposta = _kayit_ol(s, sunucu)
    kartlar = s.locator("a[href^='/izleme/']")
    for n in range(3):
        _urun_ekle(s, url=f"https://www.example.com/urun/parca-{n}", hedef="")
        # ÖNCEKİ istek tamamlanmadan sonraki `_urun_ekle` form'u dolduruyordu
        # — "Takibe al" `ekle.isPending` iken disabled, ard arda tıklama
        # bazen kayboluyordu (ÖLÇÜLDÜ: 3 çağrıdan yalnızca 2 kart oluştu).
        # Her ekleme sonrası SAYININ ARTTIĞINI bekleyerek sıraya sokuyoruz.
        expect(kartlar).to_have_count(n + 1, timeout=15000)

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    from keepmoney.models import User, Watch

    kullanici = db.query(User).filter(User.email == eposta).one()
    izlemeler = db.query(Watch).filter(Watch.user_id == kullanici.id).all()
    # Kaydedilme sırası: parca-0, parca-1, parca-2. Fiyatları KARIŞIK
    # veriyoruz ki "artan" sıralama DB/ekleme sırasıyla TESADÜFEN
    # örtüşmesin — testin gerçekten sıraladığını, zaten sıralı olan bir
    # diziyi olduğu gibi geçmediğini kanıtlamak için.
    fiyatlar = {"parca-0": 300.0, "parca-1": 100.0, "parca-2": 200.0}
    for w in izlemeler:
        for anahtar, fiyat in fiyatlar.items():
            if anahtar in w.product.sources[0].url:
                w.product.guncel_fiyat = fiyat
    db.commit()
    db.close()
    motor.dispose()

    s.reload(wait_until="networkidle")
    s.wait_for_selector("a[href^='/izleme/']", timeout=15000)


def _panel_kart_fiyatlari(s: Page) -> list[str]:
    return s.locator(
        "a[href^='/izleme/'] .font-mono.text-lg.font-semibold"
    ).all_inner_texts()


def test_panel_siralama_varsayilan_firsat(sayfa, sunucu):
    """Kabul ölçütü: varsayılan 'En iyi fırsat'."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    secili = sayfa.locator("#panel-siralama")
    secili.wait_for(timeout=15000)
    assert secili.input_value() == "firsat"


def test_panel_siralama_fiyata_gore_degistirilebilir(sayfa, sunucu):
    """Kabul ölçütü: her seçenek doğru sıralıyor."""
    _uc_urun_farkli_fiyatla_kur(sayfa, sunucu)

    sayfa.locator("#panel-siralama").select_option("fiyat_artan")
    sayfa.wait_for_timeout(300)
    fiyatlar = _panel_kart_fiyatlari(sayfa)
    assert fiyatlar == ["₺100,00", "₺200,00", "₺300,00"]

    sayfa.locator("#panel-siralama").select_option("fiyat_azalan")
    sayfa.wait_for_timeout(300)
    fiyatlar = _panel_kart_fiyatlari(sayfa)
    assert fiyatlar == ["₺300,00", "₺200,00", "₺100,00"]


def test_panel_siralama_secimi_yenilemede_korunur(sayfa, sunucu):
    """Kabul ölçütü: seçim localStorage'da kalıcı."""
    _uc_urun_farkli_fiyatla_kur(sayfa, sunucu)

    sayfa.locator("#panel-siralama").select_option("fiyat_azalan")
    sayfa.wait_for_timeout(300)

    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    assert sayfa.locator("#panel-siralama").input_value() == "fiyat_azalan"
    fiyatlar = _panel_kart_fiyatlari(sayfa)
    assert fiyatlar == ["₺300,00", "₺200,00", "₺100,00"]


# ── Panel görünüm: kart / tablo (BACKLOG C3) ──────────────────────

def test_panel_gorunum_varsayilan_kart_masaustunde_tabloya_gecilebilir(sayfa, sunucu):
    """Kabul ölçütü: varsayılan kart, masaüstünde tablo düğmesiyle
    geçilebiliyor."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    assert sayfa.locator("table").count() == 0
    sayfa.get_by_role("button", name="Tablo görünümü").click()
    expect(sayfa.locator("table")).to_be_visible(timeout=5000)
    govde = sayfa.locator("thead").inner_text()
    for baslik in ("Sinyal", "Ürün", "Eğilim", "Fiyat", "Medyana fark", "Hedef", "Son kontrol"):
        assert baslik in govde


def test_panel_tablo_kolon_basligina_tiklayinca_siralanir(sayfa, sunucu):
    """Kabul ölçütü: sütun başlığına tıklayınca o sütuna göre sıralanır —
    C1'in AYNI durumu (bkz. IzlemeTablosu.tsx). Fiyat sütunu tekrar
    tıklanınca yön DEĞİŞİR."""
    _uc_urun_farkli_fiyatla_kur(sayfa, sunucu)
    sayfa.get_by_role("button", name="Tablo görünümü").click()
    expect(sayfa.locator("table")).to_be_visible(timeout=5000)

    def fiyat_sutunu():
        return sayfa.locator("tbody tr td:nth-child(4)").all_inner_texts()

    sayfa.get_by_role("button", name="Fiyat", exact=True).click()
    sayfa.wait_for_timeout(300)
    assert fiyat_sutunu() == ["₺100,00", "₺200,00", "₺300,00"]
    assert sayfa.locator("#panel-siralama").input_value() == "fiyat_artan"

    sayfa.get_by_role("button", name="Fiyat", exact=True).click()
    sayfa.wait_for_timeout(300)
    assert fiyat_sutunu() == ["₺300,00", "₺200,00", "₺100,00"]
    assert sayfa.locator("#panel-siralama").input_value() == "fiyat_azalan"


def test_panel_gorunum_tercihi_kalici(sayfa, sunucu):
    """Kabul ölçütü: tercih localStorage'da kalıcı — C1'in sıralama
    kalıcılığıyla AYNI ilke."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.get_by_role("button", name="Tablo görünümü").click()
    expect(sayfa.locator("table")).to_be_visible(timeout=5000)

    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    expect(sayfa.locator("table")).to_be_visible(timeout=5000)


def test_768_altinda_tablo_secenegi_hic_gorunmuyor_ve_kart_zorunlu(sayfa, sunucu):
    """Kabul ölçütü: telefonda tablo seçeneği hiç görünmüyor — "768px
    altında her zaman kart", SAKLI tercih 'tablo' olsa bile."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.get_by_role("button", name="Tablo görünümü").click()
    expect(sayfa.locator("table")).to_be_visible(timeout=5000)

    # Tercih 'tablo' olarak SAKLI kalırken dar ekrana geçiliyor (taze
    # yükleme — canlı pencere daraltması AYRI bir endişe, bkz.
    # yardimcilar/genisEkran.ts'in kendi yorumu).
    sayfa.set_viewport_size({"width": 375, "height": 812})
    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    assert sayfa.locator("table").count() == 0
    assert sayfa.get_by_role("button", name="Tablo görünümü").count() == 0
    assert sayfa.get_by_role("button", name="Kart görünümü").count() == 0
    assert not sayfa.sunucu_hatalari


# ── Panel süzme (BACKLOG C2) ──────────────────────────────────────

def test_panel_suzme_duraklatilmislar_tek_urun_birakir(sayfa, sunucu):
    """BACKLOG C2'nin kendi test tarifi: iki ürün ekle, birini duraklat,
    'duraklatılmışlar' süzgecinde tek ürün kalsın."""
    _kayit_ol(sayfa, sunucu)
    kartlar = sayfa.locator("a[href^='/izleme/']")
    _urun_ekle(sayfa, url="https://www.example.com/urun/birinci-eklenen", hedef="")
    expect(kartlar).to_have_count(1, timeout=15000)
    _urun_ekle(sayfa, url="https://www.example.com/urun/ikinci-eklenen", hedef="")
    expect(kartlar).to_have_count(2, timeout=15000)

    # Panel listesi `created_at DESC` sıralı (`servisler/izleme.py`) — "ilk
    # eklenen ilk kartta görünür" VARSAYIMI YANLIŞ olurdu (ÖLÇÜLDÜ: mutasyon
    # testinde bu yanlış varsayımla yazılmış bir kimlik kontrolü, filtre
    # TERSİNE çalışırken bile yanlışlıkla geçmişti). Hangi adın
    # duraklatılacağını sabit yazmak yerine, tıklamadan hemen önce okuyoruz.
    duraklatilan_ad = kartlar.first.locator("h3").inner_text()

    kartlar.first.click()
    sayfa.wait_for_selector("text=Bildirimler", timeout=15000)
    sayfa.get_by_role("button", name="Duraklat").click()
    sayfa.wait_for_selector("button:has-text('Devam ettir')", timeout=15000)

    sayfa.get_by_role("link", name="Panele dön").click()
    expect(kartlar).to_have_count(2, timeout=15000)

    # Toggle grubundaki "Duraklatılmışlar" ile aynı ada sahip aktif çipi
    # KARIŞTIRMAMAK için `exact=True`: çip metni "Duraklatılmışlar süzgecini
    # kaldır" (sr-only ek metinle) olduğundan normalde çakışmaz, ama tam eşleşme
    # burada da yanlış düğmeye tıklama riskini baştan kapatıyor.
    sayfa.get_by_role("button", name="Duraklatılmışlar", exact=True).click()
    expect(kartlar).to_have_count(1, timeout=15000)
    # SAYI değil, KİMLİK doğrulanıyor: iki üründen biri duraklatılmış, biri
    # aktifken sayı tek başına "1" — filtre TERSİNE çalışıp AKTİF olanı
    # bıraksa da bu koşul sağlanırdı.
    assert kartlar.locator("h3").inner_text() == duraklatilan_ad


def test_panel_suzme_cip_klavyeyle_kaldirilabiliyor(sayfa, sunucu):
    """Kabul ölçütü: süzgeç çipleri klavyeyle kaldırılabiliyor. Fare tıklaması
    DEĞİL — çipe odaklanıp Enter'a basmak GERÇEK tarayıcıda kaldırmalı."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sinyal = sayfa.locator("#panel-sinyal-suzgec")
    sinyal.select_option("dip")
    cip = sayfa.get_by_role("button", name="Yalnızca dip süzgecini kaldır")
    cip.wait_for(timeout=15000)

    cip.press("Enter")
    expect(sinyal).to_have_value("hepsi")
    expect(sayfa.get_by_role("button", name="Yalnızca dip süzgecini kaldır")).to_have_count(0)


def test_panel_suzme_bos_sonuc_sebebini_soyler(sayfa, sunucu):
    """Kabul ölçütü: boş sonuç mesajı GERÇEK sebebi söylüyor. Ürün VAR ama
    süzgeçlere uyan yok — "Henüz ürün eklemedin" (üstteki, tamamen farklı
    durumun cümlesi) burada GÖRÜNMEMELİ."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.locator("#panel-arama").fill("bu-hicbir-urunle-eslesmeyecek-xyz")
    sayfa.wait_for_selector("text=Bu süzgeçlere uyan ürün yok", timeout=15000)
    assert "Henüz ürün eklemedin" not in sayfa.content()

    sayfa.get_by_role("button", name="Süzgeçleri temizle").click()
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)


# ── Panel üst kutucukları (BACKLOG C4) ────────────────────────────

def test_ust_kutucuklar_veri_yokken_anlamli_metin_gosterir(sayfa, sunucu):
    """Kabul ölçütü: veri yokken kutucuk sayı yerine anlamlı bir şey
    söylüyor. Bu paket içinde worker çalışmadığı için yeni eklenen ürün
    hiçbir kutucuğu besleyecek veriye sahip DEĞİL — üçü de "boş" hâlde
    olmalı, "0" YAZMAMALI (0 ürün yerine bilgilendirici cümle).

    URL BİLEREK KENDİNE ÖZGÜ: varsayılan `_urun_ekle` URL'si ("ekran-
    karti") `sunucu` fixture'ının paylaştığı DB'de başka testlerin (bkz.
    `test_sinyalli_kartta_...`) ZATEN `sinyal="dip"` yazdığı bir ürüne
    karşılık geliyordu — ÜRÜN KİMLİĞİ KANONİK URL'YE göre KULLANICILAR
    ARASI PAYLAŞILIR (MIMARI.md), bu yüzden "yeni ürün" varsayımı yanlıştı
    ve tam paket içinde (ama tek başına değil) ÖLÇÜLDÜ: bu test o zaman
    yanlışlıkla "1 ürün" görüyordu, "şu an yok" değil."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, url="https://www.example.com/urun/c4-bos-durum", hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.wait_for_selector("text=Dip bölgesinde", timeout=15000)
    icerik = sayfa.content()
    assert "şu an yok" in icerik
    assert "henüz yok" in icerik
    assert "son 30 günde düşüş yok" in icerik
    # Üçüncü kutucuğun aksine burada GİDİLECEK gerçek bir ürün yok — sahte
    # bir hedef uydurmak yerine (bkz. UstKutucuklar.tsx) bu durumda kutucuk
    # hiç LINK olmamalı.
    assert sayfa.get_by_role("link", name="Son 30 günde en büyük düşüş").count() == 0


def _dip_ve_dusen_urun_kur(sunucu, eposta: str) -> None:
    """Worker'ın normalde günler içinde yazacağı sütunları/okumaları elle
    kuruyoruz (bkz. `test_sinyalli_kartta_...`, BACKLOG A8 — aynı desen):
    üç kutucuğun ÜÇÜ de gerçek veriye tepki veriyor mu diye tek üründe
    hepsini birden sağlıyoruz — dip sinyali, bugün okunmuş VE değişmiş
    fiyat, son 30 günde gerçek bir düşüş."""
    from datetime import timedelta

    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from keepmoney.models import PriceReading, Source, User, Watch
    from keepmoney.zaman import utc_simdi

    motor = sa.create_engine(f"sqlite:///{sunucu.db_yolu}")
    db = Session(motor)
    # `_kullanicinin_urunu` burada KULLANILAMAZ: bu testte kullanıcının İKİ
    # ürünü var (`.one()` patlar) — hangisinin "dusen" olduğunu kaynak
    # URL'sinden ayırt ediyoruz (aynı desen `_uc_urun_farkli_fiyatla_kur`'da).
    kullanici = db.query(User).filter(User.email == eposta).one()
    izlemeler = db.query(Watch).filter(Watch.user_id == kullanici.id).all()
    urun = next(w.product for w in izlemeler if "dusen" in w.product.sources[0].url)
    kaynak = db.query(Source).filter(Source.product_id == urun.id).one()
    simdi = utc_simdi()
    db.add(PriceReading(product_id=urun.id, source_id=kaynak.id,
                        fiyat=1000, ts=simdi - timedelta(days=5)))
    db.add(PriceReading(product_id=urun.id, source_id=kaynak.id,
                        fiyat=850, ts=simdi))
    urun.guncel_fiyat = 850
    urun.son_kontrol = simdi
    urun.sinyal = "dip"
    urun.dip90 = 850.0
    urun.medyan90 = 1000.0
    urun.yuzdelik = 92
    urun.gecmis_gun = 5
    db.commit()
    db.close()
    motor.dispose()


def test_ust_kutucuklar_uc_kutu_da_dogru_eylemi_yapar(sayfa, sunucu):
    """Kabul ölçütü: üç kutucuk da tıklanabilir ve doğru eylemi yapıyor."""
    eposta = _kayit_ol(sayfa, sunucu)
    # `:has(h3)`: BU testte kutucuk 3 KENDİSİ de `/izleme/{id}`ye giden bir
    # link olacak (bkz. UstKutucuklar.tsx) — düz `a[href^='/izleme/']`
    # ONU DA yakalardı. Panel kartları h3 ürün adı taşır, kutucuk taşımaz.
    kartlar = sayfa.locator("a[href^='/izleme/']:has(h3)")
    _urun_ekle(sayfa, url="https://www.example.com/urun/dusen", hedef="")
    expect(kartlar).to_have_count(1, timeout=15000)
    _urun_ekle(sayfa, url="https://www.example.com/urun/diger", hedef="")
    expect(kartlar).to_have_count(2, timeout=15000)

    _dip_ve_dusen_urun_kur(sunucu, eposta)
    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_selector("text=Dip bölgesinde", timeout=15000)

    # Kutu 1: "Dip bölgesinde N ürün" → C2'nin "sinyal=dip" süzgecini açar.
    sayfa.get_by_role("button", name="Dip bölgesinde").click()
    expect(sayfa.locator("#panel-sinyal-suzgec")).to_have_value("dip")
    expect(kartlar).to_have_count(1, timeout=15000)
    assert kartlar.first.locator("h3").inner_text() == "dusen"

    # Süzgeci temizleyip kutu 2'yi test et — "Hepsini temizle" burada
    # KULLANILIR ("Süzgeçleri temizle" yalnızca SONUÇ BOŞSA görünür, bu
    # durumda 1 sonuç olduğu için o buton yok, bkz. C2 boş-sonuç mesajı).
    sayfa.get_by_role("button", name="Hepsini temizle").click()
    expect(kartlar).to_have_count(2, timeout=15000)

    # Kutu 2: "Bugün M fiyat değişti" → C1'in "son değişim" sıralamasını açar.
    sayfa.get_by_role("button", name="Bugün değişen").click()
    expect(sayfa.locator("#panel-siralama")).to_have_value("son_degisim")

    # Kutu 3: gerçek ürüne gider.
    sayfa.get_by_role("link", name="Son 30 günde en büyük düşüş").click()
    sayfa.wait_for_selector("text=Fiyat geçmişi", timeout=15000)
    assert "dusen" in sayfa.content()


# ── Çoklu kaynak: öneri → seçim → ekleme ─────────────────────────
# Bu akış bugün eklendi ve yalnızca birim testleriyle doğrulanmıştı:
# "JSX'te düğme var" ile "düğme çalışıyor" arasındaki farkı kapatan tek
# yer burası. Toplayıcı ARAMASI sahteleniyor (dış siteye çıkmamak için) ama
# EKLEME gerçek: POST → servis → veritabanı → yeniden çekim → DOM.

def _detaya_git(s: Page, sunucu: str) -> None:
    _kayit_ol(s, sunucu)
    _urun_ekle(s)
    s.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    s.locator("a[href^='/izleme/']").first.click()
    s.wait_for_selector("text=Kaynaklar", timeout=15000)


def test_kaynak_onerisi_secilince_gercekten_eklenir(sayfa, sunucu):
    sayfa.route(
        "**/kaynak-onerileri",
        lambda rota: rota.fulfill(
            status=200, content_type="application/json",
            body='[{"ad":"Asus RTX 5070 Ti Prime 16GB",'
                 '"url":"https://www.akakce.com/x-fiyati,1234567.html"}]'))

    _detaya_git(sayfa, sunucu)

    # Kaynak listesi arayüzde SATICI ADIYLA görünür (akakçe kuralında
    # `satici: "Akakçe"`), host'la değil.
    kaynak_baglantisi = sayfa.locator("a[href*='akakce.com']")

    sayfa.get_by_role("button", name="Başka mağazalarda ara").click()
    sayfa.wait_for_selector("text=Asus RTX 5070 Ti Prime 16GB", timeout=15000)

    # Aday listelenmiş olması TEK BAŞINA hiçbir şeyi değiştirmemeli:
    # görünen tek akakçe bağlantısı önerinin kendisi olmalı.
    assert kaynak_baglantisi.count() == 1

    sayfa.get_by_role(
        "button", name="Asus RTX 5070 Ti Prime 16GB kaynağını ekle").click()
    # Ekleme gerçek: POST → servis → veritabanı → yeniden çekim → DOM.
    # `wait_for_function` KULLANILMIYOR: CSP `unsafe-eval`i engelliyor
    # (doğru davranış) ve string olarak JS değerlendirilemiyor.
    expect(kaynak_baglantisi).to_have_count(2, timeout=15000)
    assert "Akakçe" in sayfa.content()
    assert not sayfa.sunucu_hatalari                  # type: ignore[attr-defined]


def test_arama_kendiliginden_calismaz(sayfa, sunucu):
    """Dış siteye çıkan ve gerçek tarayıcı açabilen bir uç, sayfa her
    açıldığında tetiklenmemeli — hem kullanıcıyı bekletir hem toplayıcıya
    gereksiz yük bindirir."""
    cagrildi = []
    sayfa.route("**/kaynak-onerileri",
                lambda rota: (cagrildi.append(1),
                              rota.fulfill(status=200,
                                           content_type="application/json",
                                           body="[]"))[1])
    _detaya_git(sayfa, sunucu)
    sayfa.wait_for_timeout(1500)
    assert cagrildi == []


def test_eslesme_bulunamazsa_kullaniciya_soylenir(sayfa, sunucu):
    sayfa.route("**/kaynak-onerileri",
                lambda rota: rota.fulfill(status=200,
                                          content_type="application/json",
                                          body="[]"))
    _detaya_git(sayfa, sunucu)
    sayfa.get_by_role("button", name="Başka mağazalarda ara").click()
    sayfa.wait_for_selector("text=eşleşme bulunamadı", timeout=15000)


def test_arama_bozuksa_akis_kirilmaz(sayfa, sunucu):
    """Arama bir KOLAYLIK, kritik yol değil: sayfa çalışmaya devam etmeli."""
    sayfa.beklenen_5xx.add("kaynak-onerileri")       # type: ignore[attr-defined]
    sayfa.route("**/kaynak-onerileri",
                lambda rota: rota.fulfill(status=503, body="{}"))
    _detaya_git(sayfa, sunucu)
    sayfa.get_by_role("button", name="Başka mağazalarda ara").click()
    sayfa.wait_for_selector("text=Arama şu an yapılamadı", timeout=15000)
    assert sayfa.get_by_role("heading", name="Fiyat geçmişi").is_visible()


def test_ad_okunmadan_arayinca_sebep_gosterilir(sayfa, sunucu):
    """Geçici ve kullanıcının ÇÖZEBİLECEĞİ durum, kalıcı arıza gibi
    görünmemeli.

    Ürün adı ilk taramada okunuyor; o ana kadar arama yapılamıyor. Sunucu
    sebebi söylüyor (409); arayüz onu geçip "Arama şu an yapılamadı" deseydi
    kullanıcı özelliğin bozuk olduğunu sanırdı.
    """
    sayfa.route(
        "**/kaynak-onerileri",
        lambda rota: rota.fulfill(
            status=409, content_type="application/json",
            body='{"detail":"Ürün adı henüz okunmadı — arama için önce ilk '
                 'tarama gerekiyor. Birkaç dakika sonra tekrar dene."}'))
    _detaya_git(sayfa, sunucu)
    sayfa.get_by_role("button", name="Başka mağazalarda ara").click()
    sayfa.wait_for_selector("text=Ürün adı henüz okunmadı", timeout=15000)


# ── Pazar derinliği gösterimi ────────────────────────────────────
# Koruma katmanının kullandığı sinyal kullanıcıya da gösteriliyor; amaç
# kararın DENETLENEBİLİR olması. Burada API yanıtı değiştirilerek gerçek
# derlenmiş paketin bu veriyi doğru yorumlayıp yorumlamadığı sınanıyor —
# uyarı eşiği arayüzde ayrıca hesaplanıyor ve yanlış hesaplanırsa kullanıcı
# ya boşuna korkar ya da gerçek tuzağı görmez.

def _detay_yanitini_degistir(s: Page, **kaynak_alanlari):
    """`/api/izlemeler/{id}` yanıtına pazar alanlarını enjekte eder."""
    def islemci(rota):
        yanit = rota.fetch()
        veri = yanit.json()
        for k in veri["urun"]["kaynaklar"]:
            k.update(kaynak_alanlari)
        rota.fulfill(response=yanit, json=veri)

    # Yalnızca TEK izlemenin detayı: `/api/izlemeler/{sayısal id}`.
    #
    # `"/api/izlemeler/" in u` YETERSİZDİ (BACKLOG A8'de kırıldı): kart
    # artık `/api/izlemeler/kivilcimlar`'ı da çağırıyor ve bu yol da aynı
    # alt dizgeyi içeriyor — `islemci` o yanıtı da yakalayıp `veri["urun"]`
    # okumaya çalışıyor, ki kıvılcım yanıtında böyle bir anahtar yok
    # (`{"1": [...], "2": [...]}` biçiminde). Regex SAYISAL id'yle sınırlıyor.
    s.route(re.compile(r"/api/izlemeler/\d+$"), islemci)


def test_pazar_derinligi_gosteriliyor(sayfa, sunucu):
    _detay_yanitini_degistir(sayfa, satici_sayisi=14, ikinci_fiyat=41500.0,
                             son_fiyat=38999.0)
    _detaya_git(sayfa, sunucu)
    icerik = sayfa.content()
    assert "14 satıcı" in icerik
    assert "41.500" in icerik


def test_aykiri_fiyat_uyarisi_gosteriliyor(sayfa, sunucu):
    """En ucuz, ikinciden orantısız ucuzsa kullanıcı UYARILMALI: fiyat
    geçmişi olmayan üründe elindeki tek işaret bu."""
    _detay_yanitini_degistir(sayfa, satici_sayisi=9, ikinci_fiyat=52000.0,
                             son_fiyat=4000.0)
    _detaya_git(sayfa, sunucu)
    assert "tek satıcı belirgin ucuz" in sayfa.content()


def test_makul_farkta_uyari_cikmiyor(sayfa, sunucu):
    """Yanlış pozitif kullanıcıyı uyarıya karşı duyarsızlaştırır."""
    _detay_yanitini_degistir(sayfa, satici_sayisi=9, ikinci_fiyat=46000.0,
                             son_fiyat=40000.0)
    _detaya_git(sayfa, sunucu)
    icerik = sayfa.content()
    assert "9 satıcı" in icerik
    assert "belirgin ucuz" not in icerik


def test_pazar_verisi_yoksa_satir_cikmiyor(sayfa, sunucu):
    """Toplayıcı olmayan üründe boş bir '🏪' satırı gürültüdür."""
    _detaya_git(sayfa, sunucu)
    assert "satıcı" not in sayfa.locator("section").last.inner_text()


def test_kaynak_tablosunda_en_ucuz_isaretli_ve_sebep_yaziyor(sayfa, sunucu):
    """BACKLOG F3: en ucuz mağaza işaretli, okunamayan her kaynağın sebebi
    yazıyor (bot duvarı) ve o satırdan doğrudan akakçe araması tetiklenebilir."""
    def islemci(rota):
        yanit = rota.fetch()
        veri = yanit.json()
        sablon = veri["urun"]["kaynaklar"][0]
        ortak = {"cikis_url": "", "ortaklik": False, "satici_sayisi": None,
                 "ikinci_fiyat": None, "son_kontrol": "2026-01-01T00:00:00"}
        veri["urun"]["kaynaklar"] = [
            {**sablon, **ortak, "id": 101, "satici": "Ucuz Mağaza",
             "son_fiyat": 1000.0, "durum": "OK",
             "host": "ucuz.com", "url": "https://ucuz.com/x"},
            {**sablon, **ortak, "id": 102, "satici": "Pahalı Mağaza",
             "son_fiyat": 2000.0, "durum": "OK",
             "host": "pahali.com", "url": "https://pahali.com/x"},
            {**sablon, **ortak, "id": 103, "satici": "Engelli Mağaza",
             "son_fiyat": None, "durum": "ENGELLI",
             "host": "engelli.com", "url": "https://engelli.com/x"},
        ]
        rota.fulfill(response=yanit, json=veri)

    sayfa.route(re.compile(r"/api/izlemeler/\d+$"), islemci)
    _detaya_git(sayfa, sunucu)

    tablo = sayfa.locator("table")
    ucuz_satir = tablo.locator("tr", has_text="Ucuz Mağaza")
    pahali_satir = tablo.locator("tr", has_text="Pahalı Mağaza")
    engelli_satir = tablo.locator("tr", has_text="Engelli Mağaza")

    expect(ucuz_satir.get_by_text("en ucuz")).to_be_visible()
    assert "en ucuz" not in pahali_satir.inner_text()
    assert "bot duvarı" in engelli_satir.inner_text()
    assert "akakçe kaynağı ara" in engelli_satir.inner_text()


def _urun_yanitini_gecmis_ve_serilerle_degistir(s: Page, seriler: list):
    """`/api/izlemeler/{id}` yanıtına sahte `gecmis` + `seriler` enjekte
    eder (BACKLOG B2/B3). Gerçek fiyat geçmişi kurmak yerine mock kullanmak
    F3'teki `test_kaynak_tablosunda_...` ile aynı desen: kontrollü, DB'siz
    veri — yalnızca arayüzün ALDIĞI veriyi doğru çizip çizmediği test edilir."""
    def islemci(rota):
        yanit = rota.fetch()
        veri = yanit.json()
        veri["urun"]["gecmis"] = [
            {"gun": "2026-01-01", "fiyat": 1000.0, "stokta": True},
            {"gun": "2026-01-02", "fiyat": 950.0, "stokta": True},
        ]
        veri["urun"]["seriler"] = seriler
        rota.fulfill(response=yanit, json=veri)

    s.route(re.compile(r"/api/izlemeler/\d+$"), islemci)


def test_tek_kaynakli_urunde_magazalara_ayir_dugmesi_yok(sayfa, sunucu):
    """BACKLOG B3 kabul ölçütü: tek kaynaklı üründe düğme hiç görünmüyor
    — backend zaten `seriler` boş döner (B2), burada arayüzün bunu doğru
    yorumladığı doğrulanıyor."""
    _urun_yanitini_gecmis_ve_serilerle_degistir(sayfa, [])
    _detaya_git(sayfa, sunucu)
    sayfa.wait_for_selector("svg", timeout=15000)
    assert sayfa.get_by_role("button", name="Mağazalara ayır").count() == 0


def test_uc_kaynakli_urunde_uc_cizgi_ve_renkler_tutarli(sayfa, sunucu):
    """Kabul ölçütü: üç kaynaklı üründe üç ayrı çizgi, renkler tutarlı."""
    seriler = [
        {"kaynak_id": 1, "host": "amazon.com.tr", "noktalar": [
            {"gun": "2026-01-01", "fiyat": 1000.0, "stokta": True},
            {"gun": "2026-01-02", "fiyat": 950.0, "stokta": True}]},
        {"kaynak_id": 2, "host": "hepsiburada.com", "noktalar": [
            {"gun": "2026-01-01", "fiyat": 1100.0, "stokta": True},
            {"gun": "2026-01-02", "fiyat": 1050.0, "stokta": True}]},
        {"kaynak_id": 3, "host": "trendyol.com", "noktalar": [
            {"gun": "2026-01-01", "fiyat": 900.0, "stokta": True},
            {"gun": "2026-01-02", "fiyat": 890.0, "stokta": True}]},
    ]
    _urun_yanitini_gecmis_ve_serilerle_degistir(sayfa, seriler)
    _detaya_git(sayfa, sunucu)
    sayfa.wait_for_selector("svg", timeout=15000)

    sayfa.get_by_role("button", name="Mağazalara ayır").click()
    rozetler = sayfa.locator("[aria-label='Kaynakları göster/gizle'] button")
    expect(rozetler).to_have_count(3, timeout=15000)
    cizgiler = sayfa.locator("svg path.recharts-line-curve")
    expect(cizgiler).to_have_count(3, timeout=15000)

    # Renkler tutarlı: üç rozetin nokta rengi birbirinden farklı olmalı —
    # host adının hash'inden geldiği için (index'ten değil) her açılışta
    # AYNI host AYNI rengi taşır.
    renkler = {
        rozetler.nth(i).locator("span").first
        .evaluate("el => getComputedStyle(el).backgroundColor")
        for i in range(3)
    }
    assert len(renkler) == 3
    assert not sayfa.sunucu_hatalari


def test_kaynak_gizle_goster_cizgiyi_kaldirir_ve_geri_getirir(sayfa, sunucu):
    """Y ekseninin piksel piksel daralıp genişlediğini doğrulamak
    recharts'ın kendi render davranışını test eder; ölçüm mantığı zaten
    `gorunurFiyatAraligi` birim testleriyle kanıtlı (kaynakRenkleri.test.ts).
    Burada asıl ölçülen: gizle/göster düğmesi GERÇEKTEN çizgiyi kaldırıp
    geri getiriyor, sayfa çökmüyor."""
    seriler = [
        {"kaynak_id": 1, "host": "amazon.com.tr", "noktalar": [
            {"gun": "2026-01-01", "fiyat": 1000.0, "stokta": True},
            {"gun": "2026-01-02", "fiyat": 950.0, "stokta": True}]},
        {"kaynak_id": 2, "host": "hepsiburada.com", "noktalar": [
            {"gun": "2026-01-01", "fiyat": 1100.0, "stokta": True},
            {"gun": "2026-01-02", "fiyat": 1050.0, "stokta": True}]},
        {"kaynak_id": 3, "host": "trendyol.com", "noktalar": [
            {"gun": "2026-01-01", "fiyat": 900.0, "stokta": True},
            {"gun": "2026-01-02", "fiyat": 890.0, "stokta": True}]},
    ]
    _urun_yanitini_gecmis_ve_serilerle_degistir(sayfa, seriler)
    _detaya_git(sayfa, sunucu)
    sayfa.wait_for_selector("svg", timeout=15000)

    sayfa.get_by_role("button", name="Mağazalara ayır").click()
    cizgiler = sayfa.locator("svg path.recharts-line-curve")
    expect(cizgiler).to_have_count(3, timeout=15000)

    rozetler = sayfa.locator("[aria-label='Kaynakları göster/gizle'] button")
    rozetler.first.click()
    expect(cizgiler).to_have_count(2, timeout=15000)

    rozetler.first.click()
    expect(cizgiler).to_have_count(3, timeout=15000)
    assert not sayfa.sunucu_hatalari


def _urun_yanitini_gecmisle_degistir(s: Page, gecmis: list):
    """`_urun_yanitini_gecmis_ve_serilerle_degistir`in tekil hâli — B4
    testleri `seriler`e değil, birleşik `gecmis`teki `stokta` alanına
    bakıyor."""
    def islemci(rota):
        yanit = rota.fetch()
        veri = yanit.json()
        veri["urun"]["gecmis"] = gecmis
        veri["urun"]["seriler"] = []
        rota.fulfill(response=yanit, json=veri)

    s.route(re.compile(r"/api/izlemeler/\d+$"), islemci)


def test_stok_yok_boslugu_aciklama_gosterir(sayfa, sunucu):
    """BACKLOG B4 kabul ölçütü: stoksuz dönem gözle ayırt ediliyor. Grafik
    çizgi kırılmasını piksel piksel doğrulamak recharts'ın kendi render
    davranışını test eder (ölçüm mantığı zaten `stokBosluklari.test.ts`
    ile kanıtlı); burada arayüzün stok-yok noktasını GERÇEKTEN "kesik
    çizgi" açıklamasıyla ve taramalı arka planla işaretlediği doğrulanıyor."""
    gecmis = [
        {"gun": "2026-01-01", "fiyat": 1000.0, "stokta": True},
        {"gun": "2026-01-02", "fiyat": None, "stokta": False},
        {"gun": "2026-01-03", "fiyat": 1050.0, "stokta": True},
    ]
    _urun_yanitini_gecmisle_degistir(sayfa, gecmis)
    _detaya_git(sayfa, sunucu)
    sayfa.wait_for_selector("svg", timeout=15000)

    expect(sayfa.get_by_text("kesik çizgi = stokta yok")).to_be_visible()
    # Taramalı arka plan: `<pattern id="stokYokDeseni">` yalnızca gerçekten
    # bir boşluk aralığı hesaplanınca `ReferenceArea` tarafından kullanılır.
    assert sayfa.locator("pattern#stokYokDeseni").count() == 1
    assert not sayfa.sunucu_hatalari


def test_stok_bosluğu_yoksa_aciklama_gorunmez(sayfa, sunucu):
    """Gürültü olmasın: hiç stok-yok günü yoksa açıklama metni hiç
    basılmamalı — her ürün detayında görünen sabit bir dipnot değil."""
    gecmis = [
        {"gun": "2026-01-01", "fiyat": 1000.0, "stokta": True},
        {"gun": "2026-01-02", "fiyat": 950.0, "stokta": True},
    ]
    _urun_yanitini_gecmisle_degistir(sayfa, gecmis)
    _detaya_git(sayfa, sunucu)
    sayfa.wait_for_selector("svg", timeout=15000)

    assert sayfa.get_by_text("kesik çizgi = stokta yok").count() == 0
    assert not sayfa.sunucu_hatalari


def _urun_yanitini_tooltip_icin_hazirla(s: Page, gecmis: list, tum_zamanlar_dibi_tarih: str):
    """BACKLOG B5 — `_urun_yanitini_gecmisle_degistir`in tekil hâli: tam bir
    `baglam` (medyana göre fark ve tüm zamanlar dibi tooltip'te okunabilsin
    diye) ve TEK bir kaynak (birleşik görünümde "hangi mağaza" bilinsin
    diye) enjekte eder."""
    def islemci(rota):
        yanit = rota.fetch()
        veri = yanit.json()
        veri["urun"]["gecmis"] = gecmis
        veri["urun"]["seriler"] = []
        veri["urun"]["baglam"] = {
            "sinyal": "ucuz", "emoji": "🟡", "yorum": "test", "dip90": 900.0,
            "medyan90": 1000.0, "yuzdelik": 80, "tum_zamanlar_dibi": 900.0,
            "tum_zamanlar_dibi_tarih": tum_zamanlar_dibi_tarih, "en_dusuk_gun": 0,
            "gun_sayisi": len(gecmis), "sahte_indirim": False,
            "trend_yonu": "sabit", "iyi_firsat": False,
        }
        sablon = veri["urun"]["kaynaklar"][0]
        ortak = {"cikis_url": "", "ortaklik": False, "satici_sayisi": None,
                 "ikinci_fiyat": None, "son_kontrol": "2026-01-01T00:00:00"}
        veri["urun"]["kaynaklar"] = [
            {**sablon, **ortak, "id": 101, "satici": "Test Mağazası",
             "son_fiyat": gecmis[-1]["fiyat"], "durum": "OK",
             "host": "test-magaza.com", "url": "https://test-magaza.com/x"},
        ]
        rota.fulfill(response=yanit, json=veri)

    s.route(re.compile(r"/api/izlemeler/\d+$"), islemci)


def test_grafik_tooltipi_dokununca_sabitlenir_ve_kaybolmaz(sayfa, sunucu):
    """BACKLOG B5 kabul ölçütü: telefonda dokununca tooltip çıkıyor ve
    kaybolmuyor. recharts'ın kendi hover/dokunma durumuna güvenilmiyor
    (bkz. FiyatGrafigi.tsx yorumu) — tıklama (dokunuşun tarayıcıda ürettiği
    olay) noktayı SABİTLER, fare imleci başka yere gitse de kutu kalır."""
    gecmis = [
        {"gun": "2026-01-01", "fiyat": 1000.0, "stokta": True},
        {"gun": "2026-01-02", "fiyat": 950.0, "stokta": True},
        {"gun": "2026-01-03", "fiyat": 900.0, "stokta": True},
    ]
    _urun_yanitini_tooltip_icin_hazirla(sayfa, gecmis, "2026-01-03")
    sayfa.set_viewport_size({"width": 375, "height": 812})
    _detaya_git(sayfa, sunucu)
    sayfa.wait_for_selector("svg", timeout=15000)

    grafik = sayfa.locator(".recharts-surface")
    kutu = grafik.bounding_box()
    assert kutu is not None
    # Son nokta: sağ kenara yakın bir yere dokunmak en yakın (son) noktayı
    # seçer — recharts kategorik eksende en yakın indekse yuvarlar.
    sayfa.mouse.click(kutu["x"] + kutu["width"] * 0.95, kutu["y"] + kutu["height"] * 0.5)

    kapat = sayfa.get_by_role("button", name="kapat ✕")
    expect(kapat).to_be_visible(timeout=5000)
    assert "Test Mağazası" in sayfa.content()

    # Fare/dokunuş BAŞKA bir yere gitse de kutu KALIR (asıl kabul ölçütü).
    sayfa.mouse.move(kutu["x"] - 50, kutu["y"] - 50)
    sayfa.wait_for_timeout(300)
    expect(kapat).to_be_visible()

    kapat.click()
    expect(kapat).to_have_count(0)
    assert not sayfa.sunucu_hatalari


def test_tum_zamanlar_dibi_gunu_tooltipte_isaretli(sayfa, sunucu):
    """BACKLOG B5 kabul ölçütü: tüm zamanlar dibi olan gün ayrıca
    işaretli."""
    gecmis = [
        {"gun": "2026-01-01", "fiyat": 1000.0, "stokta": True},
        {"gun": "2026-01-02", "fiyat": 950.0, "stokta": True},
        {"gun": "2026-01-03", "fiyat": 900.0, "stokta": True},
    ]
    _urun_yanitini_tooltip_icin_hazirla(sayfa, gecmis, "2026-01-03")
    _detaya_git(sayfa, sunucu)
    sayfa.wait_for_selector("svg", timeout=15000)

    grafik = sayfa.locator(".recharts-surface")
    kutu = grafik.bounding_box()
    assert kutu is not None
    sayfa.mouse.click(kutu["x"] + kutu["width"] * 0.95, kutu["y"] + kutu["height"] * 0.5)
    # Fareyi grafikten UZAĞA taşı: geçici hover kutusu bunula kaybolur,
    # kalan HER ŞEY sabitlenmiş (tıklamayla açılan) kutudan gelmeli — aksi
    # hâlde bu test hover yoluyla YANLIŞLIKLA geçebilir (sabitleme
    # tamamen bozulsa bile).
    sayfa.mouse.move(kutu["x"] - 50, kutu["y"] - 50)
    sayfa.wait_for_timeout(300)

    # Sayfada BAŞKA bir cümle de "...tüm zamanların dibini..." geçiriyor
    # (E3 uyarı kurulumu açıklaması) — rozet emojisiyle birlikte aranır,
    # aksi hâlde strict mode iki eşleşme bulup patlar.
    expect(sayfa.get_by_text("🏆 tüm zamanların dibi")).to_be_visible(timeout=5000)
    assert not sayfa.sunucu_hatalari


# ── BACKLOG H1: CSV dışa aktarma ─────────────────────────────────
#
# Buradaki testler "düğme var mı"yı değil İNDİRMENİN KENDİSİNİ ölçüyor:
# indirilen dosya tarayıcının diskine yazılıyor ve BAYTLARI okunuyor.
# `test_disa_aktar.py` biçimi zaten sınıyor; burada sınanan, düz `<a
# download>` tercihinin gerçek tarayıcıda gerçekten indirme başlatması ve
# httpOnly çerezin o isteğe TAŞINMASI — ikisi de yalnızca burada görülebilir
# (TestClient'ın Bearer başlığıyla ölçülemez).

def _indir(sayfa: Page):
    """"CSV indir" bağlantısına tıklar, indirmeyi bekler ve döndürür."""
    with sayfa.expect_download(timeout=15000) as indirme_bilgisi:
        sayfa.get_by_role("link", name="CSV indir").first.click()
    return indirme_bilgisi.value


def test_panel_csv_indirmesi_gercekten_iniyor(sayfa, sunucu):
    """Kabul ölçütü zinciri: dosya iniyor, BOM'la başlıyor, kolonlar
    noktalı virgülle ayrılıyor."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa)
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    indirme = _indir(sayfa)
    assert indirme.suggested_filename.startswith("keepmoney-takip-listem-")
    assert indirme.suggested_filename.endswith(".csv")

    icerik = pathlib.Path(indirme.path()).read_bytes()
    assert icerik.startswith(b"\xef\xbb\xbf")
    baslik = icerik.decode("utf-8-sig").splitlines()[0]
    assert baslik.split(";")[0] == "Ürün"
    assert len(baslik.split(";")) == 13
    assert not sayfa.sunucu_hatalari


def test_urun_gecmisi_csv_olarak_iniyor(sayfa, sunucu):
    """Detay sayfasındaki indirme, dosya adında ÜRÜN ADINI taşımalı —
    yoksa üç ürün dışa aktaran kullanıcının klasöründe üç `gecmis.csv`
    kalır."""
    eposta = _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa)
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    # Ürün adı URL'den türetiliyor (worker bu pakette çalışmıyor); adı
    # doğrudan veritabanına yazıp Türkçe harflerin dosya adında ASCII'ye
    # düşürüldüğünü de görelim.
    import sqlite3
    with sqlite3.connect(sunucu.db_yolu) as baglanti:
        baglanti.execute(
            "UPDATE products SET ad = ? WHERE id = ("
            "  SELECT w.product_id FROM watches w JOIN users u"
            "   ON u.id = w.user_id WHERE u.email = ?)",
            ("Kulaklık Şarj Ünitesi", eposta))

    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("text=Fiyat geçmişi", timeout=15000)

    indirme = _indir(sayfa)
    assert "kulaklik-sarj-unitesi" in indirme.suggested_filename
    assert indirme.suggested_filename.endswith(".csv")

    icerik = pathlib.Path(indirme.path()).read_bytes().decode("utf-8-sig")
    assert icerik.splitlines()[0].split(";") == [
        "Ürün", "Mağaza", "Site", "Tarih", "Saat", "Fiyat (TL)", "Stokta"]
    assert not sayfa.sunucu_hatalari


def test_bos_panelde_csv_dugmesi_yok(sayfa, sunucu):
    """Yalnızca başlık satırından ibaret bir dosya indirmek "bir şey ters
    gitti" hissi verir; hiç ürün yokken düğme DOM'a girmiyor."""
    _kayit_ol(sayfa, sunucu)
    # H2'den beri yeni kullanıcının boş paneli rehberi gösteriyor.
    sayfa.wait_for_selector("text=Üç adımda başla", timeout=15000)
    expect(sayfa.get_by_role("link", name="CSV indir")).to_have_count(0)


# ── BACKLOG H2: panel ilk açılış rehberi ─────────────────────────

def _ornek_link() -> str:
    """Rehberdeki örnek adresi KAYNAKTAN okur.

    Testin içine ikinci bir kopya yazmak, sabit değiştiğinde testin
    "geçmeye devam ederken yanlış şeyi doğruladığı" hâle gelmesi demekti.
    `tests/test_siteler.py` aynı sabiti kural dosyalarıyla eşliyor; ikisi
    birlikte sabiti hem geçerli hem desteklenen tutuyor."""
    kaynak = (KOK / "arayuz" / "src" / "yardimcilar" / "rehber.ts"
              ).read_text(encoding="utf-8")
    eslesme = re.search(r"export const ORNEK_LINK\s*=\s*\n?\s*'([^']+)'", kaynak)
    assert eslesme, "rehber.ts içinde ORNEK_LINK bulunamadı"
    return eslesme.group(1)


def test_yeni_kullanicida_uc_adimli_rehber_gorunuyor(sayfa, sunucu):
    """BACKLOG H2 — "üç adım: link yapıştır → sinyal birikirken bekle →
    uyarı kur". Üçünün de EKRANDA olduğu doğrulanıyor; ikinci adım A7'nin
    bulgusunu önceden söylediği için asıl değerli olan o."""
    _kayit_ol(sayfa, sunucu)
    sayfa.wait_for_selector("text=Üç adımda başla", timeout=15000)

    icerik = sayfa.content()
    assert "Bir ürün linki yapıştır" in icerik
    assert "Fiyat hafızası birikirken bekle" in icerik
    assert "Uyarı kur" in icerik
    # Adımlar SIRALI bir liste olmalı: ekran okuyucu "3 öğeden 2." desin.
    expect(sayfa.locator("section[aria-labelledby='rehber-basligi'] ol li")
           ).to_have_count(3)
    assert not sayfa.sunucu_hatalari


def test_ornek_link_url_kutusunu_dolduruyor(sayfa, sunucu):
    """BACKLOG H2 — "örnek link (tıklayınca kutuya dolar)". Kutuyu DOLDURUR
    ama GÖNDERMEZ: kullanıcı ne eklediğini görmeden "Takibe al"a basılmış
    olmamalı."""
    _kayit_ol(sayfa, sunucu)
    sayfa.wait_for_selector("text=Üç adımda başla", timeout=15000)

    kutu = sayfa.locator("input[type=url]")
    expect(kutu).to_have_value("")

    sayfa.get_by_role("button", name="Elimde link yok, örnekle dene").click()
    expect(kutu).to_have_value(_ornek_link())
    # Kendiliğinden EKLENMEDİ: liste hâlâ boş, rehber duruyor.
    expect(sayfa.locator("a[href^='/izleme/']")).to_have_count(0)
    assert "Üç adımda başla" in sayfa.content()
    assert not sayfa.sunucu_hatalari


def test_ilk_urun_eklenince_rehber_kayboluyor_ve_geri_gelmiyor(sayfa, sunucu):
    """BACKLOG H2 kabul ölçütü: "ilk ürün eklenince rehber kaybolur, GERİ
    GELMEZ".

    Dört aşama birden sınanıyor çünkü her biri BAŞKA bir mekanizmayı
    yakalıyor:
      1. ürün eklenince kaybolur,
      2. liste doluyken yenilenince gelmez,
      3. ürünün HEPSİ silinip liste boşalınca gelmez (aynı SPA oturumu),
      4. BİR DE boş listeyle YENİDEN YÜKLENİNCE gelmez.

    4. ŞART: 1-3 arası tek başına, kalıcılık TAMAMEN BOZUKKEN de GEÇİYOR
    — ÖLÇÜLDÜ. Sebebi: 3. aşamada React durumu (`rehberBitti`) aynı SPA
    oturumunda zaten `true` olmuş oluyor, localStorage'a hiç bakılmıyor.
    localStorage yolunu gerçekten koşturan tek adım, LİSTE BOŞKEN yapılan
    sayfa yenilemesi.
    """
    _kayit_ol(sayfa, sunucu)
    sayfa.wait_for_selector("text=Üç adımda başla", timeout=15000)

    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    expect(sayfa.get_by_text("Üç adımda başla")).to_have_count(0)

    # 2. Yenileme: tercih localStorage'da, sunucuda değil.
    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    expect(sayfa.get_by_text("Üç adımda başla")).to_have_count(0)

    # 3. Tek ürünü de sil → liste yine boş, ama rehber DÖNMEMELİ.
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("text=Takipten çıkar", timeout=15000)
    sayfa.get_by_role("button", name="Takipten çıkar").first.click()
    sayfa.wait_for_selector("dialog[open]", timeout=5000)
    sayfa.locator("dialog[open]").get_by_role(
        "button", name="Takipten çıkar").click()

    sayfa.wait_for_selector("text=Henüz ürün eklemedin", timeout=15000)
    expect(sayfa.get_by_text("Üç adımda başla")).to_have_count(0)

    # 4. Boş listeyle YENİDEN YÜKLE: React durumu sıfırlanır, karar artık
    # yalnızca localStorage'dan gelir. Kalıcılığı gerçekten sınayan
    # TEK adım budur (bkz. docstring).
    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_selector("text=Henüz ürün eklemedin", timeout=15000)
    expect(sayfa.get_by_text("Üç adımda başla")).to_have_count(0)
    assert not sayfa.sunucu_hatalari


# ── Hukuki metinler ve kayıt onayı ───────────────────────────────
#
# KVKK aydınlatma yükümlülüğünün TEKNİK karşılığı. Metnin hukuken yeterli
# olup olmadığı ayrı bir değerlendirme; burada sınanan, mekanizmanın
# gerçekten çalıştığı.

@pytest.mark.parametrize("yol,baslik", [
    ("/gizlilik", "Gizlilik ve Kişisel Verilerin Korunması"),
    ("/kosullar", "Kullanım Koşulları"),
])
def test_hukuki_sayfalar_GIRIS_YAPMADAN_aciliyor(sayfa, sunucu, yol, baslik):
    """ASIL ÖLÇÜT. Giriş duvarının arkasındaki gizlilik metni işe yaramaz:
    kişi hesap açmadan ÖNCE neyin toplandığını okuyabilmeli — kayıt
    ekranındaki onay bağlantısı da oraya gidiyor."""
    sayfa.goto(f"{sunucu}{yol}", wait_until="networkidle")
    expect(sayfa.get_by_role("heading", name=baslik)).to_be_visible(timeout=10000)
    # Giriş ekranına YÖNLENDİRİLMEMELİ
    assert sayfa.locator("input[type=password]").count() == 0
    assert not sayfa.sunucu_hatalari


def test_kayit_onay_kutusu_ISARETLENMEDEN_hesap_acilmiyor(sayfa, sunucu):
    """Onay hem `required` hem düğme kilidi ile korunuyor: tek başına
    `required`e güvenmek, formu programatik gönderen bir yolda onayı
    atlatılabilir kılardı."""
    eposta = f"e2e-{uuid.uuid4().hex[:10]}@ornek.com"
    sayfa.goto(sunucu, wait_until="networkidle")
    sayfa.get_by_text("Hesabım yok, oluştur").click()
    sayfa.locator("input[type=email]").fill(eposta)
    sayfa.locator("input[type=password]").fill("parola12345")

    dugme = sayfa.get_by_role("button", name="Hesap oluştur")
    expect(dugme).to_be_disabled()

    sayfa.locator("input[type=checkbox]").check()
    expect(dugme).to_be_enabled()
    dugme.click()
    sayfa.wait_for_selector("text=Takip listem", timeout=15000)
    assert not sayfa.sunucu_hatalari


def test_kayit_ekraninda_iki_hukuki_baglanti_da_var(sayfa, sunucu):
    sayfa.goto(sunucu, wait_until="networkidle")
    sayfa.get_by_text("Hesabım yok, oluştur").click()
    expect(sayfa.locator("a[href='/kosullar']")).to_have_count(1)
    expect(sayfa.locator("a[href='/gizlilik']")).to_have_count(1)


def test_giris_kipinde_onay_kutusu_YOK(sayfa, sunucu):
    """Var olan kullanıcıya her girişte onay kutusu göstermek anlamsız."""
    sayfa.goto(sunucu, wait_until="networkidle")
    expect(sayfa.locator("input[type=checkbox]")).to_have_count(0)


def test_verilerimi_indir_gercekten_iniyor(sayfa, sunucu):
    """KVKK m.11 erişme/taşınabilirlik — düğmenin varlığı değil DOSYANIN
    kendisi ölçülüyor."""
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)

    sayfa.goto(f"{sunucu}/ayarlar", wait_until="networkidle")
    with sayfa.expect_download(timeout=15000) as indirme_bilgisi:
        sayfa.get_by_role("link", name="Verilerimi indir").click()
    indirme = indirme_bilgisi.value

    assert indirme.suggested_filename.startswith("keepmoney-verilerim-")
    veri = json.loads(pathlib.Path(indirme.path()).read_text(encoding="utf-8"))
    assert set(veri) == {"hesap", "izlemeler", "setler", "bildirimler", "aciklama"}
    assert len(veri["izlemeler"]) == 1
    assert "password_hash" not in json.dumps(veri)
    assert not sayfa.sunucu_hatalari


def test_altbilgide_hukuki_baglantilar_her_sayfada(sayfa, sunucu):
    """Hesap açtıktan sonra metni bir daha bulamamak, "kabul ettim"i
    anlamsız kılar."""
    _kayit_ol(sayfa, sunucu)
    for yol in ("/", "/setler", "/uyarilar"):
        sayfa.goto(f"{sunucu}{yol}", wait_until="networkidle")
        expect(sayfa.locator("footer a[href='/gizlilik']")).to_have_count(1)
        expect(sayfa.locator("footer a[href='/kosullar']")).to_have_count(1)

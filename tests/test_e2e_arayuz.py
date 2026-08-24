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
import os
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

    taban = f"http://127.0.0.1:{port}"
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
    s.get_by_role("button", name="Hesap oluştur").click()
    s.wait_for_selector("text=Takip listem", timeout=15000)
    return eposta


def _urun_ekle(s: Page, url: str = "https://www.example.com/urun/ekran-karti",
               hedef: str = "45000") -> None:
    s.locator("input[type=url]").fill(url)
    if hedef:
        s.locator("input[type=number]").first.fill(hedef)
    s.get_by_role("button", name="Takibe al").click()


# ── Kimlik akışı ─────────────────────────────────────────────────

def test_acilista_giris_ekrani(sayfa, sunucu):
    sayfa.goto(sunucu, wait_until="networkidle")
    assert sayfa.locator("input[type=email]").count() == 1


def test_kayit_ve_panel(sayfa, sunucu):
    _kayit_ol(sayfa, sunucu)
    assert sayfa.get_by_role("heading", name="Takip listem").is_visible()
    assert "Henüz ürün eklemedin" in sayfa.content()      # boş durum


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
    assert "İzlenen ürün" in sayfa.content()

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
    _kayit_ol(sayfa, sunucu)
    _urun_ekle(sayfa, hedef="")
    sayfa.wait_for_selector("a[href^='/izleme/']", timeout=15000)
    sayfa.locator("a[href^='/izleme/']").first.click()
    sayfa.wait_for_selector("#hedef-fiyat", timeout=15000)

    sayfa.locator("#hedef-fiyat").fill("41000")
    sayfa.get_by_role("button", name="Kaydet").click()
    sayfa.wait_for_selector("text=41.000", timeout=15000)

    # Hedefi TEMİZLEME: API'de açık `null` desteklenir, arayüzde de olmalı.
    sayfa.get_by_role("button", name="Hedefi kaldır").click()
    sayfa.wait_for_timeout(1500)
    assert sayfa.get_by_role("button", name="Hedefi kaldır").count() == 0


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
    sayfa.wait_for_selector("text=PC Toplama", timeout=15000)
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
        sayfa.wait_for_selector(f"text={ad}", timeout=15000)

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

    sayfa.get_by_role("button", name="Seti sil (ürünler silinmez)").click()
    sayfa.wait_for_selector("dialog[open]", timeout=5000)
    sayfa.locator("dialog[open]").get_by_role("button", name="Seti sil").click()
    sayfa.wait_for_selector("text=Henüz set yok", timeout=15000)


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
    for etiket, isaret in (("Setler", "Setler"),
                           ("Bildirimler", "Bildirim"),
                           ("Ayarlar", "Ayarlar"),
                           ("Panel", "Takip listem")):
        sayfa.get_by_role("link", name=etiket).click()
        sayfa.wait_for_selector(f"text={isaret}", timeout=15000)


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

    # Yalnızca TEK izlemenin detayı; liste ucu (`/api/izlemeler`) hariç.
    s.route(lambda u: "/api/izlemeler/" in u, islemci)


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

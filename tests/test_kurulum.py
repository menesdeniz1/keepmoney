"""`betikler/kurulum.py` ve kök dizindeki `.bat` dosyalarının testi.

NEDEN TEST EDİLİYOR: kurulum betiği, kullanıcının ürünle ilk teması. Bozuksa
ürün "çalışmıyor" demektir ve bunu ancak kullanıcı fark eder. Ayrıca betikler
test edilmediği için sessizce çürür: bir dosya adı değişince
`python betikler/...` yalnızca biri elle çalıştırdığında patlar.

`.bat` dosyalarının KENDİSİ test edilemez (cmd.exe gerektirir, CI Linux'ta
koşuyor) — bu yüzden mantık Python tarafında duruyor ve buradaki `.bat`
testleri yalnızca DEĞİŞMEZLERİ koruyor: `cd /d "%~dp0"` ilk satır mı, sanal
ortam etkinleştirilmeye çalışılıyor mu, dosya ASCII mi. Üçü de gerçek
kullanımda yaşanmış arızalar.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
BETIK = KOK / "betikler" / "kurulum.py"


def _betigi_yukle():
    """Betik paket içinde değil; dosya yolundan modül olarak yüklenir
    (test_kaynak_dene.py ile aynı yaklaşım)."""
    spec = importlib.util.spec_from_file_location("kurulum", BETIK)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["kurulum"] = modul
    spec.loader.exec_module(modul)                       # type: ignore[union-attr]
    return modul


ku = _betigi_yukle()


# ── Python sürümü ─────────────────────────────────────────────────


def test_eski_python_sebebi_soyler():
    sorun = ku.python_surumu_sorunu((3, 9, 7))
    assert sorun is not None
    assert "3.12" in sorun and "3.9.7" in sorun
    # Mesaj çalıştırılabilir olmalı: nereden indirileceğini söylüyor mu.
    assert "python.org" in sorun


def test_yeterli_python_sorun_cikarmaz():
    assert ku.python_surumu_sorunu((3, 12, 0)) is None
    assert ku.python_surumu_sorunu((3, 14, 1)) is None


# ── .env okuma ────────────────────────────────────────────────────


def test_env_degeri_satir_ici_yorumu_atar():
    # `.env.example` bu biçimi GERÇEKTEN kullanıyor; yorumu değere katmak
    # ayarı sessizce bozar.
    satirlar = ["KEEPMONEY_SMTP_PORT=587      # 465 → doğrudan SSL"]
    assert ku.env_degeri(satirlar, "KEEPMONEY_SMTP_PORT") == "587"


def test_env_degeri_tirnakli_ve_bosluklu():
    satirlar = ['  KEEPMONEY_EPOSTA_GONDEREN = "KeepMoney <a@b.c>"  ']
    assert ku.env_degeri(satirlar, "KEEPMONEY_EPOSTA_GONDEREN") == "KeepMoney <a@b.c>"


def test_env_degeri_yoksa_none():
    assert ku.env_degeri(["# yorum", "BASKA=1"], "KEEPMONEY_YOK") is None


def test_env_degeri_bos_deger():
    assert ku.env_degeri([f"{ku.ANAHTAR_ADI}="], ku.ANAHTAR_ADI) == ""


# ── JWT anahtarı ──────────────────────────────────────────────────


def test_uretilen_anahtar_politikadan_gecer():
    """Kurulumun ürettiği anahtar, uygulamanın kabul ettiği anahtar olmalı.

    K57: bir dönem belgelerin önerdiği komutla üretilen geçerli anahtarlar
    reddediliyordu. Kurulum betiği artık o anahtarı KENDİSİ üretiyor; iki
    tarafın ayrışması "kur.bat çalıştı ama uygulama açılmıyor" demek olurdu.
    """
    from keepmoney.ayarlar import anahtar_sorunu

    for _ in range(2000):
        assert anahtar_sorunu(ku.anahtar_uret()) is None


def test_anahtar_uzunlugu_ayarlarla_ayni():
    """Sabit iki yerde: ayarlar.py pydantic gerektirdiği için kurulum betiği
    onu import edemiyor. Ayrışmayı bu test yakalar."""
    from keepmoney.ayarlar import ONERILEN_ANAHTAR_BAYT

    assert ku.ANAHTAR_BAYT == ONERILEN_ANAHTAR_BAYT


def test_bos_anahtar_satiri_doldurulur():
    satirlar, sonuc = ku.anahtar_satirini_doldur([f"{ku.ANAHTAR_ADI}=", "X=1"], "abc")
    assert sonuc == "yazildi"
    assert satirlar[0] == f"{ku.ANAHTAR_ADI}=abc"
    assert satirlar[1] == "X=1"


def test_var_olan_anahtarin_uzerine_yazilmaz():
    """kur.bat onarım için tekrar tekrar çalıştırılabilir olmalı. Anahtarı
    değiştirmek, dağıtılmış bütün oturumları bir anda düşürürdü."""
    onceki = [f"{ku.ANAHTAR_ADI}=eskianahtar"]
    satirlar, sonuc = ku.anahtar_satirini_doldur(onceki, "yenisi")
    assert sonuc == "zaten_var"
    assert satirlar == onceki


def test_anahtar_satiri_hic_yoksa_eklenir():
    satirlar, sonuc = ku.anahtar_satirini_doldur(["X=1"], "abc")
    assert sonuc == "eklendi"
    assert satirlar[-1] == f"{ku.ANAHTAR_ADI}=abc"


def _ornek_env_yaz(kok: pathlib.Path) -> None:
    (kok / ".env.example").write_text(
        "KEEPMONEY_ORTAM=gelistirme\n"
        f"{ku.ANAHTAR_ADI}=\n"
        "KEEPMONEY_SMTP_PORT=587   # yorum\n",
        encoding="utf-8")


def test_env_hazirla_olusturur_ve_anahtar_yazar(tmp_path):
    _ornek_env_yaz(tmp_path)
    durum = ku.env_hazirla(tmp_path)
    assert durum == "olusturuldu+yazildi"

    satirlar = (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
    anahtar = ku.env_degeri(satirlar, ku.ANAHTAR_ADI)
    from keepmoney.ayarlar import anahtar_sorunu
    assert anahtar_sorunu(anahtar) is None
    # Diğer ayarlar korunmalı: örnek dosya kopyalanıyor, yeniden yazılmıyor.
    assert ku.env_degeri(satirlar, "KEEPMONEY_SMTP_PORT") == "587"


def test_env_hazirla_ikinci_calistirmada_dokunmaz(tmp_path):
    _ornek_env_yaz(tmp_path)
    ku.env_hazirla(tmp_path)
    once = (tmp_path / ".env").read_text(encoding="utf-8")

    assert ku.env_hazirla(tmp_path) == "zaten_var"
    assert (tmp_path / ".env").read_text(encoding="utf-8") == once


def test_env_ornegi_de_yoksa_calistirilabilir_hata(tmp_path):
    with pytest.raises(ku.KurulumHatasi) as hata:
        ku.env_hazirla(tmp_path)
    assert "git clone" in hata.value.cozum


# ── Arayüz derlemesi ──────────────────────────────────────────────


def test_npm_ci_node_modules_yoksa_gerekli(tmp_path):
    assert ku.npm_kurulum_gerekli_mi(tmp_path / "yok", tmp_path / "lock.json")


def test_npm_ci_kilit_yeniyse_gerekli(tmp_path):
    nm = tmp_path / "node_modules"
    nm.mkdir()
    kilit = tmp_path / "package-lock.json"
    kilit.write_text("{}", encoding="utf-8")
    os.utime(nm, (1_000_000, 1_000_000))
    os.utime(kilit, (2_000_000, 2_000_000))
    assert ku.npm_kurulum_gerekli_mi(nm, kilit)


def test_npm_ci_guncelse_atlanir(tmp_path):
    """`npm ci` node_modules'ü silip baştan kuruyor — her kurulumda dakikalar.
    Kilit eskiyse atlanabilir."""
    nm = tmp_path / "node_modules"
    nm.mkdir()
    kilit = tmp_path / "package-lock.json"
    kilit.write_text("{}", encoding="utf-8")
    os.utime(kilit, (1_000_000, 1_000_000))
    os.utime(nm, (2_000_000, 2_000_000))
    assert not ku.npm_kurulum_gerekli_mi(nm, kilit)


def _derleme_yap(dist: pathlib.Path, varlik: str) -> None:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets" / varlik).write_text("//", encoding="utf-8")


def test_arayuz_kopyalanirken_eski_derleme_temizlenir(tmp_path):
    """Üzerine kopyalamak eski `sw.js` ve hash'li varlıkları bırakır; tarayıcı
    eski sürümü sunmaya devam eder ve 'derledim ama değişmedi' denir."""
    dist, hedef = tmp_path / "dist", tmp_path / "statik"
    _derleme_yap(dist, "yeni-a1b2.js")
    _derleme_yap(hedef, "eski-9z8y.js")

    ku.arayuzu_kopyala(dist, hedef)

    assert (hedef / "assets" / "yeni-a1b2.js").is_file()
    assert not (hedef / "assets" / "eski-9z8y.js").exists()


def test_arayuz_kopyalama_tanimadigi_dizini_silmez(tmp_path):
    """Yanlış dizini silmek geri alınamaz; index.html yoksa dokunmuyoruz."""
    dist, hedef = tmp_path / "dist", tmp_path / "statik"
    _derleme_yap(dist, "a.js")
    hedef.mkdir()
    (hedef / "onemli.txt").write_text("veri", encoding="utf-8")

    with pytest.raises(ku.KurulumHatasi):
        ku.arayuzu_kopyala(dist, hedef)
    assert (hedef / "onemli.txt").is_file()


def test_derleme_yoksa_calistirilabilir_hata(tmp_path):
    with pytest.raises(ku.KurulumHatasi) as hata:
        ku.arayuzu_kopyala(tmp_path / "dist", tmp_path / "statik")
    assert "npm run build" in hata.value.cozum


# ── Ortam kontrolleri ─────────────────────────────────────────────


def test_env_kontrolu_dosya_yoksa_uyarir(tmp_path):
    k = ku._k_env(tmp_path)
    assert not k.tamam
    assert k.cozum


def test_env_kontrolu_zayif_anahtari_yakalar(tmp_path):
    """Politika `ayarlar.py`de tekil (K57); kurulum onu ÇAĞIRIYOR, kopyalamıyor.
    Amaç, uygulamanın açılışta reddedeceği anahtarı önceden söylemek."""
    (tmp_path / ".env").write_text(
        f"{ku.ANAHTAR_ADI}=changeme-changeme-changeme-changeme-1234\n",
        encoding="utf-8")
    k = ku._k_env(tmp_path)
    assert not k.tamam
    assert "changeme" in k.detay


def test_env_kontrolu_gecerli_anahtari_gecirir(tmp_path):
    (tmp_path / ".env").write_text(f"{ku.ANAHTAR_ADI}={ku.anahtar_uret()}\n",
                                   encoding="utf-8")
    assert ku._k_env(tmp_path).tamam


def test_arayuz_kontrolu_statik_yoksa_uyarir(tmp_path):
    k = ku._k_arayuz(tmp_path)
    assert not k.tamam
    # API arayüzü mount etmezse tarayıcıda 404 açılırdı; çözüm söylenmeli.
    assert "kur.bat" in k.cozum


def test_arayuz_kontrolu_derlenmisi_gorur(tmp_path):
    (tmp_path / "statik").mkdir()
    (tmp_path / "statik" / "index.html").write_text("<html>", encoding="utf-8")
    assert ku._k_arayuz(tmp_path).tamam


def test_saat_dilimi_kontrolu_gecer():
    """Windows'ta sistem tz veritabanı yok; `tzdata` eksikse uygulama HİÇ
    açılmaz. Kontrol paketin varlığına değil ZoneInfo'nun açılmasına bakmalı."""
    assert ku._k_saat_dilimi().tamam


def test_paket_kontrolu_gecer():
    """Testler sanal ortamda koşuyor; bütün paketler kurulu olmalı."""
    k = ku._k_paketler()
    assert k.tamam, k.detay


def test_kontrol_listesi_eksiksiz(monkeypatch):
    # Tarayıcı kontrolü gerçek playwright sürücüsünü başlatıyor (~1 sn);
    # burada ölçülen şey listenin kendisi.
    monkeypatch.setattr(ku, "_k_tarayici_motoru",
                        lambda: ku.Kontrol("tarayıcı motoru", True))
    adlar = [k.ad for k in ku.kontrolleri_calistir(KOK)]
    assert adlar == ["python paketleri", "saat dilimi", ".env",
                     "veritabanı şeması", "tarayıcı motoru", "arayüz"]


def test_rapor_eksikte_cozumu_basar(capsys):
    tamam = ku.raporla([
        ku.Kontrol("bir", True, "iyi"),
        ku.Kontrol("iki", False, "bozuk", "sunu calistir"),
    ])
    cikti = capsys.readouterr().out
    assert not tamam
    assert "sunu calistir" in cikti


def test_rapor_hepsi_tamamsa_dogru_doner():
    assert ku.raporla([ku.Kontrol("bir", True), ku.Kontrol("iki", True)])


# ── Süreç kaydı ───────────────────────────────────────────────────


def test_kayit_yaz_oku(tmp_path):
    ku.kayit_yaz([{"ad": "api", "pid": 42, "imaj": "python.exe"}], tmp_path)
    kayit = ku.kayit_oku(tmp_path)
    assert kayit["surecler"][0]["pid"] == 42


def test_bozuk_kayit_cokme_yerine_none(tmp_path):
    yol = ku.kayit_yolu(tmp_path)
    yol.parent.mkdir(parents=True)
    yol.write_text("{bozuk", encoding="utf-8")
    assert ku.kayit_oku(tmp_path) is None


def test_yeniden_baslatilmis_makinede_kayit_bayat():
    """PID'ler yeniden kullanılır. Makine yeniden başlatıldıysa kayıttaki
    numara BAŞKA bir sürecin olabilir; yanlış süreci öldürmek, hiçbir şey
    öldürmemekten çok daha kötüdür."""
    assert not ku.kayit_gecerli_mi(1_000_000.0, 1_090_000.0)


def test_ayni_oturumda_kayit_gecerli():
    # Sayaç çözünürlüğü ve askıya alma küçük kaymalar üretir; tolerans onun için.
    assert ku.kayit_gecerli_mi(1_000_000.0, 1_000_030.0)


def test_acilis_bilinmiyorsa_kayit_gecerli_sayilir():
    """Açılış anı okunamayan bir platformda kaydı çöpe atmak, kullanıcıyı
    süreçleri elle kapatmaya mecbur bırakırdı; karar imaj adı kontrolüne kalır."""
    assert ku.kayit_gecerli_mi(0.0, 1_000_000.0)
    assert ku.kayit_gecerli_mi(1_000_000.0, 0.0)


def test_acilis_ani_makul():
    """Açılış anı geçmişte ve makul bir aralıkta olmalı (0 = bilinmiyor)."""
    import time as _t
    deger = ku.acilis_ani()
    assert deger == 0.0 or 0 < deger <= _t.time()


def test_tasklist_ayristirici_csv_satirini_okur():
    cikti = '"python.exe","1234","Console","1","24.000 K"\n'
    assert ku.tasklist_imaji(cikti) == "python.exe"


def test_tasklist_ayristirici_bulunamadi_satirini_ayirir():
    """Eşleşme olmayınca tasklist CSV değil bilgi satırı basıyor; onu imaj
    adı sanmak, ölü bir PID'i yaşıyor göstermek olurdu."""
    assert ku.tasklist_imaji(
        "INFO: No tasks are running which match the specified criteria.") is None


def test_kendi_surecimiz_yasiyor():
    assert ku.surec_yasiyor_mu(os.getpid(), pathlib.Path(sys.executable).name)


def test_gecersiz_pid_yasamiyor():
    assert not ku.surec_yasiyor_mu(0)


@pytest.mark.skipif(os.name != "nt", reason="imaj adı kontrolü Windows'a özgü")
def test_imaj_adi_uymayan_pid_bizim_degil():
    """PID yeniden kullanımına karşı ikinci savunma: numara yaşıyor olabilir
    ama bizim python'umuz değilse ona dokunulmaz."""
    assert not ku.surec_yasiyor_mu(os.getpid(), "kesinlikle-baska.exe")


def test_dur_kayit_yokken_sorun_cikarmaz(tmp_path, capsys):
    assert ku.komut_dur(tmp_path) == 0
    assert "kayd" in capsys.readouterr().out.lower()


def test_dur_olu_pidlere_dokunmaz_ve_kaydi_siler(tmp_path, capsys):
    ku.kayit_yaz([{"ad": "api", "pid": 0, "imaj": "python.exe"}], tmp_path)
    assert ku.komut_dur(tmp_path) == 0
    assert not ku.kayit_yolu(tmp_path).exists()
    assert "0 süreç kapatıldı" in capsys.readouterr().out


# ── Ağ yardımcıları ───────────────────────────────────────────────


def test_dinlenen_port_dolu_gorunur():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((ku.API_HOST, 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert not ku.port_bos_mu(port)
    assert ku.port_bos_mu(port)


class _Saglik(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"durum":"iyi"}')

    def log_message(self, *_):                           # sessiz
        return


@pytest.fixture
def saglik_sunucusu():
    sunucu = HTTPServer((ku.API_HOST, 0), _Saglik)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    yield f"http://{ku.API_HOST}:{sunucu.server_address[1]}/saglik"
    sunucu.shutdown()


def test_saglik_ucu_cevap_verince_hazir(saglik_sunucusu):
    assert ku.saglik_yanit_verdi_mi(saglik_sunucusu)


def test_kapali_ucta_hazir_degil():
    # Kapalı port: `basla` burada beklemeye devam eder, çökmez.
    assert not ku.saglik_yanit_verdi_mi("http://127.0.0.1:1/saglik", zaman_asimi=0.5)


# ── Komut satırı ──────────────────────────────────────────────────


def test_anahtar_komutu_gecerli_anahtar_basar(capsys):
    from keepmoney.ayarlar import anahtar_sorunu

    assert ku.main(["anahtar"]) == 0
    assert anahtar_sorunu(capsys.readouterr().out.strip()) is None


def test_komutsuz_cagri_yardim_ister():
    with pytest.raises(SystemExit):
        ku.main([])


# ── .bat değişmezleri ─────────────────────────────────────────────
#
# Bunlar biçim takıntısı değil; üçü de gerçek kullanımda yaşanmış arıza.

BATLAR = ("kur.bat", "basla.bat", "dur.bat")


def _bat_metni(ad: str) -> str:
    return (KOK / ad).read_bytes().decode("ascii")


def _bat_calisan_satirlar(ad: str) -> list[str]:
    """Yalnızca ÇALIŞAN satırlar. Yorumlar (REM) hariç: bu dosyalardaki
    yorumlar tam da kaçınılan tuzakları anlatıyor ve adlarını geçiriyor."""
    return [s.strip() for s in _bat_metni(ad).splitlines()
            if s.strip() and not s.strip().upper().startswith(("REM", "@ECHO"))]


@pytest.mark.parametrize("ad", BATLAR)
def test_bat_dosyalari_var(ad):
    assert (KOK / ad).is_file()


@pytest.mark.parametrize("ad", BATLAR)
def test_bat_ascii(ad):
    """cmd.exe bu dosyayı konsolun kod sayfasıyla okuyor (Türkçe Windows'ta
    cp857). UTF-8 Türkçe karakter hem bozuk görünür hem ayrıştırmayı bozabilir;
    Türkçe mesajların yeri Python tarafı."""
    _bat_metni(ad)              # ASCII değilse UnicodeDecodeError


@pytest.mark.parametrize("ad", BATLAR)
def test_bat_once_kendi_klasorune_gecer(ad):
    """Kullanıcının takıldığı yer tam olarak burasıydı: yeni pencere
    C:\\WINDOWS\\system32'de açıldı ve hiçbir göreli yol tutmadı."""
    assert _bat_calisan_satirlar(ad)[0].lower() == 'cd /d "%~dp0"'


@pytest.mark.parametrize("ad", BATLAR)
def test_bat_sanal_ortami_etkinlestirmeye_calismaz(ad):
    """`Activate.ps1` PowerShell çalıştırma politikasına takılıyor ve bu
    tuzağa iki kez düşüldü. python.exe tam yoluyla çağrılır."""
    assert not any("Activate" in s for s in _bat_calisan_satirlar(ad))


@pytest.mark.parametrize("ad", ("basla.bat", "dur.bat"))
def test_bat_venv_pythonunu_dogrudan_cagirir(ad):
    assert r".venv\Scripts\python.exe" in _bat_metni(ad)


def test_kur_bat_kurulum_betigini_cagirir():
    assert r"betikler\kurulum.py kur" in _bat_metni("kur.bat")


def test_dur_bat_pencere_basligiyla_oldurmez():
    """ÖLÇÜLDÜ: Windows 11'de konsol penceresinin sahibi WindowsTerminal.exe,
    yani `taskkill /FI "WINDOWTITLE eq KeepMoney API"` KeepMoney'i değil
    kullanıcının terminal uygulamasını kapatırdı. Süreçler PID ile izleniyor."""
    assert not any("WINDOWTITLE" in s.upper()
                   for s in _bat_calisan_satirlar("dur.bat"))


def test_kayit_dosyasi_gite_girmez():
    """PID kaydı `data/` altında: `.gitignore` orayı zaten dışlıyor."""
    assert ku.kayit_yolu(KOK).parent.name == "data"
    assert "data/" in (KOK / ".gitignore").read_text(encoding="utf-8")


def test_json_kaydi_okunabilir_bicimde(tmp_path):
    ku.kayit_yaz([{"ad": "tarayici", "pid": 7, "imaj": "python.exe"}], tmp_path)
    ham = ku.kayit_yolu(tmp_path).read_text(encoding="utf-8")
    # Elle bakılabilmeli: kullanıcı "hangi süreç" diye sorduğunda dosya cevap
    # verir. json.loads ile de okunmalı.
    assert "tarayici" in ham
    assert json.loads(ham)["surecler"][0]["pid"] == 7


def test_venv_yokken_basla_calistirilabilir_hata(tmp_path):
    """Betik elle çağrıldığında (ya da `.venv` silinmişse) çıplak
    FileNotFoundError yerine ne yapılacağını söyleyen mesaj görülmeli."""
    with pytest.raises(ku.KurulumHatasi) as hata:
        ku.komut_basla(tmp_path)
    assert "kur.bat" in hata.value.cozum


# ── macOS betikleri (.command) ────────────────────────────────────
#
# `.bat` tarafındaki değişmezlerin macOS karşılığı. Bu dosyalar Windows'ta
# yazılıp Mac'te çalıştırılacak; buradaki üç kural da o yolculukta bozulan
# şeyleri koruyor.

COMMANDLAR = ("kur.command", "basla.command", "dur.command")


def _kabuk_metni(ad: str) -> str:
    return (KOK / ad).read_text(encoding="utf-8")


@pytest.mark.parametrize("ad", COMMANDLAR)
def test_command_dosyalari_var(ad):
    assert (KOK / ad).is_file()


@pytest.mark.parametrize("ad", COMMANDLAR)
def test_command_shebang_ile_basliyor(ad):
    """Finder'dan çift tıklanınca hangi yorumlayıcıyla koşacağını söyleyen
    tek şey bu satır."""
    assert _kabuk_metni(ad).startswith("#!/bin/bash")


@pytest.mark.parametrize("ad", COMMANDLAR)
def test_command_kendi_klasorune_gecer(ad):
    """Finder'dan çift tıklanan betik EV DİZİNİNDE başlar, betiğin
    klasöründe değil — `.bat` tarafındaki `cd /d "%~dp0"` ile aynı tuzak."""
    satirlar = [s.strip() for s in _kabuk_metni(ad).splitlines()
                if s.strip() and not s.strip().startswith("#")]
    assert any(s.startswith('cd "$(dirname "$0")"') for s in satirlar[:3]), \
        "ilk çalışan satırlar arasında kendi klasörüne geçiş yok"


@pytest.mark.parametrize("ad", COMMANDLAR)
def test_command_lf_ile_saklanir(ad):
    """CRLF olursa macOS shebang'i okuyamaz: "bad interpreter: /bin/bash^M".
    `.gitattributes` bunu zorluyor; burada depodaki HÂLİ doğrulanıyor."""
    assert b"\r\n" not in (KOK / ad).read_bytes()


@pytest.mark.parametrize("ad", ("basla.command", "dur.command"))
def test_command_venv_pythonunu_dogrudan_cagirir(ad):
    """Sanal ortam etkinleştirilmez — `.bat` tarafındaki kuralın aynısı."""
    metin = _kabuk_metni(ad)
    assert ".venv/bin/python" in metin
    assert "activate" not in metin.lower()


def test_macos_servis_betigi_var_ve_lf():
    yol = KOK / "betikler" / "macos" / "kur-servis.sh"
    assert yol.is_file()
    assert b"\r\n" not in yol.read_bytes()
    metin = yol.read_text(encoding="utf-8")
    # Servisin varlık sebebi: çökerse kendi kendine kalkması.
    assert "KeepAlive" in metin
    assert "ThrottleInterval" in metin


# ── Telegram token doğrulama ──────────────────────────────────────


def test_token_yoksa_ne_yapilacagini_soyler(tmp_path, capsys):
    """Token boşken bot süreci açılıp hata verip kapanıyor ve launchd onu
    tekrar tekrar başlatıyor; kullanıcı yalnızca "bot cevap vermiyor" görür.
    Bu komut sebebi tek satırda söylemeli."""
    (tmp_path / ".env").write_text("KEEPMONEY_TELEGRAM_BOT_TOKEN=\n",
                                   encoding="utf-8")
    assert ku.komut_bot_dene(tmp_path) == 1
    cikti = capsys.readouterr().out
    assert "BOŞ" in cikti
    assert "BotFather" in cikti


def test_env_yoksa_calistirilabilir_hata(tmp_path):
    with pytest.raises(ku.KurulumHatasi) as hata:
        ku.komut_bot_dene(tmp_path)
    assert hata.value.cozum


def test_token_dogrulama_degeri_ekrana_basmaz(tmp_path, capsys, monkeypatch):
    """Token bir paroladır: doğrulama çıktısında GÖRÜNMEMELİ — terminal
    kaydı, ekran görüntüsü ve log dosyası hep sızma yoludur."""
    gizli = "123456789:AAHgizli-token-degeri-xyz"
    (tmp_path / ".env").write_text(
        f"KEEPMONEY_TELEGRAM_BOT_TOKEN={gizli}\n"
        "KEEPMONEY_TELEGRAM_BOT_ADI=deneme_bot\n", encoding="utf-8")

    class SahteYanit:
        status = 200

        def read(self):
            return b'{"ok":true,"result":{"username":"deneme_bot"}}'

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(ku.urllib.request, "urlopen",
                        lambda *a, **k: SahteYanit())
    assert ku.komut_bot_dene(tmp_path) == 0
    cikti = capsys.readouterr().out
    assert "deneme_bot" in cikti
    assert gizli not in cikti


def test_bot_adi_uyusmazsa_uyarir(tmp_path, capsys, monkeypatch):
    """Deep-link `.env`teki ada göre kuruluyor; yanlışsa "Telegram'a bağla"
    akışı SESSİZCE başka bir hesaba gider."""
    (tmp_path / ".env").write_text(
        "KEEPMONEY_TELEGRAM_BOT_TOKEN=123:ABC\n"
        "KEEPMONEY_TELEGRAM_BOT_ADI=yanlis_ad\n", encoding="utf-8")

    class SahteYanit:
        status = 200

        def read(self):
            return b'{"ok":true,"result":{"username":"gercek_bot"}}'

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(ku.urllib.request, "urlopen",
                        lambda *a, **k: SahteYanit())
    assert ku.komut_bot_dene(tmp_path) == 1
    cikti = capsys.readouterr().out
    assert "yanlis_ad" in cikti and "gercek_bot" in cikti


def test_token_yokken_bot_sureci_acilmaz(tmp_path):
    """Token yokken bot açılsaydı hata verip kapanır ve kullanıcıya "bir şey
    bozuk" gibi görünürdü."""
    (tmp_path / ".env").write_text("KEEPMONEY_TELEGRAM_BOT_TOKEN=\n",
                                   encoding="utf-8")
    assert ku._telegram_tokeni_var(tmp_path) is False


def test_token_varsa_bot_sureci_acilir(tmp_path):
    """Eskiden bot HİÇ açılmıyordu: token yazılıyor ama uyarılar telefona
    düşmüyordu — web'de birikiyorlardı."""
    (tmp_path / ".env").write_text("KEEPMONEY_TELEGRAM_BOT_TOKEN=123:ABC\n",
                                   encoding="utf-8")
    assert ku._telegram_tokeni_var(tmp_path) is True


def test_env_yokken_bot_sorulmaz(tmp_path):
    assert ku._telegram_tokeni_var(tmp_path) is False

"""Kapanış denetiminde TESTSİZ bulunan üç ucun testleri.

NASIL BULUNDU: OpenAPI şemasındaki 37 uç, test dosyalarının tamamına karşı
tarandı. Üçü hiçbir testte geçmiyordu:

    POST   /api/uyarilar/hepsi-okundu
    POST   /api/auth/telegram/baglanti
    DELETE /api/auth/telegram

Üçü de arayüzde KULLANILIYOR (Bildirimler sayfasındaki "hepsini okundu"
düğmesi, Ayarlar sayfasındaki Telegram bağlama/kaldırma) — yani "kullanılmayan
kod" değil, sınanmayan kod. BACKLOG §1'in kuralı ("yeni davranışın testi
yoksa task kapanmaz") bu üçünden önce yazılmıştı; boşluk kapanıyor.

Üçünün de ASIL riski aynı: hepsi kullanıcıya ÖZEL veri üzerinde toplu iş
yapıyor. `hepsi-okundu` bir `UPDATE ... WHERE` — süzgeci eksik olsa BAŞKA
kullanıcıların uyarılarını da okundu işaretlerdi ve kimse fark etmezdi.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from keepmoney.api.app import uygulama_olustur
from keepmoney.ayarlar import ayarlar
from keepmoney.db import get_db
from keepmoney.models import Alert, User


@pytest.fixture
def oturum_fabrikasi(motor):
    return sessionmaker(bind=motor)


@pytest.fixture
def istemci(oturum_fabrikasi):
    app = uygulama_olustur()

    def test_db():
        db = oturum_fabrikasi()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(oturum_fabrikasi):
    s = oturum_fabrikasi()
    yield s
    s.close()


def kayit_ol(istemci, eposta="a@ornek.com") -> dict:
    istemci.post("/api/auth/kayit",
                 json={"eposta": eposta, "parola": "parola1234"})
    y = istemci.post("/api/auth/giris",
                     json={"eposta": eposta, "parola": "parola1234"})
    return {"Authorization": f"Bearer {y.json()['erisim_tokeni']}"}


def uyari_ekle(db, eposta: str, adet: int) -> None:
    k = db.query(User).filter(User.email == eposta).one()
    for i in range(adet):
        db.add(Alert(user_id=k.id, tur="DIP", baslik=f"b{i}",
                     mesaj="m", okundu=False))
    db.commit()


# ═════════════ POST /api/uyarilar/hepsi-okundu ═════════════

def test_hepsi_okundu_kendi_uyarilarini_isaretliyor(istemci, db):
    b = kayit_ol(istemci, "a@ornek.com")
    uyari_ekle(db, "a@ornek.com", 3)

    y = istemci.post("/api/uyarilar/hepsi-okundu", headers=b)
    assert y.status_code == 200
    assert y.json()["isaretlenen"] == 3
    assert istemci.get("/api/uyarilar/sayi", headers=b).json()["okunmamis"] == 0


def test_hepsi_okundu_BASKASININ_uyarilarina_dokunmuyor(istemci, db):
    """ASIL RİSK. Toplu `UPDATE ... WHERE` süzgeci eksik olsa bütün
    kullanıcıların uyarıları okundu olurdu ve hiçbir hata çıkmazdı —
    kullanıcılar yalnızca bildirimlerinin "kendiliğinden okunduğunu"
    görürdü. Sessiz veri bozulmasının ders kitabı hâli."""
    a = kayit_ol(istemci, "a@ornek.com")
    b = kayit_ol(istemci, "b@ornek.com")
    uyari_ekle(db, "a@ornek.com", 2)
    uyari_ekle(db, "b@ornek.com", 4)

    y = istemci.post("/api/uyarilar/hepsi-okundu", headers=a)
    assert y.json()["isaretlenen"] == 2, "yalnızca A'nınkiler işaretlenmeli"
    assert istemci.get("/api/uyarilar/sayi", headers=b).json()["okunmamis"] == 4


def test_hepsi_okundu_okunmamis_yokken_sifir_donuyor(istemci, db):
    """Hata değil: işaretlenecek bir şey olmaması normal bir durum."""
    b = kayit_ol(istemci)
    y = istemci.post("/api/uyarilar/hepsi-okundu", headers=b)
    assert y.status_code == 200
    assert y.json()["isaretlenen"] == 0


def test_hepsi_okundu_zaten_okunmuslari_tekrar_saymiyor(istemci, db):
    b = kayit_ol(istemci)
    uyari_ekle(db, "a@ornek.com", 2)
    istemci.post("/api/uyarilar/hepsi-okundu", headers=b)
    assert istemci.post("/api/uyarilar/hepsi-okundu",
                        headers=b).json()["isaretlenen"] == 0


def test_hepsi_okundu_kimliksiz_401(istemci):
    assert istemci.post("/api/uyarilar/hepsi-okundu").status_code == 401


# ═════════════ Telegram bağlama / kaldırma ═════════════

def test_telegram_baglanti_bot_yapilandirilmamissa_503(istemci, monkeypatch):
    """Sessizce boş bir link dönmek yerine AÇIK hata. Bot token'ı yokken
    üretilen link zaten hiçbir yere gitmezdi."""
    monkeypatch.setenv("KEEPMONEY_TELEGRAM_BOT_TOKEN", "")
    ayarlar.cache_clear()
    b = kayit_ol(istemci)
    try:
        y = istemci.post("/api/auth/telegram/baglanti", headers=b)
        assert y.status_code == 503
    finally:
        ayarlar.cache_clear()


def test_telegram_baglanti_deep_link_uretiyor(istemci, db, monkeypatch):
    """Bağlantı BOT ADINDAN kuruluyor, token'dan değil — sabit yazılıyken
    başka adla kayıtlı botlarda deep-link yanlış hesaba gidiyordu."""
    monkeypatch.setenv("KEEPMONEY_TELEGRAM_BOT_TOKEN", "123:sahte-token")
    monkeypatch.setenv("KEEPMONEY_TELEGRAM_BOT_ADI", "BaskaBotAdi")
    ayarlar.cache_clear()
    b = kayit_ol(istemci)
    try:
        y = istemci.post("/api/auth/telegram/baglanti", headers=b)
        assert y.status_code == 200
        baglanti = y.json()["baglanti"]
        assert baglanti.startswith("https://t.me/BaskaBotAdi?start=")
        assert y.json()["gecerlilik_dk"] == ayarlar().telegram_baglama_omru_dk

        # Token DB'ye yazılmış ve linktekiyle aynı olmalı; yoksa bot
        # doğrulayamaz ve bağlama sessizce çalışmaz.
        k = db.query(User).filter(User.email == "a@ornek.com").one()
        assert k.telegram_token == baglanti.split("start=")[1]
        assert k.telegram_token_biter is not None
    finally:
        ayarlar.cache_clear()


def test_telegram_baglanti_her_cagrida_YENI_token(istemci, db, monkeypatch):
    """Eski link üretildikten sonra yenisi istenirse eskisi ölmeli."""
    monkeypatch.setenv("KEEPMONEY_TELEGRAM_BOT_TOKEN", "123:sahte-token")
    ayarlar.cache_clear()
    b = kayit_ol(istemci)
    try:
        bir = istemci.post("/api/auth/telegram/baglanti", headers=b).json()
        iki = istemci.post("/api/auth/telegram/baglanti", headers=b).json()
        assert bir["baglanti"] != iki["baglanti"]
        k = db.query(User).filter(User.email == "a@ornek.com").one()
        assert k.telegram_token == iki["baglanti"].split("start=")[1]
    finally:
        ayarlar.cache_clear()


def test_telegram_kaldirinca_chat_id_ve_token_siliniyor(istemci, db):
    """Yarım silme, botun yazmaya devam etmesi demektir: `chat_id` kalırsa
    kullanıcı "bağlantıyı kaldırdım" der ama bildirim gelmeye devam eder."""
    b = kayit_ol(istemci)
    k = db.query(User).filter(User.email == "a@ornek.com").one()
    k.telegram_chat_id = "999"
    k.telegram_token = "eski-token"
    db.commit()

    assert istemci.delete("/api/auth/telegram", headers=b).status_code == 204

    db.expire_all()
    k = db.query(User).filter(User.email == "a@ornek.com").one()
    assert k.telegram_chat_id is None
    assert k.telegram_token is None
    assert k.telegram_token_biter is None


def test_telegram_kaldirma_bagli_degilken_de_204(istemci):
    """Idempotent: iki kez kaldırmak hata vermemeli."""
    b = kayit_ol(istemci)
    assert istemci.delete("/api/auth/telegram", headers=b).status_code == 204
    assert istemci.delete("/api/auth/telegram", headers=b).status_code == 204


@pytest.mark.parametrize("yontem,yol", [
    ("POST", "/api/auth/telegram/baglanti"),
    ("DELETE", "/api/auth/telegram"),
])
def test_telegram_uclari_kimliksiz_401(istemci, yontem, yol):
    assert istemci.request(yontem, yol).status_code == 401

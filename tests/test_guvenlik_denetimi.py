"""Canlı kod denetiminde ÖLÇÜLEREK bulunan üç açığın testleri.

Üçü de "belgede doğru yazıyordu ama kod öyle davranmıyordu" türünden.
Her testin başındaki not, açığın nasıl ölçüldüğünü söylüyor — bu dosyanın
değeri, bir daha aynı yere düşülmemesi.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from keepmoney.api.app import uygulama_olustur
from keepmoney.ayarlar import ayarlar
from keepmoney.db import get_db
from keepmoney.models import User
from keepmoney.servisler import kullanici as ksvc


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


@pytest.fixture
def ayar_sifirla():
    """`ayarlar()` lru_cache'li; test içinde değiştirilen ortam değişkeni
    ancak önbellek temizlenirse görülür."""
    ayarlar.cache_clear()
    yield
    ayarlar.cache_clear()


def kayit_ol(istemci, eposta="a@ornek.com", parola="parola1234") -> dict:
    istemci.post("/api/auth/kayit", json={"eposta": eposta, "parola": parola})
    y = istemci.post("/api/auth/giris",
                     json={"eposta": eposta, "parola": parola})
    return {"Authorization": f"Bearer {y.json()['erisim_tokeni']}"}


# ══════════ 1. X-Forwarded-For ile hız sınırı atlatma ══════════
#
# ÖLÇÜLDÜ (düzeltmeden önce): her istekte farklı bir XFF başlığıyla 40
# başarısız giriş denemesinin 40'ı da 401 döndü, tek bir 429 çıkmadı —
# limit 8 iken. `istemci_ip` başlığı KOŞULSUZ kullanıyordu, oysa başlığı
# istemcinin kendisi yazabilir. `compose.yaml` de konteynerin 8000'ini
# doğrudan yayınlıyor: "önünde başlığı ezen bir vekil var" varsayımı
# hiçbir yerde kurulu değildi.

def test_sahte_xff_hiz_sinirini_atlatamiyor(istemci):
    """Asıl regresyon testi: vekil TANIMLI DEĞİLKEN başlık yok sayılmalı."""
    istemci.post("/api/auth/kayit",
                 json={"eposta": "kurban@ornek.com", "parola": "parola1234"})

    kodlar = []
    for i in range(20):
        y = istemci.post("/api/auth/giris",
                         json={"eposta": "kurban@ornek.com",
                               "parola": f"yanlis{i}"},
                         headers={"X-Forwarded-For": f"10.0.{i // 256}.{i % 256}"})
        kodlar.append(y.status_code)

    assert 429 in kodlar, (
        "sahte X-Forwarded-For ile hız sınırı atlatılabiliyor: "
        f"{kodlar.count(401)} deneme 401 döndü, hiç 429 yok")


def test_vekil_tanimsizken_xff_yok_sayiliyor(istemci):
    """Aynı kullanıcı, farklı XFF: hepsi AYNI kovaya düşmeli."""
    from keepmoney.api.koruma import sinirlayicilar

    istemci.post("/api/auth/kayit",
                 json={"eposta": "k2@ornek.com", "parola": "parola1234"})
    for i in range(ayarlar().giris_limiti):
        istemci.post("/api/auth/giris",
                     json={"eposta": "k2@ornek.com", "parola": f"x{i}"},
                     headers={"X-Forwarded-For": f"203.0.113.{i}"})

    y = istemci.post("/api/auth/giris",
                     json={"eposta": "k2@ornek.com", "parola": "baska"},
                     headers={"X-Forwarded-For": "198.51.100.7"})
    assert y.status_code == 429
    sinirlayicilar.sifirla()


def test_guvenilen_vekil_arkasinda_xff_kullaniliyor(monkeypatch, ayar_sifirla):
    """Ters vekil arkasında başlık GEREKLİ: kullanılmazsa tüm istekler
    vekilin IP'sinden geliyormuş gibi görünür ve IP başına sayan limitler
    (kayıt) tüm kullanıcılar için tek kovaya düşer."""
    from starlette.datastructures import Headers

    from keepmoney.api.koruma import istemci_ip

    monkeypatch.setenv("KEEPMONEY_GUVENILEN_VEKILLER", "10.0.0.0/8")
    ayarlar.cache_clear()

    class SahteIstek:
        def __init__(self, es, xff):
            self.client = type("C", (), {"host": es})()
            self.headers = Headers({"x-forwarded-for": xff} if xff else {})

    # Vekil güvenilir → zincirdeki gerçek istemci alınır.
    assert istemci_ip(SahteIstek("10.0.0.1", "203.0.113.9")) == "203.0.113.9"
    # Vekil güvenilir DEĞİL → başlık yok sayılır, bağlanan adres kullanılır.
    assert istemci_ip(SahteIstek("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_xff_zinciri_SAGDAN_yurunuyor(monkeypatch, ayar_sifirla):
    """Zincirin SOL ucunu istemci uydurabilir; sağ uç bizim vekilimizin
    YAZDIĞI değerdir. Soldan almak, atlatmayı geri getirirdi."""
    from starlette.datastructures import Headers

    from keepmoney.api.koruma import istemci_ip

    monkeypatch.setenv("KEEPMONEY_GUVENILEN_VEKILLER", "10.0.0.0/8")
    ayarlar.cache_clear()

    class SahteIstek:
        client = type("C", (), {"host": "10.0.0.1"})()
        # Saldırgan "1.1.1.1" yazdı; vekilimiz gerçek adresi (203.0.113.9)
        # sağa ekledi. Doğru cevap sağdaki güvenilmeyen ilk adres.
        headers = Headers({"x-forwarded-for": "1.1.1.1, 203.0.113.9, 10.0.0.2"})

    assert istemci_ip(SahteIstek()) == "203.0.113.9"


def test_bozuk_vekil_tanimi_acilista_patliyor(monkeypatch, ayar_sifirla):
    """Sessizce atlansaydı: limit çalışıyor görünür, yanlış anahtarla sayar."""
    monkeypatch.setenv("KEEPMONEY_GUVENILEN_VEKILLER", "10.0.0.0/33")
    ayarlar.cache_clear()
    with pytest.raises(RuntimeError, match="GUVENILEN_VEKILLER"):
        ayarlar()


# ══════════ 2. Parola değişince oturumlar düşmüyordu ══════════
#
# ÖLÇÜLDÜ (düzeltmeden önce): parola sıfırlandıktan sonra ESKİ token
# `/api/auth/ben`den 200 almaya devam ediyordu. Yani hesabı ele geçirilmiş
# kullanıcının parolasını değiştirmesi saldırganı DIŞARI ATMIYORDU — oysa
# insanların bu işlemden beklediği tam olarak budur (OWASP ASVS 3.3.x).

def test_parola_sifirlaninca_eski_oturum_dusuyor(istemci, db):
    basliklar = kayit_ol(istemci, "kurban@ornek.com", "eskiparola1")
    assert istemci.get("/api/auth/ben", headers=basliklar).status_code == 200

    sonuc = ksvc.parola_sifirlama_iste(db, "kurban@ornek.com")
    assert sonuc is not None
    ksvc.parola_sifirla(db, sonuc[1], "yeniparola9")

    y = istemci.get("/api/auth/ben", headers=basliklar)
    assert y.status_code == 401, (
        "parola değişti ama eski token hâlâ geçerli — sıfırlama saldırganı "
        "dışarı atmıyor")


def test_sifirlamadan_sonra_verilen_oturum_calisiyor(istemci, db):
    """Sayacın KENDİ kullanıcısını dışarı atmaması da bir kabul ölçütü:
    sıfırlama ucu, sayaç artırıldıktan SONRA yeni sürümle token üretmeli.
    Eski sürümle üretseydi kullanıcı parolasını değiştirir değiştirmez
    kendi oturumu düşerdi."""
    istemci.post("/api/auth/kayit",
                 json={"eposta": "k3@ornek.com", "parola": "eskiparola1"})
    sonuc = ksvc.parola_sifirlama_iste(db, "k3@ornek.com")
    assert sonuc is not None

    y = istemci.post("/api/auth/parola/sifirla",
                     json={"token": sonuc[1], "parola": "yeniparola9"})
    assert y.status_code == 200
    # Uç çerezi kurdu; TestClient onu taşır.
    assert istemci.get("/api/auth/ben").status_code == 200


def test_parola_degismemis_kullanicinin_oturumu_dusmuyor(istemci):
    """Sayaç 0 = "hiç parola değiştirilmemiş". Göç kimsenin oturumunu
    kapatmamalı."""
    basliklar = kayit_ol(istemci, "k4@ornek.com")
    assert istemci.get("/api/auth/ben", headers=basliklar).status_code == 200


def test_ver_tasimayan_eski_token_gocten_sonra_calisiyor(istemci, db):
    """Bu değişiklik dağıtıldığı gün kimsenin oturumu düşmemeli: `ver`
    taşımayan token 0 sayılır ve sayaç da 0'dan başlar."""
    import jwt as pyjwt

    kayit_ol(istemci, "k5@ornek.com")
    k = db.query(User).filter(User.email == "k5@ornek.com").one()
    a = ayarlar()
    from datetime import timedelta

    from keepmoney.zaman import utc_simdi
    eski = pyjwt.encode(
        {"sub": str(k.id), "iat": utc_simdi(),
         "exp": utc_simdi() + timedelta(days=1)},
        a.jwt_gizli_anahtar, algorithm=a.jwt_algoritma)
    y = istemci.get("/api/auth/ben",
                    headers={"Authorization": f"Bearer {eski}"})
    assert y.status_code == 200


def test_ver_tasimayan_token_sifirlamadan_sonra_dusuyor(istemci, db):
    """Ama muafiyet KALICI DEĞİL: ilk sıfırlamada sayaç 1 olur ve `ver`
    taşımayan token tam o anda geçersizleşir. Aksi hâlde 0-muafiyeti
    kontrolü baştan etkisiz kılardı."""
    from datetime import timedelta

    import jwt as pyjwt

    from keepmoney.zaman import utc_simdi

    kayit_ol(istemci, "k6@ornek.com")
    k = db.query(User).filter(User.email == "k6@ornek.com").one()
    a = ayarlar()
    eski = pyjwt.encode(
        {"sub": str(k.id), "iat": utc_simdi(),
         "exp": utc_simdi() + timedelta(days=1)},
        a.jwt_gizli_anahtar, algorithm=a.jwt_algoritma)
    assert istemci.get("/api/auth/ben",
                       headers={"Authorization": f"Bearer {eski}"}).status_code == 200

    sonuc = ksvc.parola_sifirlama_iste(db, "k6@ornek.com")
    assert sonuc is not None
    ksvc.parola_sifirla(db, sonuc[1], "yeniparola9")

    assert istemci.get("/api/auth/ben",
                       headers={"Authorization": f"Bearer {eski}"}).status_code == 401


def test_iki_kez_sifirlama_ilk_sifirlamanin_oturumunu_da_dusuruyor(istemci, db):
    """Sayaç monoton artıyor: her sıfırlama bir öncekinin verdiği oturumu da
    kapatır. Zaman damgası yaklaşımında bu, saat çözünürlüğüne bağlıydı."""
    istemci.post("/api/auth/kayit",
                 json={"eposta": "k7@ornek.com", "parola": "parola1234"})
    for _ in range(2):
        sonuc = ksvc.parola_sifirlama_iste(db, "k7@ornek.com")
        k = ksvc.parola_sifirla(db, sonuc[1], "parola1234")
    assert k.oturum_surumu == 2


# ══════════ 3. /metrics kimliksiz açıktı ══════════
#
# ÖLÇÜLDÜ (düzeltmeden önce): token'sız `GET /metrics` 200 döndü. Sızan şey
# parola değil ama keşif bilgisi: hangi uçlar var, hangi hızda çağrılıyor,
# hata oranı, hangi mağazalardan fiyat okunabiliyor.

def test_gelistirmede_metrics_acik(istemci):
    """Yerelde pano kurmak kolay kalsın — ortam 'test'."""
    assert istemci.get("/metrics").status_code == 200


def test_token_tanimliysa_metrics_token_istiyor(istemci, monkeypatch,
                                                ayar_sifirla):
    monkeypatch.setenv("KEEPMONEY_METRIK_TOKENI", "m-gizli-token-123456")
    ayarlar.cache_clear()

    assert istemci.get("/metrics").status_code == 404
    assert istemci.get("/metrics",
                       headers={"Authorization": "Bearer yanlis"}
                       ).status_code == 404
    y = istemci.get("/metrics",
                    headers={"Authorization": "Bearer m-gizli-token-123456"})
    assert y.status_code == 200
    assert b"keepmoney_http_istek_toplam" in y.content


def test_uretimde_tokensiz_metrics_kapali(istemci, monkeypatch, ayar_sifirla):
    """Açık bırakmaktansa kapalı. Operatör açılışta uyarılıyor."""
    monkeypatch.setenv("KEEPMONEY_ORTAM", "uretim")
    monkeypatch.setenv("KEEPMONEY_METRIK_TOKENI", "")
    monkeypatch.setenv("KEEPMONEY_CORS_KAYNAKLARI", "https://ornek.test")
    ayarlar.cache_clear()

    assert istemci.get("/metrics").status_code == 404


def test_saglik_ucu_her_zaman_acik(istemci):
    """Yük dengeleyici token taşımaz; sağlık ucu korumaya girmemeli."""
    assert istemci.get("/saglik").status_code == 200

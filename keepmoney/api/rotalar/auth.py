"""Kimlik rotaları."""
from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Request,
    Response,
    status,
)

from ... import semalar
from ...ayarlar import ayarlar
from ...eposta import postaci
from ...guvenlik import jwt_uret
from ...servisler import kullanici as svc
from ..deps import DB, Kullanici, oturum_cerezi_sil, oturum_cerezi_yaz
from ..koruma import (
    giris_basarili,
    giris_basarisiz,
    giris_denemesi_kontrol,
    kayit_kontrol,
    sifirlama_kontrol,
)

router = APIRouter(prefix="/api/auth", tags=["kimlik"])


def _yanit(k) -> dict:
    return {
        "id": k.id,
        "email": k.email,
        "telegram_bagli": bool(k.telegram_chat_id),
        "eposta_dogrulandi": bool(k.eposta_dogrulandi),
        "created_at": k.created_at,
    }


@router.post("/kayit", response_model=semalar.KullaniciYaniti,
             status_code=status.HTTP_201_CREATED)
def kayit(istek: semalar.KayitIstegi, http: Request, arka: BackgroundTasks,
          db: DB):
    # Hesap açma spam'i: tek IP'den saatte sınırlı sayıda kayıt.
    kayit_kontrol(http)
    try:
        k = svc.kayit(db, istek.eposta, istek.parola)
    except svc.KimlikHatasi as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e

    # Doğrulama bağlantısı ARKA PLANDA gider: SMTP yavaşsa kullanıcı kayıt
    # ekranında beklemesin. E-posta ulaşmazsa yeniden istenebilir.
    token = svc.dogrulama_tokeni_uret(db, k)
    arka.add_task(_dogrulama_epostasi, k.email, token)
    return _yanit(k)


@router.post("/giris", response_model=semalar.TokenYaniti)
def giris(istek: semalar.GirisIstegi, http: Request, yanit: Response, db: DB):
    """Token'ı HEM httpOnly çerez olarak kurar HEM gövdede döner.

    Tarayıcı istemcisi gövdeyi yok sayar (token'a hiç dokunmaz); programatik
    istemciler gövdedeki token'ı Bearer olarak kullanır.
    """
    # Brute force freni — 401 dönmeden ÖNCE kontrol et.
    giris_denemesi_kontrol(http, istek.eposta)
    try:
        token = svc.giris(db, istek.eposta, istek.parola)
    except svc.KimlikHatasi as e:
        giris_basarisiz(http, istek.eposta)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, str(e),
            headers={"WWW-Authenticate": "Bearer"}) from e

    giris_basarili(http, istek.eposta)      # meşru kullanıcı cezalanmasın
    oturum_cerezi_yaz(yanit, token)
    return {"erisim_tokeni": token}


@router.post("/cikis", status_code=status.HTTP_204_NO_CONTENT)
def cikis(yanit: Response):
    """Çerezi siler. Token'ın kendisi süresi dolana kadar geçerli kalır —
    gerçek iptal için kara liste gerekir; kullanıcı sayısı anlamlı olunca
    eklenecek (şimdi kullanılmayan altyapı olurdu)."""
    oturum_cerezi_sil(yanit)


@router.get("/ben", response_model=semalar.KullaniciYaniti)
def ben(k: Kullanici):
    return _yanit(k)


@router.post("/telegram/baglanti", response_model=semalar.TelegramBaglamaYaniti)
def telegram_baglanti(k: Kullanici, db: DB):
    """Tek kullanımlık deep-link üretir. Kullanıcı chat ID kopyalamaz."""
    bot = ayarlar().telegram_bot_token
    if not bot:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Sunucuda Telegram botu yapılandırılmamış")
    # Token'ın ilk parçası bot kullanıcı adı değil, sayısal ID'dir; deep-link
    # için bot adı ayrı ayarlanmalı. Şimdilik ortam değişkeninden gelen adı
    # kullanmıyoruz — bot adı Faz 4'te bot modülüyle birlikte gelecek.
    baglanti, omur = svc.telegram_baglantisi(db, k, "KeepMoneyBot")
    return {"baglanti": baglanti, "gecerlilik_dk": omur}


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
def telegram_kaldir(k: Kullanici, db: DB):
    svc.telegram_kaldir(db, k)


# ─────────────────── e-posta gönderim yardımcıları ───────────────────
#
# Metinler burada, rotanın yanında: gönderilen içerik API sözleşmesinin
# parçasıdır ve değiştiğinde rotayla birlikte gözden geçirilmelidir.


def _dogrulama_epostasi(alici: str, token: str) -> None:
    a = ayarlar()
    baglanti = f"{a.site_adresi.rstrip('/')}/eposta-dogrula?token={token}"
    postaci().gonder(
        alici,
        "KeepMoney — e-posta adresini doğrula",
        f"Merhaba,\n\n"
        f"KeepMoney hesabını doğrulamak için:\n{baglanti}\n\n"
        f"Bağlantı {a.eposta_dogrulama_omru_saat} saat geçerli.\n"
        f"Bu hesabı sen açmadıysan bu e-postayı yok sayabilirsin.\n",
    )


def _sifirlama_epostasi(alici: str, token: str) -> None:
    a = ayarlar()
    baglanti = f"{a.site_adresi.rstrip('/')}/parola-sifirla?token={token}"
    postaci().gonder(
        alici,
        "KeepMoney — parola sıfırlama",
        f"Merhaba,\n\n"
        f"Parolanı sıfırlamak için:\n{baglanti}\n\n"
        f"Bağlantı {a.parola_sifirlama_omru_dk} dakika geçerli ve yalnızca "
        f"bir kez kullanılabilir.\n"
        f"Bu isteği sen yapmadıysan hiçbir şey yapmana gerek yok — parolan "
        f"değişmedi.\n",
    )


# ─────────────────── parola sıfırlama ───────────────────


@router.post("/parola/sifirlama-iste", status_code=status.HTTP_202_ACCEPTED)
def parola_sifirlama_iste(istek: semalar.ParolaSifirlamaIstegi,
                          http: Request, arka: BackgroundTasks, db: DB):
    """Sıfırlama bağlantısı gönderir.

    HESAP SAYIMI SIZMASIN: e-posta kayıtlı olsa da olmasa da AYNI cevap
    döner. Farklı cevap vermek, saldırgana hangi adreslerin sistemde
    olduğunu söyler ve o liste kimlik avı için doğrudan kullanılır.

    Hız sınırı ayrıca gerekli: bu uç kimlik doğrulaması istemiyor ve
    sınırsız bırakılırsa bir hesabın kutusuna e-posta bombardımanı
    yapılabilir.
    """
    sifirlama_kontrol(http, istek.eposta)
    sonuc = svc.parola_sifirlama_iste(db, istek.eposta)
    if sonuc is not None:
        k, token = sonuc
        arka.add_task(_sifirlama_epostasi, k.email, token)
    return {"durum": "Bu adres kayıtlıysa sıfırlama bağlantısı gönderildi"}


@router.post("/parola/sifirla", response_model=semalar.KullaniciYaniti)
def parola_sifirla(istek: semalar.ParolaSifirlamaUygulaIstegi,
                   yanit: Response, db: DB):
    """Token'ı harcar, parolayı değiştirir ve kullanıcıyı oturum açtırır."""
    try:
        k = svc.parola_sifirla(db, istek.token, istek.parola)
    except svc.KimlikHatasi as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    # Sıfırlamadan sonra doğrudan oturum: kullanıcı yeni parolayı bir daha
    # yazmak zorunda kalmasın.
    oturum_cerezi_yaz(yanit, jwt_uret(k.id))
    return _yanit(k)


# ─────────────────── e-posta doğrulama ───────────────────


@router.post("/eposta/dogrula", response_model=semalar.KullaniciYaniti)
def eposta_dogrula(istek: semalar.TokenIstegi, db: DB):
    try:
        return _yanit(svc.epostayi_dogrula(db, istek.token))
    except svc.KimlikHatasi as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.post("/eposta/dogrulama-gonder", status_code=status.HTTP_202_ACCEPTED)
def dogrulama_yeniden_gonder(k: Kullanici, arka: BackgroundTasks, db: DB):
    """Doğrulama e-postası ulaşmadıysa yeniden ister. Oturum gerektirir."""
    if k.eposta_dogrulandi:
        return {"durum": "Adres zaten doğrulanmış"}
    token = svc.dogrulama_tokeni_uret(db, k)
    arka.add_task(_dogrulama_epostasi, k.email, token)
    return {"durum": "Doğrulama bağlantısı gönderildi"}


# ─────────────────── hesap silme (KVKK) ───────────────────


@router.delete("/hesap", status_code=status.HTTP_204_NO_CONTENT)
def hesabi_sil(istek: semalar.HesapSilmeIstegi, yanit: Response,
               k: Kullanici, db: DB):
    """Hesabı ve kişisel verileri siler (KVKK/GDPR: silme hakkı).

    Küresel fiyat geçmişi SİLİNMEZ — kişisel veri değildir ve diğer
    kullanıcıların hafızasıdır (bkz. servis katmanı).
    """
    try:
        svc.hesabi_sil(db, k, istek.parola)
    except svc.KimlikHatasi as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e
    oturum_cerezi_sil(yanit)

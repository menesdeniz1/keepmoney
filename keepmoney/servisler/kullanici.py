"""Kimlik use-case'leri: kayıt, giriş, Telegram bağlama."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ayarlar import ayarlar
from ..guvenlik import (
    baglama_tokeni,
    jwt_uret,
    parola_dogrula,
    parola_hashle,
    tek_kullanimlik_token,
    token_eslesir_mi,
    token_hashle,
)
from ..models import User
from ..zaman import utc_simdi


class KimlikHatasi(Exception):
    pass


def _normalize(eposta: str) -> str:
    return eposta.strip().lower()


def eposta_ile(db: Session, eposta: str) -> User | None:
    # Normalleştirme TEK YERDE. Kayıt `.strip().lower()` uygularken arama
    # yalnızca `.lower()` uygulasaydı, boşluklu girilen bir e-postayla açılan
    # hesaba bir daha giriş yapılamazdı.
    return db.query(User).filter(User.email == _normalize(eposta)).one_or_none()


def kayit(db: Session, eposta: str, parola: str) -> User:
    eposta = _normalize(eposta)
    if eposta_ile(db, eposta) is not None:
        raise KimlikHatasi("Bu e-posta zaten kayıtlı")

    k = User(email=eposta, password_hash=parola_hashle(parola))
    db.add(k)
    try:
        db.commit()
    except IntegrityError as e:
        # Kontrol ile INSERT arasında aynı e-posta ile ikinci bir kayıt
        # gelebilir. Tekillik kısıtı veriyi korur; burada kullanıcıya 500
        # yerine anlamlı hata dönmesini sağlıyoruz.
        db.rollback()
        raise KimlikHatasi("Bu e-posta zaten kayıtlı") from e
    db.refresh(k)
    return k


def giris(db: Session, eposta: str, parola: str) -> str:
    """Başarılıysa JWT döner.

    Kullanıcı yoksa da parola yanlışsa da AYNI mesaj verilir — farklı mesaj,
    hangi e-postaların kayıtlı olduğunu sızdırır (kullanıcı numaralandırma).
    """
    k = eposta_ile(db, eposta)
    if k is None or not parola_dogrula(parola, k.password_hash):
        raise KimlikHatasi("E-posta veya parola hatalı")
    return jwt_uret(k.id, k.oturum_surumu or 0)


def telegram_baglantisi(db: Session, kullanici: User, bot_adi: str) -> tuple[str, int]:
    """Tek kullanımlık deep-link üretir: (baglanti, gecerlilik_dk).

    Kullanıcı hiçbir şey kopyalamaz; linke tıklar, bot `/start <token>` alır
    ve chat_id'yi sunucu tarafında doğrulayıp yazar (bkz. MIMARI K7).
    """
    a = ayarlar()
    token = baglama_tokeni()
    kullanici.telegram_token = token
    kullanici.telegram_token_biter = utc_simdi() + timedelta(
        minutes=a.telegram_baglama_omru_dk)
    db.commit()
    return f"https://t.me/{bot_adi}?start={token}", a.telegram_baglama_omru_dk


def telegram_dogrula(db: Session, token: str, chat_id: str) -> User | None:
    """Bot tarafı: token'ı harcayıp chat_id'yi hesaba yazar.

    None döner = token geçersiz/süresi dolmuş. Token TEK KULLANIMLIKTIR;
    doğrulandığı anda silinir.
    """
    k = db.query(User).filter(User.telegram_token == token).one_or_none()
    if k is None or not k.telegram_token_biter:
        return None
    if k.telegram_token_biter < utc_simdi():
        return None

    # Bu chat başka bir hesaba bağlıysa devral: kullanıcı hesap değiştirmiş
    # olabilir ve chat_id tekil olmak zorunda (bot gelen mesajı tek kullanıcıya
    # çözebilmeli).
    onceki = db.query(User).filter(
        User.telegram_chat_id == str(chat_id), User.id != k.id).all()
    for o in onceki:
        o.telegram_chat_id = None

    k.telegram_chat_id = str(chat_id)
    k.telegram_token = None
    k.telegram_token_biter = None
    db.commit()
    db.refresh(k)
    return k


def telegram_kaldir(db: Session, kullanici: User) -> None:
    kullanici.telegram_chat_id = None
    kullanici.telegram_token = None
    kullanici.telegram_token_biter = None
    db.commit()


def chat_id_ile(db: Session, chat_id: str) -> User | None:
    """Bot gelen mesajı hangi hesaba ait çözecek."""
    return db.query(User).filter(
        User.telegram_chat_id == str(chat_id)).one_or_none()


# ─────────────────── Parola sıfırlama ───────────────────
#
# GÜVENLİK İLKESİ — HESAP SAYIMI SIZMASIN: "bu e-posta kayıtlı değil" demek,
# saldırgana hangi adreslerin sistemde olduğunu söyler. Bu yüzden istek ucu
# HER ZAMAN aynı nötr cevabı döner; kullanıcı yoksa hiçbir şey yapılmaz.


def parola_sifirlama_iste(db: Session, eposta: str) -> tuple[User, str] | None:
    """Sıfırlama token'ı üretir. Kullanıcı yoksa None — çağıran YİNE de
    aynı nötr mesajı döndürür.

    Token ham hâliyle DÖNER (e-postaya konacak) ama veritabanına HASH'İ
    yazılır (bkz. guvenlik.token_hashle).
    """
    k = eposta_ile(db, eposta)
    if k is None:
        return None

    ham = tek_kullanimlik_token()
    k.parola_sifirlama_hash = token_hashle(ham)
    k.parola_sifirlama_biter = utc_simdi() + timedelta(
        minutes=ayarlar().parola_sifirlama_omru_dk)
    db.commit()
    return k, ham


def parola_sifirla(db: Session, token: str, yeni_parola: str) -> User:
    """Token'ı harcar ve parolayı değiştirir.

    Token TEK KULLANIMLIKTIR. Ayrıca parola değişince e-posta adresi de
    doğrulanmış sayılır: kullanıcı o kutuya erişebildiğini kanıtladı.
    """
    hash_ = token_hashle(token)
    k = (db.query(User)
         .filter(User.parola_sifirlama_hash == hash_)
         .one_or_none())
    if k is None or not k.parola_sifirlama_biter:
        raise KimlikHatasi("Bağlantı geçersiz ya da süresi dolmuş")
    if k.parola_sifirlama_biter < utc_simdi():
        raise KimlikHatasi("Bağlantı geçersiz ya da süresi dolmuş")
    if not token_eslesir_mi(token, k.parola_sifirlama_hash):
        raise KimlikHatasi("Bağlantı geçersiz ya da süresi dolmuş")

    k.password_hash = parola_hashle(yeni_parola)
    k.parola_sifirlama_hash = None
    k.parola_sifirlama_biter = None
    k.eposta_dogrulandi = True          # kutuya erişimi kanıtlandı
    # ESKİ OTURUMLARI DÜŞÜR. Bu satır olmadan parola değişse bile daha
    # önce verilmiş token'lar 7 gün boyunca çalışmaya devam ediyordu —
    # yani hesabı ele geçirilmiş kullanıcının parolasını değiştirmesi
    # saldırganı dışarı ATMIYORDU (ölçüldü). Sayacı artırmak, o kullanıcının
    # o ana kadarki BÜTÜN token'larını tek hamlede geçersiz kılar.
    k.oturum_surumu = (k.oturum_surumu or 0) + 1
    db.commit()
    db.refresh(k)
    return k


# ─────────────────── E-posta doğrulama ───────────────────


def dogrulama_tokeni_uret(db: Session, kullanici: User) -> str:
    ham = tek_kullanimlik_token()
    kullanici.eposta_dogrulama_hash = token_hashle(ham)
    kullanici.eposta_dogrulama_biter = utc_simdi() + timedelta(
        hours=ayarlar().eposta_dogrulama_omru_saat)
    db.commit()
    return ham


def epostayi_dogrula(db: Session, token: str) -> User:
    hash_ = token_hashle(token)
    k = (db.query(User)
         .filter(User.eposta_dogrulama_hash == hash_)
         .one_or_none())
    if (k is None or not k.eposta_dogrulama_biter
            or k.eposta_dogrulama_biter < utc_simdi()
            or not token_eslesir_mi(token, k.eposta_dogrulama_hash)):
        raise KimlikHatasi("Bağlantı geçersiz ya da süresi dolmuş")

    k.eposta_dogrulandi = True
    k.eposta_dogrulama_hash = None
    k.eposta_dogrulama_biter = None
    db.commit()
    db.refresh(k)
    return k


# ─────────────────── Hesap silme (KVKK) ───────────────────


def hesabi_sil(db: Session, kullanici: User, parola: str) -> None:
    """Hesabı ve KİŞİSEL verilerini siler.

    KVKK/GDPR gereği kullanıcı verisinin silinmesi bir HAKTIR; bu ucun
    olmaması ürünü yayına alınamaz yapıyordu.

    NE SİLİNİR: kullanıcı kaydı, izlemeleri, setleri, uyarıları — yani
    kişiye bağlanabilen her şey. Cascade `models.py`de tanımlı.

    NE SİLİNMEZ: küresel ürün ve fiyat geçmişi. Bunlar kişisel veri DEĞİL
    (bir ekran kartının dünkü fiyatı kimseye ait değildir) ve diğer
    kullanıcıların hafızasıdır. Silinmesi hem gereksiz hem zararlı olurdu.
    İzleyen sayacı düşürülür ki tarama önceliği doğru kalsın.

    Parola YENİDEN SORULUR: oturumu çalınmış birinin hesabı silmesini
    zorlaştırır ve yıkıcı işlemlerde niyeti teyit eder.
    """
    if not parola_dogrula(parola, kullanici.password_hash):
        raise KimlikHatasi("Parola hatalı")

    from ..models import Watch
    from .izleme import _izleyen_sayaci

    urun_idleri = [w.product_id for w in
                   db.query(Watch).filter(Watch.user_id == kullanici.id).all()]

    db.delete(kullanici)                # cascade: watches, sets
    db.flush()
    for urun_id in urun_idleri:
        _izleyen_sayaci(db, urun_id, -1)
    db.commit()

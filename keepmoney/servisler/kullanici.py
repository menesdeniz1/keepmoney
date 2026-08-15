"""Kimlik use-case'leri: kayıt, giriş, Telegram bağlama."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..ayarlar import ayarlar
from ..guvenlik import baglama_tokeni, jwt_uret, parola_dogrula, parola_hashle
from ..models import User
from ..zaman import utc_simdi


class KimlikHatasi(Exception):
    pass


def eposta_ile(db: Session, eposta: str) -> User | None:
    return db.query(User).filter(User.email == eposta.lower()).one_or_none()


def kayit(db: Session, eposta: str, parola: str) -> User:
    eposta = eposta.lower().strip()
    if eposta_ile(db, eposta) is not None:
        raise KimlikHatasi("Bu e-posta zaten kayıtlı")
    k = User(email=eposta, password_hash=parola_hashle(parola))
    db.add(k)
    db.commit()
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
    return jwt_uret(k.id)


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

"""Parola hash'leme, JWT ve Telegram bağlama token'ları.

Kripto ile ilgili HER ŞEY burada. Dağıtılmış kripto kodu, güvenlik açığının
en yaygın kaynağıdır — tek dosyada tutulunca denetlenebilir kalır.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

import bcrypt
import jwt

from .ayarlar import ayarlar
from .zaman import utc_simdi

# bcrypt 72 BAYT'tan sonrasını sessizce yok sayar — 73. karakterden itibaren
# farklı parolalar aynı hash'i üretir. Şema katmanı da sınırlıyor ama burada
# da açıkça reddediyoruz: sessiz kesme, güvenlik açığıdır.
MAKS_PAROLA_BAYT = 72


class ParolaCokUzun(ValueError):
    pass


def parola_hashle(parola: str) -> str:
    ham = parola.encode("utf-8")
    if len(ham) > MAKS_PAROLA_BAYT:
        raise ParolaCokUzun(f"Parola en fazla {MAKS_PAROLA_BAYT} bayt olabilir")
    return bcrypt.hashpw(ham, bcrypt.gensalt()).decode("utf-8")


def parola_dogrula(parola: str, hash_: str) -> bool:
    ham = parola.encode("utf-8")
    if len(ham) > MAKS_PAROLA_BAYT:
        return False
    try:
        return bcrypt.checkpw(ham, hash_.encode("utf-8"))
    except ValueError:
        return False          # bozuk/eski biçimli hash — giriş reddedilir


def jwt_uret(kullanici_id: int, omur: timedelta | None = None) -> str:
    """Konu (`sub`) olarak e-posta değil KULLANICI ID kullanılır: kullanıcı
    e-postasını değiştirdiğinde mevcut oturumları düşmesin."""
    a = ayarlar()
    simdi = utc_simdi()
    yuk = {
        "sub": str(kullanici_id),
        "iat": simdi,
        "exp": simdi + (omur or timedelta(minutes=a.jwt_omur_dk)),
    }
    return jwt.encode(yuk, a.jwt_gizli_anahtar, algorithm=a.jwt_algoritma)


def jwt_coz(token: str) -> dict[str, Any] | None:
    """Geçersiz/süresi dolmuş token'da None döner — çağıran 401 üretir."""
    a = ayarlar()
    try:
        return jwt.decode(token, a.jwt_gizli_anahtar, algorithms=[a.jwt_algoritma])
    except jwt.PyJWTError:
        return None


def jwt_kullanici_id(token: str) -> int | None:
    yuk = jwt_coz(token)
    if not yuk:
        return None
    try:
        return int(yuk["sub"])
    except (KeyError, TypeError, ValueError):
        return None


def tek_kullanimlik_token() -> str:
    """Parola sıfırlama / e-posta doğrulama için URL güvenli token.

    `token_urlsafe(32)` = 256 bit entropi; kaba kuvvetle bulunması pratikte
    imkânsız. Ayrıca kısa ömürlü ve tek kullanımlıktır.
    """
    return secrets.token_urlsafe(32)


def token_hashle(token: str) -> str:
    """Token'ı SAKLAMAK için hash'ler.

    Bu sütunlar paroladan farksız yetki taşır: geçerli sıfırlama token'ı
    olan kişi hesabı devralır. Ham saklanırsa bir veritabanı yedeği sızdığında
    ya da bir okuma açığında doğrudan hesap devralma olur; hash'i işe yaramaz.

    Neden bcrypt değil SHA-256: bcrypt'in yavaşlığı DÜŞÜK ENTROPİLİ girdiler
    (insan parolaları) içindir. Bu token 256 bit CSPRNG çıktısı — sözlük
    saldırısı diye bir şey yok, hızlı hash hem yeterli hem doğrulamayı ucuz
    tutuyor. Kritik olan veritabanında ham token bulunmaması.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_eslesir_mi(token: str, saklanan_hash: str | None) -> bool:
    """Sabit zamanlı karşılaştırma."""
    if not saklanan_hash:
        return False
    return secrets.compare_digest(token_hashle(token), saklanan_hash)


def baglama_tokeni() -> str:
    """Telegram deep-link için tek kullanımlık token.

    Kullanıcı chat ID'sini ELLE GİRMEZ (bkz. docs/MIMARI.md K7): web bu
    token'ı üretir, kullanıcı `t.me/bot?start=<token>` linkine tıklar, bot
    token'ı doğrulayıp chat_id'yi sunucu tarafında yazar. Elle giriş, botun
    yazma yetkisi olduğu bir sistemde hesap ele geçirme yoludur.

    `token_urlsafe(24)` = 192 bit entropi; 10 dakikalık ömürde brute-force
    pratikte imkânsız.
    """
    return secrets.token_urlsafe(24)

"""E-posta gönderimi.

Parola sıfırlama ve adres doğrulama bu katman olmadan YAZILAMAZ; ürünün
hesap yaşam döngüsündeki en temel boşluk buydu (parolasını unutan kullanıcı
hesabını tamamen kaybediyordu).

TASARIM — `Postaci` protokolü, tıpkı Telegram tarafındaki gibi:
  • `SmtpPostaci`   → gerçek gönderim (üretim)
  • `GunlukPostaci` → gönderimi loga yazar (geliştirme; SMTP kurmadan çalış)
  • testlerde sahte bir uygulama verilir

Neden üçüncü parti SDK (SendGrid/SES) yok: gönderdiğimiz e-posta sayısı çok
az (yalnızca sıfırlama/doğrulama) ve hepsi işlemsel. `smtplib` standart
kütüphanede; herhangi bir SMTP sağlayıcısı (Postmark, Resend, Gmail, kurumsal
sunucu) aynı arayüzden çalışır. Sağlayıcıya kilitlenmemenin bedeli sıfır.

GÖNDERİM ÇAĞRI İÇİNDE YAPILMAZ: SMTP sunucusu yavaşsa ya da düşükse
kullanıcı "parolamı unuttum" ekranında 30 saniye bekler. Uyarılarda olduğu
gibi (K23 outbox) gönderim arka plana atılır; burada FastAPI'nin
`BackgroundTasks`'i yeterli — e-posta kaybolursa kullanıcı yeniden ister,
fiyat uyarısı gibi kalıcı olması gereken bir veri değil.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol

from .ayarlar import ayarlar
from .gunluk import log

logger = log("keepmoney.eposta")


class EpostaPostacisi(Protocol):
    """Gönderim arayüzü. Testler sahte uygulama verir, ağ gerekmez."""

    def gonder(self, alici: str, konu: str, govde: str) -> bool: ...


class GunlukPostaci:
    """Geliştirme postacısı — e-postayı GÖNDERMEZ, loga yazar.

    SMTP yapılandırılmadan da tüm akış uçtan uca denenebilsin diye var.
    Bağlantı log satırından kopyalanıp tarayıcıya yapıştırılabilir.

    ÜRETİMDE GÖVDE LOGA YAZILMAZ. Gövde, parola sıfırlama ve e-posta
    doğrulama bağlantılarını TAŞIR; o bağlantılardaki token parolaya
    eşdeğer yetkidir — token'ı eline geçiren hesabı devralır. Token'lar
    veritabanında tam bu yüzden HASH'Lİ saklanıyor (guvenlik.token_hashle);
    ham hâllerini loga yazmak o korumayı tamamen anlamsız kılar, üstelik
    daha kötü bir yere: loglar çoğu kurulumda merkezî bir toplayıcıya
    akar ve veritabanından DAHA GENİŞ bir kitleye açıktır.

    ÖLÇÜLDÜ: `KEEPMONEY_ORTAM=uretim` + SMTP tanımsızken sıfırlama
    token'ı düz metin olarak log satırına düşüyordu. Bu yapılandırma
    yalnızca UYARI veriyor, açılışı engellemiyor — yani gerçekten
    oluşabilir bir durum.
    """

    def __init__(self) -> None:
        self.gonderilenler: list[tuple[str, str, str]] = []

    def gonder(self, alici: str, konu: str, govde: str) -> bool:
        self.gonderilenler.append((alici, konu, govde))
        if ayarlar().uretim_mi:
            # Gövde YOK. Operatör eksik yapılandırmayı görsün ama token
            # loga girmesin. `False` dönüyor: gönderim gerçekten olmadı,
            # çağıran tarafın buna "başarılı" demesi yanlış olurdu.
            logger.warning("eposta_gonderilemedi_smtp_yok",
                           alici=alici, konu=konu)
            return False
        logger.info("eposta_gonderilmedi_gelistirme",
                    alici=alici, konu=konu, govde=govde)
        return True


class SmtpPostaci:
    """Gerçek gönderim. STARTTLS varsayılan; 465 portunda doğrudan SSL."""

    def __init__(self) -> None:
        a = ayarlar()
        self.sunucu = a.smtp_sunucu
        self.port = a.smtp_port
        self.kullanici = a.smtp_kullanici
        self.parola = a.smtp_parola
        self.gonderen = a.eposta_gonderen

    def gonder(self, alici: str, konu: str, govde: str) -> bool:
        mesaj = EmailMessage()
        mesaj["Subject"] = konu
        mesaj["From"] = self.gonderen
        mesaj["To"] = alici
        mesaj.set_content(govde)

        try:
            if self.port == 465:
                baglanti = smtplib.SMTP_SSL(self.sunucu, self.port, timeout=15)
            else:
                baglanti = smtplib.SMTP(self.sunucu, self.port, timeout=15)
            with baglanti as s:
                if self.port != 465:
                    s.starttls()
                if self.kullanici:
                    s.login(self.kullanici, self.parola or "")
                s.send_message(mesaj)
            logger.info("eposta_gonderildi", alici=alici, konu=konu)
            return True
        except Exception as e:
            # Gönderim hatası isteği DÜŞÜRMEZ: kullanıcıya zaten nötr mesaj
            # dönüyoruz (hesap sayımı sızmasın diye), o yüzden burada
            # yapılacak tek şey görünür biçimde loglamak.
            logger.error("eposta_gonderilemedi", alici=alici, hata=str(e))
            return False


def postaci() -> EpostaPostacisi:
    """Yapılandırmaya göre postacı seçer.

    SMTP sunucusu tanımlı değilse geliştirme postacısına düşer. Üretimde
    tanımsız bırakmak, parola sıfırlamanın sessizce çalışmaması demektir —
    bu yüzden `ayarlar` üretimde açılışta uyarıyor.
    """
    return SmtpPostaci() if ayarlar().smtp_sunucu else GunlukPostaci()

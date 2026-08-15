"""SSRF koruması — kullanıcının verdiği URL'e gitmeden önceki son kapı.

TEHDİT: Bu üründe kullanıcı KEYFİ bir URL veriyor ve sunucu ona HTTP isteği
atıyor. Bu, Server-Side Request Forgery'nin ders kitabı tanımıdır
(OWASP Top 10 — A10). Korumasız hâlde saldırgan şunu ekleyebilir:

    https://169.254.169.254/latest/meta-data/iam/security-credentials/

Bulut sağlayıcılarının metadata ucu budur ve IAM anahtarları döndürür. Sayfa
başlığı ürün adı olarak KULLANICIYA GERİ GÖSTERİLDİĞİ için bu kör bir SSRF
bile değil — doğrudan veri sızdırma kanalıdır. Aynı yolla `veritabani:5432`,
`localhost:8000`, `10.0.0.0/8` gibi iç ağ hedefleri taranabilir.

SAVUNMA — üç katman:
  1. Şema beyaz listesi (yalnız http/https)
  2. Ana makine adının ÇÖZÜLMÜŞ IP'lerinin tamamı halka açık olmalı
     (yalnız yazılı IP'ye bakmak yetmez: `iç.saldirgan.com` → 10.0.0.5)
  3. Yönlendirmeler elle takip edilir ve HER SIÇRAMA yeniden doğrulanır
     (halka açık bir URL 302 ile metadata ucuna atabilir)

ARTIK RİSK — DNS rebinding: doğrulama ile bağlantı arasında DNS cevabı
değişebilir. Tam çözüm, çözülen IP'ye doğrudan bağlanıp Host başlığını elle
vermektir; requests'te bu ek bir taşıyıcı (adapter) gerektirir. Zaman
penceresi çok dar ve saldırı yüzeyi sınırlı olduğu için şimdilik kabul edildi
ve burada açıkça kayda geçirildi.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

IZINLI_SEMALAR = frozenset({"http", "https"})

# Yönlendirme zinciri sınırı. Sonsuz döngü ve zincir sonunda iç ağa sapma.
MAKS_YONLENDIRME = 3

# Tek sayfadan okunacak azami bayt. Bunu koymazsak tek bir dev sayfa
# (ya da sıkıştırma bombası) worker'ın belleğini bitirir.
MAKS_GOVDE_BAYT = 5 * 1024 * 1024        # 5 MB


class GuvensizHedef(ValueError):
    """URL iç ağa/özel adrese işaret ediyor."""


def _ip_halka_acik_mi(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """`is_global` tek başına yetmez: bazı sürümlerde link-local ve reserved
    aralıkları beklenenden farklı sınıflanıyor. Açıkça sayıyoruz."""
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local          # 169.254.0.0/16 — bulut metadata burada
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _cozumle(host: str) -> list[str]:
    """Ana makine adının TÜM A/AAAA kayıtları. Çözülemezse boş liste."""
    try:
        bilgi = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    return [k[4][0] for k in bilgi]


def url_sorunu(url: str) -> str | None:
    """URL güvenli mi? Değilse sebebini döner (None = güvenli).

    Hem ekleme anında (kullanıcıya anlamlı hata) hem çekme anında (asıl
    koruma) çağrılır. İki yerde çağırmak fazlalık değil: ekleme anındaki
    kontrol kullanıcı deneyimi, çekme anındaki güvenliktir.
    """
    try:
        p = urlparse(url)
    except ValueError:
        return "URL çözümlenemedi"

    if p.scheme not in IZINLI_SEMALAR:
        return f"yalnızca http/https destekleniyor ('{p.scheme}' verildi)"

    host = p.hostname
    if not host:
        return "URL'de ana makine adı yok"

    # Yazılı IP verilmişse doğrudan kontrol et
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None if _ip_halka_acik_mi(ip) else (
            f"özel/iç ağ adresi hedeflenemez ({host})")

    # Ad → IP. Çözülen adreslerin HEPSİ halka açık olmalı: bir kaydı bile
    # iç ağa düşen ad, saldırganın kontrolündeki bir DNS olabilir.
    adresler = _cozumle(host)
    if not adresler:
        return f"alan adı çözümlenemedi ({host})"

    for ham in adresler:
        try:
            ip = ipaddress.ip_address(ham)
        except ValueError:
            continue
        if not _ip_halka_acik_mi(ip):
            return f"alan adı iç ağ adresine çözülüyor ({host} → {ham})"

    return None


def guvenli_mi(url: str) -> bool:
    return url_sorunu(url) is None


def dogrula(url: str) -> None:
    """Güvensizse `GuvensizHedef` fırlatır."""
    sorun = url_sorunu(url)
    if sorun is not None:
        raise GuvensizHedef(sorun)

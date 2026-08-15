"""Affiliate (ortaklık) linki üretimi — gelir modeli.

TEMEL KURAL: saklanan URL'ye DOKUNULMAZ.

Ortaklık etiketi yalnızca kullanıcı mağazaya giderken, TIKLAMA ANINDA
eklenir. Sebep mimari: `Source.url` kanonik anahtardır (K16) — iki kullanıcının
aynı ürüne düşmesi ona bağlı. Etiketi kalıcı yazsak:
  • aynı ürün farklı etiketlerle farklı satırlara bölünürdü,
  • scraper mağazaya ortaklık parametresiyle giderdi (gereksiz, bazı
    programlarda kural ihlali),
  • etiket değişince tüm geçmiş bağlantısı kopardı.

ŞEFFAFLIK: Ortaklık ilişkisi kullanıcıdan gizlenmez. `ortaklik_var` bayrağı
arayüze taşınır ve link "ortaklık bağlantısı" olarak işaretlenir. Bu hem yasal
olarak doğru hem de güvenin tek sermayesi olduğu bir üründe tek doğru seçim:
fiyat tavsiyesi veren bir sistemde gizli komisyon, ürünün tüm iddiasını çürütür.

TARAFSIZLIK: Ortaklık, hangi kaynağın "en ucuz" seçileceğini ETKİLEMEZ.
`karar.en_iyi_kaynak` yalnızca fiyata bakar ve bu modülü hiç tanımaz.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# İsimleri değil MODÜLÜ import ediyoruz: `from .siteler import kural` adı
# import anında bağlar ve hem testte hem çalışma zamanında değiştirilemez
# hâle getirir. Modül üzerinden çağırmak bağı geç kurar.
from . import siteler


def ortaklik_kurali(url: str) -> dict | None:
    """Site kuralındaki `ortaklik` bloğu.

    Biçim (siteler/*.yaml):
        ortaklik:
          parametre: "tag"          # sorgu parametresi olarak eklenir
          deger: "keepmoney-21"
    """
    o = siteler.kural(url).get("ortaklik")
    return o if isinstance(o, dict) and o.get("parametre") and o.get("deger") else None


def cikis_linki(url: str) -> tuple[str, bool]:
    """Mağazaya gidiş linki. Dönüş: (link, ortaklik_var).

    Kural yoksa URL olduğu gibi döner — ortaklık isteğe bağlı bir katmandır,
    yokluğu hiçbir şeyi bozmaz.
    """
    o = ortaklik_kurali(url)
    if o is None:
        return url, False

    parcalar = urlparse(url)
    sorgu = dict(parse_qsl(parcalar.query, keep_blank_values=True))

    # Kullanıcının/mağazanın kendi parametresi zaten varsa ÜZERİNE YAZMA:
    # başka birinin ortaklık kodunu çalmak, programdan atılma sebebidir.
    if o["parametre"] in sorgu:
        return url, False

    sorgu[o["parametre"]] = o["deger"]
    return urlunparse(parcalar._replace(query=urlencode(sorgu))), True


def ortaklik_aktif_mi(url: str) -> bool:
    return ortaklik_kurali(url) is not None


def desteklenen_magazalar() -> list[str]:
    """Şeffaflık sayfası için: hangi mağazalarda ortaklığımız var."""
    return [d for d in siteler.tanimli_siteler()
            if ortaklik_aktif_mi(f"https://{d}/")]


__all__ = [
    "cikis_linki",
    "desteklenen_magazalar",
    "ortaklik_aktif_mi",
    "ortaklik_kurali",
]

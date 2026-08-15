"""TL fiyat ayrıştırma ve biçimleme — sistemin en kritik saf fonksiyonları.

Bir fiyatı yanlış okumak, yanlış alarm göndermekten daha kötüdür: bozuk değer
geçmişe yazılır ve aylarca "dip" hesabını zehirler. Bu yüzden parse tarafı
tolerant değil, MUHAFAZAKÂRDIR — emin olamadığı girdiye None döner.
"""
import re

# Üst sınır: 100 milyon TL üstü bir perakende fiyatı gerçek değildir; bu tür
# değerler neredeyse her zaman parse hatasıdır (birleşmiş iki sayı, telefon
# numarası, ürün kodu vb.).
MAKUL_UST_SINIR = 100_000_000


def parse_tl(s) -> float | None:
    """TL fiyat metnini sayıya çevirir. Kritik ayrım:

    '53.599 TL'    → nokta binlik ayracı  → 53599.0
    '53.599,50 TL' → virgül ondalık       → 53599.5
    '599.5 TL'     → nokta ondalık        → 599.5
    '2,399.00 TL'  → EN yerelli site      → 2399.0

    Kural: hem nokta hem virgül varsa SONDAKİ işaret ondalıktır; tek işaret
    varsa ve sonrasında tam 3 hane varsa binliktir.

    Bu ayrım Türk e-ticaret siteleri için hayati: aynı sayfada '53.599' (elli
    üç bin) ile '599.5' (beş yüz doksan dokuz buçuk) yan yana geçebiliyor.
    """
    if s is None:
        return None
    if isinstance(s, (int, float)):
        v = float(s)
        return v if 0 < v < MAKUL_UST_SINIR else None

    temiz = re.sub(r"[^\d.,]", "", str(s))
    if not temiz or not any(c.isdigit() for c in temiz):
        return None

    if "," in temiz and "." in temiz:
        if temiz.rfind(",") > temiz.rfind("."):      # 53.599,50
            temiz = temiz.replace(".", "").replace(",", ".")
        else:                                        # 53,599.50
            temiz = temiz.replace(",", "")
    elif temiz.count(",") > 1:                       # 1,053,599
        temiz = temiz.replace(",", "")
    elif "," in temiz:                               # 53599,50 | 53,599
        bas, son = temiz.split(",")
        temiz = bas + son if len(son) == 3 else bas + "." + son
    elif temiz.count(".") > 1:                       # 1.053.599
        temiz = temiz.replace(".", "")
    elif "." in temiz:                               # 53.599 binlik | 599.5 ondalık
        bas, son = temiz.split(".")
        if len(son) == 3:
            temiz = bas + son

    try:
        v = float(temiz)
    except ValueError:
        return None
    return v if 0 < v < MAKUL_UST_SINIR else None


def tl(v: float | None) -> str:
    """Tam biçim: 26.450,00 TL"""
    if v is None:
        return "—"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


def kisa_tl(v: float | None) -> str:
    """Kompakt biçim (buton/rozet içi): 26.450₺ — ondalık yok, dar alanda
    fiyatın TAMAMI görünsün."""
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", ".") + "₺"


def yuzde(v: float) -> str:
    """Değişim gösterimi: -4.23 → '↓%4,2' · 2.1 → '↑%2,1'"""
    ok = "↓" if v < 0 else "↑"
    return f"{ok}%{abs(v):.1f}".replace(".", ",")

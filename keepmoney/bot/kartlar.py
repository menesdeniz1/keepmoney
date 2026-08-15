"""Telegram mesaj ve klavye kurucuları — SAF fonksiyonlar.

aiogram import EDİLMEZ. Girdi: model nesneleri. Çıktı: metin ve düğme
sözlükleri. Sebep tanıdık: mesaj biçimi, ürünün kullanıcıya dokunduğu yerdir
ve ağ/kütüphane olmadan test edilebilmelidir. Handler katmanı bu çıktıları
aiogram nesnelerine çevirir, başka iş yapmaz.

Düğme verisi (`callback_data`) Telegram'da 64 BAYT ile sınırlı — bu yüzden
kısa eylem kodları kullanılır ("h:12:45000" gibi), okunaklı isimler değil.
"""
from __future__ import annotations

from ..analiz import Baglam
from ..fiyat import kisa_tl, tl

# Telegram callback_data sınırı. Aşılırsa düğme SESSİZCE çalışmaz.
CALLBACK_SINIRI = 64


def _kirp(metin: str, uzunluk: int) -> str:
    return metin if len(metin) <= uzunluk else metin[: uzunluk - 1] + "…"


def karsilama(bagli: bool, eposta: str | None = None) -> str:
    if bagli:
        return (f"👋 Hoş geldin! Hesabın bağlı: {eposta}\n\n"
                "/liste — takip ettiklerin\n"
                "/yardim — neler yapabilirim")
    return (
        "👋 Ben KeepMoney botuyum.\n\n"
        "Fiyat uyarılarını buradan alabilir, hedeflerini buradan "
        "değiştirebilirsin.\n\n"
        "Başlamak için siteden **Ayarlar → Telegram'a bağla** de ve çıkan "
        "bağlantıya tıkla. Chat ID kopyalaman gerekmiyor."
    )


def baglama_basarili(eposta: str) -> str:
    return (f"✅ Hesabın bağlandı: {eposta}\n\n"
            "Bundan sonra fiyat uyarıları buraya da düşecek.\n"
            "/liste ile takip ettiklerini görebilirsin.")


def baglama_basarisiz() -> str:
    return ("⚠️ Bu bağlantı geçersiz ya da süresi dolmuş.\n\n"
            "Siteden **Ayarlar → Telegram'a bağla** ile yeni bir bağlantı "
            "üret — bağlantılar 10 dakika geçerlidir.")


YARDIM = (
    "🤖 *KeepMoney*\n\n"
    "/liste — takip ettiğin ürünler\n"
    "/durum — özet: kaç ürün, kaçı hedefte\n"
    "/yardim — bu mesaj\n\n"
    "Ürün eklemek için siteye link yapıştırman yeterli; buradan da "
    "hedeflerini değiştirip bildirimleri susturabilirsin."
)


def liste_metni(izlemeler: list) -> str:
    """Takip listesi. Hedefte olanlar önce — kullanıcı önce fırsatı görsün."""
    if not izlemeler:
        return "Henüz takip ettiğin ürün yok. Siteden bir link ekleyerek başla."

    def sira(w):
        f, h = (w.product.guncel_fiyat if w.product else None), w.hedef_fiyat
        hedefte = bool(f and h and f <= h)
        return (0 if hedefte else 1, w.product.ad if w.product else "")

    satirlar = [f"📋 *{len(izlemeler)} ürün izleniyor*\n"]
    for w in sorted(izlemeler, key=sira):
        if not w.product:
            continue
        f, h = w.product.guncel_fiyat, w.hedef_fiyat
        if f and h and f <= h:
            durum = "🎯"
        elif f and h:
            durum = f"→ {kisa_tl(f - h)}"
        else:
            durum = ""
        satirlar.append(f"• {_kirp(w.product.ad, 40)} — *{tl(f)}* {durum}")
    return "\n".join(satirlar)


def durum_metni(izlemeler: list) -> str:
    toplam = len(izlemeler)
    hedefte = sum(
        1 for w in izlemeler
        if w.product and w.product.guncel_fiyat and w.hedef_fiyat
        and w.product.guncel_fiyat <= w.hedef_fiyat
    )
    okunamayan = sum(
        1 for w in izlemeler if w.product and w.product.guncel_fiyat is None)
    liste_toplami = sum(
        (w.product.guncel_fiyat or 0) for w in izlemeler if w.product)

    return (f"📊 *Durum*\n\n"
            f"İzlenen ürün: {toplam}\n"
            f"Hedefte: {hedefte}\n"
            f"Henüz okunamayan: {okunamayan}\n"
            f"Liste toplamı: {tl(liste_toplami)}")


def urun_karti(izleme, baglam: Baglam | None, yorum_metni: str) -> str:
    """Tek ürünün kartı — uyarı mesajlarının altına da bu içerik gider."""
    u = izleme.product
    satirlar = [f"*{_kirp(u.ad, 60)}*", f"💰 {tl(u.guncel_fiyat)}"]

    if u.guncel_satici:
        satirlar[-1] += f"  ·  {u.guncel_satici}"
    if izleme.hedef_fiyat:
        fark = (u.guncel_fiyat or 0) - izleme.hedef_fiyat
        satirlar.append(
            f"🎯 Hedefin: {tl(izleme.hedef_fiyat)}"
            + (" — HEDEFTE ✅" if fark <= 0 else f" ({kisa_tl(fark)} kaldı)"))
    if u.puan is not None:
        satirlar.append(f"⭐ {u.puan:.1f} ({u.yorum_sayisi or 0} yorum)")

    satirlar.append("")
    satirlar.append(yorum_metni)
    if baglam and baglam.sahte_indirim:
        satirlar.append("⚠️ Bu indirim şişirilmiş fiyattan yapılmış görünüyor.")
    return "\n".join(satirlar)


def urun_klavyesi(izleme_id: int, aktif: bool) -> list[list[dict]]:
    """Kart altındaki hızlı eylemler.

    Numara ezberi yok: her şey düğme. `callback_data` kısa tutulur —
    64 baytı aşan düğme Telegram'da sessizce çalışmaz.
    """
    return [
        [
            {"text": "🎯 Hedefi değiştir", "callback_data": f"hd:{izleme_id}"},
            {"text": "🔕 1 hafta sustur", "callback_data": f"ss:{izleme_id}:7"},
        ],
        [
            {"text": "▶️ Devam ettir" if not aktif else "⏸ Duraklat",
             "callback_data": f"dr:{izleme_id}"},
            {"text": "🗑 Takipten çıkar", "callback_data": f"sl:{izleme_id}"},
        ],
    ]


def hedef_secim_klavyesi(izleme_id: int, guncel_fiyat: float | None) -> list[list[dict]]:
    """Yüzdelik kısayollar — kullanıcı rakam yazmak zorunda kalmasın."""
    if not guncel_fiyat:
        return [[{"text": "✍️ Elle yaz", "callback_data": f"he:{izleme_id}"}]]

    satirlar = []
    for yuzde in (3, 5, 10):
        yeni = round(guncel_fiyat * (1 - yuzde / 100))
        satirlar.append([{
            "text": f"%{yuzde} altı → {kisa_tl(yeni)}",
            "callback_data": f"hs:{izleme_id}:{yeni}",
        }])
    satirlar.append([{"text": "✍️ Elle yaz", "callback_data": f"he:{izleme_id}"}])
    return satirlar


def uyari_mesaji(uyari) -> str:
    """Uyarı kaydını Telegram mesajına çevirir.

    Metnin kendisi zaten `analiz.yorum()` ile üretilmişti — burada yalnızca
    başlık ve gövde birleştirilir. Cümleyi burada yeniden kurmak, web ile
    Telegram'ın farklı şeyler söylemesi demek olurdu.
    """
    return f"*{uyari.baslik}*\n{uyari.mesaj}"


def callback_gecerli_mi(veri: str) -> bool:
    return 0 < len(veri.encode("utf-8")) <= CALLBACK_SINIRI


def callback_coz(veri: str) -> tuple[str, list[str]]:
    """'hs:12:45000' → ('hs', ['12', '45000'])"""
    parcalar = veri.split(":")
    return parcalar[0], parcalar[1:]

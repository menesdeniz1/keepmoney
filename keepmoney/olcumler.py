"""Prometheus ölçümleri.

Sadece KARAR VERDİREN ölçümler. Her şeyi ölçmek, hiçbir şeyi ölçmemekle
aynı kapıya çıkar — panoda 40 grafik varsa kimse bakmaz.

Bu ürünün gerçek riski scraping'in sessizce bozulmasıdır: bir mağaza HTML'ini
değiştirir, fiyatlar okunmaz, kimse fark etmez ve kullanıcı bayat veriye
bakar. Ölçümler bunun etrafında kuruldu.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── Tarama sağlığı — asıl izlenecek şey ──────────────────────────
kaynak_okuma = Counter(
    "keepmoney_kaynak_okuma_toplam",
    "Kaynak okuma denemeleri",
    ["domain", "sonuc"],          # sonuc: ok | engelli | olu | hata | reddedildi
)

okuma_suresi = Histogram(
    "keepmoney_okuma_suresi_saniye",
    "Tek kaynak okuma süresi",
    ["domain"],
    buckets=(0.5, 1, 2, 5, 10, 20, 40),
)

fiyat_guveni = Counter(
    "keepmoney_fiyat_guveni_toplam",
    "Fiyatın hangi yöntemle bulunduğu — regex payının artması, seçicilerin "
    "bozulmaya başladığının erken sinyalidir",
    ["guven"],                    # json-ld | secici | meta | regex | yok
)

# ── Uyarı akışı ──────────────────────────────────────────────────
uretilen_uyari = Counter(
    "keepmoney_uyari_toplam", "Üretilen uyarılar", ["tur"])

bekleyen_uyari = Gauge(
    "keepmoney_bekleyen_uyari",
    "Telegram'a iletilmeyi bekleyen uyarı sayısı — sürekli artıyorsa "
    "gönderici tıkanmıştır")

# ── Kapsam ───────────────────────────────────────────────────────
izlenen_urun = Gauge("keepmoney_izlenen_urun", "Toplam ürün sayısı")
bayat_urun = Gauge(
    "keepmoney_bayat_urun",
    "24 saattir okunamayan ürün sayısı — kullanıcı bayat fiyata bakıyor")

tarama_turu_suresi = Histogram(
    "keepmoney_tarama_turu_saniye", "Bir tarama turunun süresi",
    buckets=(5, 15, 30, 60, 180, 600, 1800))

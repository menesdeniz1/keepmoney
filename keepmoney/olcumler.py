"""Prometheus ölçümleri.

Sadece KARAR VERDİREN ölçümler. Her şeyi ölçmek, hiçbir şeyi ölçmemekle
aynı kapıya çıkar — panoda 40 grafik varsa kimse bakmaz.

Bu ürünün gerçek riski scraping'in sessizce bozulmasıdır: bir mağaza HTML'ini
değiştirir, fiyatlar okunmaz, kimse fark etmez ve kullanıcı bayat veriye
bakar. Ölçümler bunun etrafında kuruldu.

SÜREÇ AYRIMI — bu dosyanın en kolay gözden kaçan yanı:

    api  ────────►  /metrics       (HTTP ölçümleri)
    tarayici ────►  :9100/metrics  (tarama + kapsam ölçümleri)

`prometheus_client`in varsayılan kayıt defteri SÜREÇ İÇİDİR. Tarama sayaçları
`tarayici` sürecinde artar; API süreci onları GÖREMEZ. Bu yüzden her süreç
kendi ucunu kendisi yayınlar ve Prometheus iki hedefi ayrı ayrı toplar
(`compose.yaml`). Tek uç yayınlayıp diğer sürecin sayaçlarını beklemek,
sessizce boş kalan bir pano üretir — ölçüm olmamasından daha kötüdür, çünkü
"ölçüyoruz" sanılır.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── API süreci: HTTP trafiği ─────────────────────────────────────
# Etiket olarak ROTA ŞABLONU kullanılır ("/api/izlemeler/{izleme_id}"),
# ham yol DEĞİL. Ham yol kullanılsaydı her izleme kimliği yeni bir zaman
# serisi doğururdu (kardinalite patlaması) — Prometheus'u şişiren en yaygın
# hata budur.
http_istek = Counter(
    "keepmoney_http_istek_toplam",
    "HTTP istekleri",
    ["yontem", "rota", "durum"],
)

http_sure = Histogram(
    "keepmoney_http_sure_saniye",
    "HTTP istek süresi",
    ["yontem", "rota"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

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

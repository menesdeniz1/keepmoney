# KeepMoney

**Kişisel fiyat takip ve alım zamanlaması.** Fiyatı göstermez — *"şu an almalı mıyım?"* sorusuna cevap verir.

Türkiye'de Keepa'nın karşılığı yok. Akakçe/Cimri fiyat *karşılaştırır*, fiyat *hafızası* tutmaz. KeepMoney bu boşluğu doldurmak için yazılıyor.

> Durum: **uçtan uca çalışıyor.** Web + Telegram botu + tarama motoru,
> Docker ile üç süreç olarak ayağa kalkıyor. **409 backend + 18 arayüz testi**;
> paket hem SQLite hem gerçek PostgreSQL'e karşı, kritik kullanıcı akışları
> ise **gerçek tarayıcıyla uçtan uca** koşuyor (23 senaryo).
> Canlı öncesi güvenlik/mimari denetiminden geçti (OWASP A01/A05/A07/A10).
> **Henüz canlıda çalışmadı** — site seçicileri gerçek sayfalara karşı
> doğrulanmayı bekliyor.
> Kararların gerekçesi: [`docs/MIMARI.md`](docs/MIMARI.md) (44 karar kaydı)

---

## Ne yapar

| | |
|---|---|
| 🔗 **Herhangi bir link** | Sadece katalogdaki ürünler değil — küçük mağazanın linkini de yapıştır, izlemeye alsın |
| 📊 **Fiyat hafızası** | 90 günün dibi, medyanı, tüm zamanların dibi — "bu fiyat gerçekten iyi mi?" |
| 🎭 **Sahte indirim dedektörü** | Önce şişirilip sonra "indirilen" fiyatı yakalar |
| 📦 **Set / bütçe takibi** | "PC toplamam 84.000'in altına insin" — parçalar tek tek hedefte olmasa bile **toplam** yakalanır |
| 🛒 **Çoklu kaynak** | Aynı ürünü N mağazadan izler, **en ucuzunu** bildirir |
| 📱 **İki yüz, tek beyin** | Web dashboard + Telegram botu — ikisi de aynı veriye bakar, birinden değiştirdiğin diğerinde görünür |

**Asıl ayırt edici özellik set/bütçe takibi.** Fiyat alarmı herkeste var; "sepetimin toplamı hedefimin altına indi" alarmı hiçbirinde yok.

---

## Neden bu proje var

İki öncül proje vardı ve ikisi de yarısını çözüyordu:

- **`tracker`** — Telegram botu. Üretimde aylarca çalışmış, çok sağlam koruma mantığı var. Ama tek kullanıcılık, web arayüzü yok.
- **`setprice`** — Web uygulaması. Güzel dashboard, çok kullanıcı, AI karar motoru. Ama şeması ölçeklenmiyor ve koruma katmanı zayıf.

KeepMoney ikisinin birleşimi değil — **`tracker`'ın kanıtlanmış mantığı**, **`setprice`'ın ürün vizyonu**, **yeni ve doğru bir şema** üzerine kurulu.

Ayrıntılı gerekçe: [`docs/MIMARI.md`](docs/MIMARI.md)

---

## Kurulum

### Docker ile (önerilen)

```bash
cp .env.example .env    # KEEPMONEY_JWT_GIZLI_ANAHTAR'ı doldur
docker compose up -d    # veritabanı + göçler + api + tarayıcı + bot
```

### Elle

```bash
git clone https://github.com/menesdeniz1/keepmoney && cd keepmoney
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic upgrade head                          # şemayı kur
pytest                                        # 409 test
uvicorn keepmoney.api.app:app --reload        # API      :8000
python -m keepmoney.zamanlayici               # tarayıcı
python -m keepmoney.bot                       # bot (token varsa)

cd arayuz && npm install && npm run dev       # arayüz   :5173
```

API dokümanı: http://localhost:8000/docs

Üretimde `KEEPMONEY_JWT_GIZLI_ANAHTAR` ZORUNLUDUR (yoksa uygulama açılmaz).
Tüm ayarlar `KEEPMONEY_` önekli ortam değişkenleriyle verilir — bkz.
[`keepmoney/ayarlar.py`](keepmoney/ayarlar.py).

---

## Şu an ne çalışıyor

```
keepmoney/
  ── ALAN (saf Python, sıfır bağımlılık) ────────────────
  analiz.py     ⭐ "bu iyi fiyat mı" + insan cümlesi (yorum)
  karar.py      🛡  okumaya güvenilir mi, alarm gitmeli mi
  fiyat.py         TL parse ve biçimleme
  zaman.py      🇹🇷 saat dilimi politikası (DB'de UTC, gösterimde TR)
  ── UYGULAMA ───────────────────────────────────────────
  servisler/       use-case'ler: kullanici · izleme · urun · setler · uyari
  worker.py     🔁 tarama motoru — çek, çıkar, doğrula, yaz, uyar
  ── ALTYAPI ────────────────────────────────────────────
  models.py     🗄  şema — küresel ürün / kişisel izleme ayrımı
  db.py            bağlantı (SQLite → Postgres)
  ayikla.py        HTML → fiyat (güven zinciri) + puan + başlık
  cekici.py        requests → cloudscraper → Playwright
  siteler.py       site kuralları (siteler/*.yaml — 10 Türk sitesi)
  throttle.py      site kuyruğu + üstel geri çekilme
  ── SUNUM ──────────────────────────────────────────────
  api/             FastAPI: rotalar + bağımlılıklar
  semalar.py       Pydantic v2 API sözleşmesi
  ayarlar.py       tiplenmiş yapılandırma · guvenlik.py  JWT + bcrypt
  zamanlayici.py   tarama döngüsü (7/24 worker süreci)
  bot/             Telegram (aiogram 3) — kartlar saf, handler ince
  affiliate.py     ortaklık linkleri — kanonik URL'ye dokunmaz
  gunluk.py        structlog · olcumler.py  Prometheus
arayuz/            React 19 + TS + Vite + TanStack Query + Recharts
migrations/        Alembic
tests/             409 test, hepsi yeşil
```

**Bağımlılık yönü içeri doğrudur.** Alan katmanı veritabanı, ağ ve framework
bilmez; bu yüzden testlerin çoğu hiçbir kurulum gerektirmez. Aynı iş kuralları
hem API'yi hem Telegram botunu besleyecek — iki yerde iki tanım oluşamaz.

### Tarama akışı

```
sırası gelen ürünleri seç        ← çok izlenen önce, uyarlanabilir aralık
  → her kaynağı çek + çıkar      ← güven zinciri: json-ld > seçici > meta > regex
    → koruma katmanı             ← şüpheli fiyat 2. okumayla doğrulanır
      → temiz okumaları yaz      ← küresel fiyat geçmişi
        → en ucuz kaynağı seç
          → izleyicilere uyarı   ← hedef · 30g dibi · sahte indirim · set bütçesi
            → sonraki tarama zamanını ayarla
```

Tüm zincir gerçek ağa çıkmadan test ediliyor: worker'a sahte bir çekici
veriliyor, 25 uçtan uca test tüm yolları geçiyor.

Çekirdek katman bilerek **saf ve bağımsız** yazıldı: analiz ve karar fonksiyonları veritabanı, ağ veya framework bilmez. Böylece tarama worker'ı, API ve bot **aynı kodu** çağırır — üç yerde üç farklı "dip" tanımı oluşamaz.

### Örnek

```python
from datetime import datetime
from keepmoney.analiz import Okuma, fiyat_baglami

okumalar = [Okuma(datetime(2026, 8, g), f) for g, f in
            [(1, 52000), (3, 51500), (7, 49900), (10, 53000), (14, 48500)]]

b = fiyat_baglami(okumalar, guncel=48500)
print(f"{b.emoji} {b.etiket}")             # 🟢 dip bölgesi
print(f"90g dip: {b.dip90}")               # 48500
print(f"günlerin %{b.yuzdelik}'inden ucuz")  # %100
print(f"sahte indirim: {b.sahte_indirim}")   # False
print(f"trend: {b.trend_yonu}")              # dusuyor
```

---

## Yol haritası

- [x] **Faz 0** — çekirdek: analiz, koruma, şema, testler
- [x] **Faz 1** — tarama motoru: çekme zinciri + çıkarım + koruma + uyarı üretimi
- [x] **Faz 2** — API: JWT kimlik, izleme/set/uyarı uçları, Alembic, kota
- [x] **Faz 3** — web arayüzü: Keepa tarzı grafik, yorum kartı, setler, bildirimler
- [x] **Faz 4** — Telegram botu: deep-link bağlama, kart/buton, outbox gönderimi
- [x] **Faz 5** — zamanlayıcı, structlog, Prometheus ölçümleri, Docker Compose
- [x] **Faz 6** — ortaklık linkleri (şeffaf), PWA

## Lisans

Henüz belirlenmedi.

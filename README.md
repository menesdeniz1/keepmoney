# KeepMoney

**Kişisel fiyat takip ve alım zamanlaması.** Fiyatı göstermez — *"şu an almalı mıyım?"* sorusuna cevap verir.

Türkiye'de Keepa'nın karşılığı yok. Akakçe/Cimri fiyat *karşılaştırır*, fiyat *hafızası* tutmaz. KeepMoney bu boşluğu doldurmak için yazılıyor.

> Durum: **tarama motoru çalışıyor** — link ver, fiyatı okusun, geçmişi tutsun,
> hedefe inince uyarı üretsin. 151 test yeşil.
> Sıradaki: API → web dashboard → Telegram botu. Bkz. [`docs/MIMARI.md`](docs/MIMARI.md).

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

```bash
git clone https://github.com/menesdeniz1/keepmoney && cd keepmoney
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest                      # 82 test
```

---

## Şu an ne çalışıyor

```
keepmoney/
  analiz.py     ⭐ fiyat zekâsı — "bu iyi fiyat mı" (saf fonksiyonlar, DB'siz)
  karar.py      🛡  koruma — okumaya güvenilir mi, alarm gitmeli mi
  worker.py     🔁 tarama motoru — çek, çıkar, doğrula, yaz, uyar
  ayikla.py        HTML → fiyat (güven zinciri) + puan/yorum + başlık
  cekici.py        requests → cloudscraper → Playwright
  siteler.py       site kuralları (siteler/*.yaml — 10 Türk sitesi tanımlı)
  fiyat.py         TL parse ve biçimleme
  throttle.py      site bazlı kuyruk + üstel geri çekilme
  zaman.py      🇹🇷 saat dilimi politikası (DB'de UTC, her yerde TR saati)
  models.py     🗄  şema — küresel ürün / kişisel izleme ayrımı
  db.py            bağlantı (SQLite → Postgres)
tests/           151 test, hepsi yeşil
```

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
- [ ] **Faz 2** — FastAPI: auth, watch CRUD, geçmiş, alert
- [ ] **Faz 3** — web dashboard (grafik, set, bütçe çubuğu)
- [ ] **Faz 4** — Telegram botu (deep-link bağlama, kart/buton UX, iki yönlü)
- [ ] **Faz 5** — kota, affiliate, gözlemlenebilirlik paneli

## Lisans

Henüz belirlenmedi.

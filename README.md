# KeepMoney

**Kişisel fiyat takip ve alım zamanlaması.** Fiyatı göstermez — *"şu an almalı mıyım?"* sorusuna cevap verir.

Türkiye'de Keepa'nın karşılığı yok. Akakçe/Cimri fiyat *karşılaştırır*, fiyat *hafızası* tutmaz. KeepMoney bu boşluğu doldurmak için yazılıyor.

> Durum: **temel katman kuruldu** (analiz + koruma + şema, 82 test yeşil).
> Sıradaki: tarama worker'ı → API → web → Telegram botu. Bkz. [`docs/MIMARI.md`](docs/MIMARI.md).

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
  fiyat.py         TL parse ve biçimleme
  throttle.py      site bazlı kuyruk + üstel geri çekilme
  models.py     🗄  şema — küresel ürün / kişisel izleme ayrımı
  db.py            bağlantı (SQLite → Postgres)
tests/           82 test, hepsi yeşil
```

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
- [ ] **Faz 1** — tarama worker'ı (fetch zinciri + throttle + koruma → DB)
- [ ] **Faz 2** — FastAPI: auth, watch CRUD, geçmiş, alert
- [ ] **Faz 3** — web dashboard (grafik, set, bütçe çubuğu)
- [ ] **Faz 4** — Telegram botu (deep-link bağlama, kart/buton UX, iki yönlü)
- [ ] **Faz 5** — uyarlanabilir tarama sıklığı, kota, affiliate

## Lisans

Henüz belirlenmedi.

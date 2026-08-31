# Yapım listesi — Keepa refleksli arayüz

**Bu dosya tek başına yeterlidir.** Projeye yeni başlayan biri yalnızca bunu
okuyup çalışmaya başlayabilir: kurulum, kurallar, 34 task, kabul ölçütleri ve
sıra burada. Mimari kararların gerekçesi `MIMARI.md`'de, projenin ölçülmüş
durumu `DEVIR.md`'de — ama task'lara başlamak için ikisi de şart değil.

*24 Ağustos 2026 · 34 task · 8 epik · ~11 gün · 3 göç · 4 yeni uç*

**Durum (31 Ağustos 2026): 34/34 task kapalı, 79 kabul ölçütü işaretli.**
İşaretler belgeye bakılarak değil, **kod koşturularak** kondu — yöntem ve
denetimde çıkan üç güvenlik bulgusu için §5'e bak.

---

## 0. Başlarken

### Kurulum

```powershell
.\kur.bat            # sanal ortam, paketler, chromium, veritabanı — tek sefer
.\basla.bat          # API + worker + bot açar
.\dur.bat            # hepsini kapatır
```

Durum kontrolü:

```powershell
.\.venv\Scripts\python.exe betikler\kurulum.py dogrula   # ortam sağlam mı
.\.venv\Scripts\python.exe betikler\kurulum.py durum     # sistem ne durumda
```

Arayüzü geliştirirken:

```powershell
cd arayuz ; npm run dev      # canlı sunucu, API'ye vekil ile bağlanır
```

### Proje ne yapıyor

Kullanıcı herhangi bir mağazanın ürün linkini yapıştırır; sistem fiyatı
periyodik okur, geçmişini biriktirir ve **"bu iyi bir fiyat mı"** sorusunu
cevaplar. Ayrıca ürünler bütçeli **setlere** konabilir: parçalar tek tek
hedefte olmasa bile toplam bütçe yakalanınca haber verilir.

### Dosya haritası

```
keepmoney/
  analiz.py            "iyi fiyat mı" hesabı — dip/ucuz/pahalı, medyan, yüzdelik
  worker.py            tarama turu + uyarı üretimi
  models.py            SQLAlchemy modelleri
  semalar.py           Pydantic şemaları (API sözleşmesi)
  cekici.py            sayfa çekme: requests → cloudscraper → playwright
  ayikla.py            HTML'den fiyat/ad çıkarma
  siteler/*.yaml       site başına seçici kuralları
  servisler/           use-case katmanı (izleme.py, setler.py)
  api/rotalar/         FastAPI uçları
  bot/                 Telegram botu
arayuz/src/
  sayfalar/            Panel, IzlemeDetay, Setler, Uyarilar, Ayarlar…
  bilesenler/          IzlemeKarti, FiyatGrafigi, SetUyeSecici…
  api/                 istemci.ts (fetch), kancalar.ts (TanStack Query), tipler.ts
tests/                 pytest — birim + API + uçtan uca (gerçek tarayıcı)
migrations/versions/   Alembic göçleri
```

---

## 1. Çalışma kuralları

### Bitti sayılma şartı

Bir task, şu beşi birden yeşil olmadan **bitmiş sayılmaz**:

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # tamamı, ~2,5 dk
.\.venv\Scripts\python.exe -m ruff check .
cd arayuz ; npx tsc -b ; npx eslint src --max-warnings=0 ; npm test ; cd ..
.\.venv\Scripts\python.exe -m alembic check
```

Arayüz değiştiyse ayrıca `npm run build` ve `dist` → `statik/` kopyalanır.
Push'tan sonra **CI kontrol edilir** — bir dönem üç commit boyunca kırmızı
kaldı ve fark edilmedi.

**Yeni davranışın testi yoksa task kapanmaz.** Arayüz davranışı
`tests/test_e2e_arayuz.py`'a, iş kuralı ilgili birim testine yazılır.

### Kod kuralları

- Kod, yorum, commit mesajı, belge **hepsi Türkçe**
- Yorumlar **NEDEN**'i anlatır, NE'yi değil. Gerçek bir vakadan geliyorsa o
  vakayı yaz — bu depodaki yorumların değeri buradan geliyor
- Katmanlı mimari, bağımlılıklar içe doğru: `api → servisler → models`
- Saat dilimi Europe/Istanbul, para birimi TL
- Gizli bilgi (anahtar, token, parola) **asla** commit edilmez

### Asla yapılmayacaklar

Görünürde başarı üretmek için: testi devre dışı bırakmak, kırık testi
gerekçesiz silmek, özelliği yorum satırına almak, istisnayı yutmak, cevabı
sabit kodlamak, lint kuralını global kapatmak, güvensiz tip bastırma eklemek,
yer tutucu veri döndürmek, **çalıştırmadan "bitti" demek**.

### Bilinen tuzaklar — bunlara takılacaksın

**Göç yazarken.** SQLite sütun ekleme/düşürmeyi desteklemiyor; Alembic tabloyu
DROP edip yeniden kuruyor ve `ON DELETE CASCADE` bağlı satırları siliyor. Göç
hatasız biter, `alembic check` temiz der, veri gider. **Sıra: veriyi belleğe
al → şemayı değiştir → geri yaz.** Her göç için `tests/test_gocler.py`'a
gerçek veriyle test eklenir; `alembic check` şemayı doğrular, veriyi değil.

**Uçtan uca test yazarken.** `wait_for_function` uygulamanın CSP'sine takılır
(`unsafe-eval` yok) — `expect(locator).to_have_count(...)` kullan. Kontrollü
onay kutusunda `check()` değil `click()`: işaret ancak sunucu cevabı gelince
döner, `check()` "durumu değişmedi" diye patlar.

**Test saati.** Sessiz saat kuralı (00:00–08:00) uyarıları erteliyor. Uyarı
testi yazarken saati sabitle, yoksa paket gece kırmızıya döner.

**Alt süreç çıktısı.** Bir alt sürecin `stdout`'unu boruya bağlıyorsan ya oku
ya dosyaya yönlendir. Okunmayan boru sessiz kilitlenme mekanizmasıdır.

---

## 2. Bu iş neden var

`analiz.fiyat_baglami()` dip/ucuz/pahalı sinyalini, 90 günün dibini, medyanı,
yüzdeliği, trendi ve sahte indirim tespitini üretiyor. Ürün detayında güzelce
gösteriliyor.

**Panelde hiç yok.** Kart yalnızca ad, satıcı, son kontrol, fiyat ve varsa
hedefe kalan mesafeyi gösteriyor. `worker.py:424` her taramada bu bağlamı
hesaplıyor, uyarı kararı için kullanıyor ve **atıyor**; `Product` tablosunda
saklayan sütun yok.

Yani ürünün en değerli tarafı, en çok bakılan ekranda kapalı duruyor — ve
açmak yeni hesap değil, zaten hesaplananı saklamak meselesi.

**Hedef Keepa'nın kopyası değil.** İki yerde zaten öndeyiz ve korunacak: çok
mağaza tek ürün (Keepa yalnızca Amazon izler) ve bütçeli setler (rakiplerde
yok). Keepa'dan alınacak olan **refleksler**: fiyatın iyi olup olmadığını ürünü
açmadan anlamak, grafiği zaman aralığıyla okumak, fırsatları tek yerde görmek.

---

## EPİK A · Sinyali görünür yapmak

*8 task · ~2,5 gün · en yüksek getiri*

### A1 — `Product`'a bağlam sütunları

**Tür:** DB · göç · 3 saat
**Neden:** Sinyal her taramada hesaplanıyor ama saklanmıyor; liste ucu ürün
başına geçmiş sorgusu açmadan gösteremiyor.

**Dosyalar:** `keepmoney/models.py` · `migrations/versions/xxxx_urun_baglami.py` (yeni) · `tests/test_gocler.py`

**Yapılacak.** `Product` sınıfına altı sütun:

```python
sinyal      = Column(String,   nullable=True)   # dip | ucuz | pahali
dip90       = Column(Float,    nullable=True)
medyan90    = Column(Float,    nullable=True)
yuzdelik    = Column(Integer,  nullable=True)   # 0-100
gecmis_gun  = Column(Integer,  nullable=True)   # kaç günlük veri var
baglam_ts   = Column(DateTime, nullable=True)   # ne zaman hesaplandı
```

- Hepsi `nullable` — mevcut ürünlerde veri yok, ilk taramada dolar.
- `sahte_indirim` ve `trend_yonu` **saklanmaz**: kart bunları göstermiyor,
  gösterecek yer detay sayfası ve orada zaten canlı hesaplanıyor. Gereksiz
  sütun yazma maliyetidir.
- Göç yalnızca sütun ekliyor ama SQLite'ta yine tablo yeniden kuruluyor →
  §1'deki göç kuralı geçerli.

**Kabul ölçütleri**

- [x] `alembic upgrade head` sonrası altı sütun var, mevcut ürünler ve izlemeler duruyor
- [x] `alembic downgrade` sütunları kaldırıyor, `set_uyeleri` satırları hâlâ yerinde
- [x] `alembic check` temiz

**Test.** `tests/test_gocler.py`: göçten önce ürün + izleme + set üyeliği yaz,
`upgrade` et, üçünün de durduğunu ve sütunların geldiğini doğrula. Sonra
`downgrade` edip üyeliklerin hâlâ orada olduğunu doğrula.

---

### A2 — Worker hesapladığını yazsın

**Tür:** arka uç · 2 saat
**Neden:** A1'in sütunlarını dolduran tek yer burası.

**Dosyalar:** `keepmoney/worker.py` · `tests/test_worker.py`

**Yapılacak**

- `uyari_uret()` içinde `baglam` zaten hesaplanıyor (~satır 424). Hemen
  ardından `urun.sinyal = baglam.sinyal` vb. yazılır.
- **Yazma noktasını dikkatli seç:** `uyari_uret` uyarı çıkmayacak durumlarda da
  çağrılıyor mu? Değilse yazma işi `urun_tara`'ya taşınır — sinyal, uyarı
  çıksın çıkmasın güncellenmeli.
- `baglam is None` ise (geçmiş yok) sütunlar `None` bırakılır, **eski değer
  silinmez** — bir tarama okunamadı diye sinyal kaybolmamalı.

**Kabul ölçütleri**

- [x] Bir tarama turundan sonra fiyatı okunan her ürünün `sinyal` ve `baglam_ts`'i dolu
- [x] Okunamayan üründe eski sinyal korunuyor
- [x] Geçmişi 3 günlük üründe `gecmis_gun = 3`

**Test.** Sahte çekiciyle iki tur koştur; ilk turdan sonra sütunların
dolduğunu, ikinci turda okuma başarısız olduğunda eski değerin durduğunu
doğrula.

---

### A3 — Geriye dönük doldurma betiği

**Tür:** arka uç · 1 saat
**Neden:** A1+A2 sonrası sütunlar boş; ilk tarama turuna kadar panel sinyalsiz
kalır. 35 ürün için beklemek gereksiz.

**Dosyalar:** `betikler/baglam_doldur.py` (yeni)

**Yapılacak**

- Tüm ürünler üzerinde dönüp geçmişi okur, `analiz.fiyat_baglami()` çağırır,
  sütunları yazar.
- **Ağ isteği YOK** — yalnızca veritabanındaki geçmişten hesaplar. Güvenle
  tekrar çalıştırılabilir.
- `kurulum.py durum` çıktısına "kaç üründe sinyal var" satırı eklenir.

**Kabul ölçütleri**

- [x] Betik çalıştıktan sonra geçmişi olan her üründe sinyal dolu
- [x] İki kez çalıştırmak aynı sonucu veriyor

---

### A4 — Liste ucu sinyali döndürsün

**Tür:** arka uç · 2 saat
**Neden:** `UrunOzet` yalnızca ad/fiyat/satıcı döndürüyor; sinyal yalnızca
`UrunDetay`'da, yani ürüne tıklamadan görünmüyor.

**Dosyalar:** `keepmoney/semalar.py` · `tests/test_api.py`

**Yapılacak.** `UrunOzet`'e ekle:

```python
sinyal:     str | None = None
dip90:      float | None = None
medyan90:   float | None = None
yuzdelik:   int | None = None
gecmis_gun: int | None = None
```

- **Ek sorgu YOK** — hepsi `Product` sütunu, mevcut yükleme yeterli.
- `UrunDetay`'daki canlı `baglam` alanı **kalıyor**: detay sayfası anlık hesabı
  göstermeye devam eder, kart saklanan değeri kullanır. İkisi arasında bir
  tarama turu kadar fark olabilir ve bu kabul edilebilir.

**Kabul ölçütleri**

- [x] `GET /api/izlemeler` yanıtında her ürün için beş alan var
- [x] Geçmişi olmayan üründe hepsi `null` ve istek hata vermiyor
- [x] Liste ucunun açtığı sorgu sayısı değişmemiş

---

### A5 — Kıvılcım verisi ucu

**Tür:** arka uç · 3 saat
**Neden:** Kartta minik grafik çizmek için ürün başına 90 günlük seri lazım;
35 ayrı istek atmak kabul edilemez.

**Dosyalar:** `keepmoney/api/rotalar/izlemeler.py` · `keepmoney/servisler/izleme.py` · `keepmoney/semalar.py` · `tests/test_api.py`

**Yapılacak.** Yeni uç `GET /api/izlemeler/kivilcimlar?gun=90`:

```json
{ "3": [1639.0, 1639.0, 1720.0],
  "4": [45499.0, 44900.0] }
```

- Anahtar **izleme id**, değer gün başına minimum fiyat dizisi (eskiden yeniye).
  Tarih taşınmaz — kıvılcımda eksen yok, yer kaplar.
- **TEK sorgu:** `WHERE product_id IN (...) GROUP BY product_id, date(ts)`.
  Ürün başına sorgu açan çözüm reddedilir.
- Eksik günler doldurulmaz — kıvılcım yalnızca şekil gösterir.
- Ayrı uç olmasının sebebi: liste yanıtını üç katına çıkarmadan, kart
  göründükten sonra ikinci istekle yüklenebilmesi.

**Kabul ölçütleri**

- [x] 35 ürünlük hesapta uç **tek** SQL sorgusu açıyor (log ile doğrulanacak)
- [x] Geçmişi olmayan ürün sözlükte hiç görünmüyor (boş dizi değil)
- [x] Başkasının izlemesi asla dönmüyor
- [x] `gun` parametresi 7–365 aralığında sınırlı; dışında 422

**Test.** İki kullanıcı kur, birinin ucu diğerinin izlemesini döndürmesin.
Sorgu sayısını SQLAlchemy olayıyla say.

---

### A6 — Sinyal rozeti bileşeni

**Tür:** arayüz · 2 saat
**Neden:** Üç durum tek yerden çizilsin — kart, detay ve Fırsatlar sayfası aynı
rozeti kullanacak.

**Dosyalar:** `arayuz/src/bilesenler/SinyalRozeti.tsx` (yeni) · `arayuz/src/api/tipler.ts`

**Yapılacak**

- Girdi: `sinyal`, `yuzdelik`, `gecmis_gun`
- Metinler: `dip` → "90 günün dibi" · `ucuz` → "ucuz dönem" · `pahali` → "pahalı dönem"
- Renkler mevcut uygulamanın yeşil/amber/kırmızısı. **Yalnızca renkle
  anlatma** — metin de olacak (renk körlüğü)
- `sinyal == null` ise rozet yerine A7'deki "geçmiş biriktiriliyor" hâli

**Kabul ölçütleri**

- [x] Üç durum + null durumu doğru çiziliyor
- [x] Karanlık temada okunabilir
- [x] Rozet metni ekran okuyucuya geçiyor (yalnız renk/emoji değil)

---

### A7 — "Geçmiş biriktiriliyor" hâli

**Tür:** arayüz · 2 saat

**Neden — gerçek çalıştırmada ölçüldü.** Worker 3 gün koştu, HyperX'te %7,2
düşüş oldu ve *hiç uyarı çıkmadı*. Doğru davranış: `worker.py:467` dip uyarısı
için en az 7 günlük geçmiş şart koşuyor, sistem 4 günlük veriyle "rekor"
demeyi reddediyor. Ama kullanıcı bunu bilmiyor — bir hafta sessizlik görüyor ve
kural mı arıza mı ayırt edemiyor. Üstelik detay sayfası 4 günlük veriden
"son 91 günün %1'inden ucuz" gibi yanıltıcı bir yüzdelik gösterebiliyor.

**Dosyalar:** `arayuz/src/bilesenler/SinyalRozeti.tsx` · `arayuz/src/bilesenler/IzlemeKarti.tsx` · `arayuz/src/sayfalar/IzlemeDetay.tsx` · `tests/test_e2e_arayuz.py`

**Yapılacak**

- `gecmis_gun < 7` iken rozet yerine nötr işaret:
  **"3/7 gün — sinyal için geçmiş biriktiriliyor"**
- Detay sayfasındaki analiz kutusuna da aynı cümle; yanıltıcı yüzdelik
  gösterilmeyecek
- Panelde hiç sinyali olmayan ürün varsa üstte tek satır: "N ürün için geçmiş
  biriktiriliyor; ilk sinyaller ~M gün içinde."

**Kabul ölçütleri**

- [x] Yeni eklenen üründe "pahalı" yazmıyor — "geçmiş biriktiriliyor" yazıyor
- [x] 7 günü dolduran üründe rozete geçiyor
- [x] Sayaç gerçek gün sayısını gösteriyor

**Test.** E2E: yeni ürün ekle, kartta "biriktiriliyor" metnini gör, sinyal
rozeti görünmesin.

---

### A8 — Kartı yeniden kur: rozet + kıvılcım + fark

**Tür:** arayüz · 4 saat
**Neden:** Epiğin görünen sonucu.

**Dosyalar:** `arayuz/src/bilesenler/IzlemeKarti.tsx` · `arayuz/src/bilesenler/Kivilcim.tsx` (yeni) · `arayuz/src/api/kancalar.ts` · `arayuz/src/sayfalar/Panel.tsx`

**Yapılacak**

- Kart düzeni: üstte `SinyalRozeti`, altında ad, altında satıcı · son kontrol ·
  **medyana göre % fark**; sağda fiyat ve altında 30 günlük değişim
- `Kivilcim.tsx`: 90 nokta, ~56×20px **inline SVG**, son noktada işaretçi.
  Kütüphane kullanılmaz — recharts bu boyutta ağır ve 35 örneği yavaşlatır
- `useKivilcimlar()` kancası; kıvılcım verisi **ayrı ve gecikmeli** yüklenir,
  kart onsuz da tam görünür
- Kıvılcım rengi sinyale bağlı; `prefers-reduced-motion` ile animasyon yok

**Kabul ölçütleri**

- [x] Kıvılcım ucu 500 ms gecikse bile kart bozulmuyor, sıçrama olmuyor (yer önceden ayrılmış)
- [x] Mobilde (390px) kart taşmıyor, yatay kaydırma yok
- [x] Karanlık temada üç sinyal rengi de okunuyor
- [x] 35 kartlı listede gözle görülür yavaşlama yok

**Test.** E2E: sinyalli ürün kur, kartta rozet metnini ve `svg`'yi gör; mevcut
"mobilde yatay kaydırma yok" testi kırılmasın.

---

## EPİK B · Grafik

*5 task · ~2 gün*

### B1 — Zaman aralığı düğmeleri

**Tür:** arayüz · 2 saat
**Neden:** Tüm geçmiş tek görünümde eziliyor; son haftanın hareketi 120 günün
içinde kayboluyor. Keepa'nın en çok kullanılan kontrolü.

**Dosyalar:** `arayuz/src/bilesenler/FiyatGrafigi.tsx` · `tests/test_e2e_arayuz.py`

**Yapılacak**

- Düğmeler `7g · 30g · 90g · 1y · Tümü`, grafiğin sağ üstünde, seçili işaretli
- Tamamen istemci tarafı — veri zaten geliyor, yalnızca dilimleniyor
- Varsayılan **90g** (analiz penceresiyle aynı, tutarlılık)
- Veri seçilen aralıktan kısaysa düğme `disabled` — tıklanıp hiçbir şey
  olmaması kötü
- Seçim `localStorage`'da; ürünler arası gezerken sıfırlanmaz
- `role="group"` + `aria-pressed`; klavyeyle gezilebilir

**Kabul ölçütleri**

- [x] Aralık değişince y ekseni o dilime göre yeniden ölçekleniyor
- [x] 90 günden az veride "1y" ve "Tümü" pasif
- [x] Sayfa yenilendiğinde son seçim korunuyor

---

### B2 — Geçmişi kaynak bazında döndür

**Tür:** arka uç · 3 saat
**Neden:** `PriceReading.source_id` zaten yazılıyor — *"grafikte mağaza başına
ayrı çizgi çizilebilsin diye"* (models.py yorumu). API bunu tek seriye eziyor;
niyet kodda var, ürüne çıkmamış.

**Dosyalar:** `keepmoney/semalar.py` · `keepmoney/servisler/izleme.py` · `tests/test_api.py`

```python
class SeriNoktasi(BaseModel):
    gun: date
    fiyat: float

class KaynakSerisi(BaseModel):
    kaynak_id: int
    host: str                      # "amazon.com.tr"
    noktalar: list[SeriNoktasi]

# UrunDetay:
gecmis: list[FiyatNoktasi]         # KALIYOR — birleşik seri
seriler: list[KaynakSerisi]        # YENİ
```

- `gecmis` **kaldırılmaz**: kıvılcım ve varsayılan görünüm onu kullanıyor
- Kaynak sayısı 1 ise `seriler` boş dizi döner — istemci tek çizgi çizmeye devam eder
- Tek sorgu, `GROUP BY source_id, date(ts)`

**Kabul ölçütleri**

- [x] İki kaynaklı üründe iki seri, doğru host adlarıyla
- [x] Tek kaynaklı üründe `seriler` boş
- [x] Sorgu sayısı artmamış

---

### B3 — Mağaza başına çizgi + aç/kapa

**Tür:** arayüz · 4 saat
**Neden:** Çok mağaza avantajımızın görünür hâli. Keepa'da çizgiler satıcı
*tipine* göre; bizde gerçekten farklı mağazalara göre — daha anlamlısı.

**Dosyalar:** `arayuz/src/bilesenler/FiyatGrafigi.tsx` · `arayuz/src/api/tipler.ts`

**Yapılacak**

- Her kaynağa sabit renk — **host adının hash'inden**, sıradan değil: kaynak
  eklenip çıkınca renkler kaymasın
- Grafiğin altında açma/kapama: host adı + renk noktası, tıklayınca çizgi gizlenir
- En ucuz kaynağın çizgisi kalın
- Renk paleti karanlık temada da ayırt edilebilir; ikiden fazla kaynakta renk
  körlüğü için çizgi deseni de değişir
- **Varsayılan görünüm birleşik seri kalır.** "Mağazalara ayır" düğmesiyle
  geçilir — grafiği ilk açılışta çizgi çorbasına çevirmek, analizi cümleye
  çeviren üstünlüğümüzü kaybettirir

**Kabul ölçütleri**

- [x] Üç kaynaklı üründe üç ayrı çizgi, renkler tutarlı
- [x] Kaynak gizlenince y ekseni kalanlara göre ölçekleniyor
- [x] Tek kaynaklı üründe "Mağazalara ayır" düğmesi hiç görünmüyor

---

### B4 — Grafikte stok boşlukları

**Tür:** arka uç + arayüz · 4 saat
**Neden:** Fiyatın "sabit kaldığı" dönemle "ürün yok" dönemi grafikte aynı
görünüyor. `STOKTA_YOK` modelde var, grafik bilmiyor. Gerçek veride şu an 3
kaynak bu durumda.

**Yapılacak**

- Nokta şemasına `stokta: bool`
- Stok yokken çizgi kesilir (`fiyat: null` + `connectNulls=false`), arka plana
  soluk tarama deseni
- Grafik altına küçük açıklama: "kesik = stokta yok"

**Kabul ölçütleri**

- [x] Stoksuz dönem gözle ayırt ediliyor
- [x] Stok bilgisi olmayan eski okumalar `stokta: true` sayılıyor — geçmiş bozulmuyor

---

### B5 — Tooltip'i zenginleştir

**Tür:** arayüz · 2 saat
**Neden:** Şu an yalnızca tarih ve fiyat. Kullanıcının sorusu "o gün ucuz muydu".

**Yapılacak.** Tarih · fiyat · **o günkü medyana göre fark** · hangi mağaza ·
stok durumu. Dokunmatikte de çalışsın (mobil PWA).

**Kabul ölçütleri**

- [x] Telefonda dokununca tooltip çıkıyor ve kaybolmuyor
- [x] Tüm zamanlar dibi olan gün ayrıca işaretli

---

## EPİK C · Liste kontrolü

*4 task · ~1 gün · tamamı istemci tarafı*

### C1 — Sıralama

**Tür:** arayüz · 3 saat
**Neden:** 35 üründe sabit sıra zorlaşıyor; 100'de kullanılamaz.

**Dosyalar:** `arayuz/src/sayfalar/Panel.tsx` · `arayuz/src/bilesenler/ListeKontrol.tsx` (yeni)

**Yapılacak**

- Seçenekler: **en iyi fırsat** (yüzdelik) · fiyat artan/azalan · hedefe
  yakınlık · son değişim · ad · eklenme
- Varsayılan "en iyi fırsat" — panel açıldığında en yukarıda alınacak şey durur
- Sinyalsiz ürünler her zaman **sona** (null'lar başa toplanmaz)

**Kabul ölçütleri**

- [x] Her seçenek doğru sıralıyor, null'lar sonda
- [x] Seçim `localStorage`'da kalıcı
- [x] Türkçe sıralama doğru (`localeCompare('tr')` — İ/ı)

---

### C2 — Süzme

**Tür:** arayüz · 3 saat

**Yapılacak**

- Metin araması (ad içinde, Türkçe küçültmeyle)
- Sinyale göre: yalnızca dip · dip+ucuz · hepsi
- Sete göre, mağazaya göre
- Durum: hedefi olanlar · susturulmuşlar · duraklatılmışlar · okunamayanlar
- Aktif süzgeçler kaldırılabilir çipler olarak görünür; "hepsini temizle" var
- Sonuç boşsa **sebebi söylenir**: "Bu süzgeçlere uyan ürün yok" ≠ "Henüz ürün
  eklemedin"

**Kabul ölçütleri**

- [x] İki süzgeç birlikte çalışıyor (VE mantığı)
- [x] Boş sonuç mesajı gerçek sebebi söylüyor
- [x] Süzgeç çipleri klavyeyle kaldırılabiliyor

**Test.** E2E: iki ürün ekle, birini duraklat, "duraklatılmışlar" süzgecinde
tek ürün kalsın.

---

### C3 — Kart / tablo görünümü

**Tür:** arayüz · 3 saat
**Neden:** Masaüstünde iki kolon kart yatay alanı boşa harcıyor; 35 satırlık
tablo daha çok bilgi taşır. Telefonda tam tersi.

**Yapılacak**

- Tablo kolonları: sinyal · ad · kıvılcım · fiyat · medyana fark · hedef · son kontrol
- Kolon başlığına tıklayınca o kolona göre sıralanır (C1 ile aynı durum)
- Tercih kalıcı; **768px altında her zaman kart** — tablo telefonda okunmaz
- Sayılar `tabular-nums` ile hizalı

**Kabul ölçütleri**

- [x] Tablo görünümünde yatay kaydırma kendi kabında, sayfa gövdesi kaymıyor
- [x] Telefonda tablo seçeneği hiç görünmüyor

---

### C4 — Üst kutucukları değiştir

**Tür:** arayüz · 2 saat
**Neden:** Şu an "İzlenen 8 · Hedefte 0 · Liste toplamı ₺118.814". Ortadaki
neredeyse hep sıfır; sağdaki toplam anlamsız, kimse hepsini birden almayacak.

**Yapılacak**

- **Dip bölgesinde N ürün** — tıklayınca C2'nin "yalnızca dip" süzgecini açar
- **Bugün M fiyat değişti** — tıklayınca son değişime göre sıralar
- **Son 30 günde en büyük düşüş** — ürün adı + tutar, tıklayınca ürüne gider
- "Liste toplamı" **kaldırılır** — anlamlı olduğu yer Setler sayfası

**Kabul ölçütleri**

- [x] Üç kutucuk da tıklanabilir ve doğru eylemi yapıyor
- [x] Veri yokken kutucuk sayı yerine anlamlı bir şey söylüyor

---

## EPİK D · Fırsatlar sayfası

*3 task · ~5 saat · A'ya bağımlı*

Keepa'nın Deals'ının bize uyarlanmışı: **takip ettiğin her şey, kendi geçmişine
göre** ne kadar iyi durumda olduğuna göre sıralı. Ürünün her gün açılacak
sayfası bu olur.

### D1 — Fırsat ucu

**Tür:** arka uç · 2 saat
**Dosyalar:** `keepmoney/api/rotalar/firsatlar.py` (yeni) · `keepmoney/servisler/izleme.py` · `tests/test_api.py`

`GET /api/firsatlar?en_az_gun=7&sinyal=dip,ucuz` — `IzlemeYaniti` listesi,
yüzdeliğe göre sıralı.

- `gecmis_gun < en_az_gun` olanlar **hiç girmez** — 3 günlük veriden "fırsat"
  demek yalan olur
- `sahte_indirim` işaretli olanlar listeye girer ama **işaretli** döner;
  gizlemek kullanıcıyı kör eder, sessizce üste koymak yanıltır
- Yeni dosya, çünkü `izlemeler.py` zaten kalabalık ve bu ayrı bir kaynak

**Kabul ölçütleri**

- [x] Sıralama yüzdeliğe göre azalan
- [x] Geçmişi yetersiz ürün listede yok
- [x] Başkasının izlemesi asla dönmüyor
- [x] Ek sorgu yok — A1 sütunlarından okunuyor

---

### D2 — Fırsatlar sayfası + gezinme

**Tür:** arayüz · 3 saat
**Dosyalar:** `arayuz/src/sayfalar/Firsatlar.tsx` (yeni) · `arayuz/src/App.tsx` · `arayuz/src/bilesenler/Duzen.tsx` · `arayuz/src/api/{istemci,kancalar,tipler}.ts`

- `/firsatlar` yolu, gezinmede **Panel'den sonra ikinci sıraya**
- Üstte özet: "N ürün şu an iyi fiyatta."
- Her satır: sinyal · ad · fiyat · medyana fark · kıvılcım · "en son ne zaman
  bu kadar ucuzdu"
- Sahte indirim işaretlisinde uyarı rozeti: "ilan edilen indirim geçmişle
  uyuşmuyor"
- Mobilde gezinme ikon-only; **beşinci sekme 390px'te sığıyor mu kontrol et**

**Kabul ölçütleri**

- [x] Sekme mobilde taşmıyor
- [x] Satıra tıklayınca ürün detayına gidiyor
- [x] Mevcut "tüm ana sayfalar geziliyor" E2E testine yeni sayfa eklenmiş

---

### D3 — Boş durumları ayır

**Tür:** arayüz · 1 saat
**Neden:** Üç ayrı sebep aynı boş ekrana çıkıyor.

- Hiç ürün yok → "Önce panelden ürün ekle."
- Ürün var, geçmiş yetersiz → "N ürün için geçmiş biriktiriliyor, ilk fırsatlar ~M gün içinde."
- Geçmiş var, iyi fiyat yok → "Şu an dip bölgesinde ürün yok. Hepsi normal aralıkta."

**Kabul ölçütü:** [x] Üç durum üç ayrı metin veriyor

---

## EPİK E · Uyarı kurma

*5 task · ~2 gün*

### E1 — Yüzde eşiği: şema ve göç

**Tür:** DB · göç · 2 saat
**Neden:** "%15 düşerse haber ver" — mutlak rakamı bilmeyen kullanıcının doğal
ifadesi. Şu an yalnızca mutlak hedef var.

```python
# Watch:
dusus_yuzdesi   = Column(Integer, nullable=True)  # 1-90
yeniden_kur_gun = Column(Integer, nullable=True)  # rearm, varsayılan 7
```

- Referans **90 günlük medyan**, "en son gördüğüm fiyat" değil: yükselip düşen
  fiyat sahte uyarı üretir
- `tests/test_gocler.py`'a veri koruma testi

---

### E2 — Worker yüzde kuralı

**Tür:** arka uç · 3 saat
**Dosyalar:** `keepmoney/worker.py` · `tests/test_worker.py`

- `_watch_uyarilari` içine üçüncü kural; sıra **acil → hedef → yüzde → dip**.
  Aynı taramada iki uyarı çıkmaz
- Yüzde kuralı da `gun_sayisi >= 7` şartına tabi — medyan az veriyle güvenilmez
- Sessiz saat ve bekleme süresi kuralları aynen geçerli

**Kabul ölçütleri**

- [x] %15 eşiğinde %14,9 düşüş uyarı üretmiyor, %15,1 üretiyor
- [x] Hem hedef hem yüzde sağlanınca yalnızca hedef uyarısı çıkıyor
- [x] 7 günden az geçmişte hiç çıkmıyor
- [x] Sessiz saatte erteleniyor

**Test.** Saat sabitlenerek, sınır değerler tek tek.

---

### E3 — Uyarı kurma arayüzü

**Tür:** arayüz · 3 saat
**Neden:** Detayda şu an tek "Hedef fiyat" kutusu var.

- Üç seçenek: **Hedef fiyat** · **Yüzde düşüş** · **Dip kırılınca** (varsayılan açık)
- Yüzde seçilince *canlı önizleme*: "%15 → yaklaşık ₺2.428 ve altı" (medyandan
  hesaplanır). Soyut sayıyı somuta çevirir
- Yeniden kurma süresi: `3g · 7g · 30g · hiç`
- Altta tek cümle özet: "₺5.500 altına inince ya da 90 günlük medyanın %15
  altına düşünce haber verilir; uyarıdan sonra 7 gün susar."

**Kabul ölçütleri**

- [x] Önizleme yazarken anlık güncelleniyor
- [x] Geçmiş yetersizken yüzde seçeneği pasif ve sebebi yazıyor
- [x] Özet cümlesi seçili kuralları doğru anlatıyor

---

### E4 — Yeniden kurma (rearm) görünür olsun

**Tür:** arka uç + arayüz · 3 saat
**Neden:** Bekleme süresi mantığı worker'da var ama kullanıcı ne görebiliyor ne
değiştirebiliyor. Keepa'da bu birinci sınıf bir ayar.

- `yeniden_kur_gun` `_hatirlatma_zamani`'nda kullanılır
- Kartta ve detayda: "3 gün sonra yeniden uyarır" veya "susturuldu — 12 Eylül'e kadar"
- Tek tıkla "şimdi yeniden kur"

**Kabul ölçütleri**

- [x] Süre dolunca aynı ürün için tekrar uyarı çıkıyor
- [x] "hiç" seçilirse bir daha çıkmıyor
- [x] Kalan süre doğru gösteriliyor

---

### E5 — Bot tarafında da aynı kurallar

**Tür:** arka uç · 3 saat
**Neden:** Telegram botundan hedef konabiliyor; yüzde kuralı eklenince bot
geride kalırsa iki arayüz ayrışır.

**Dosyalar:** `keepmoney/bot/uygulama.py` · `keepmoney/bot/kartlar.py` · `tests/test_bot.py`

- Ürün kartına "%15 düşünce" düğmesi
- Mevcut regresyon testi (üretilen ile işlenen callback kodlarını karşılaştıran)
  yeni düğmeleri de kapsayacak — **ölü düğme kalmayacak**

**Kabul ölçütleri**

- [x] Botta üretilen her callback kodunun bir işleyicisi var
- [x] Bottan kurulan kural webde görünüyor

---

## EPİK F · Set ve mağaza

*4 task · ~1,5 gün*

### F1 — Bütçe aşımını göster

**Tür:** arayüz · 2 saat
**Neden:** "₺104.826 / bütçe ₺90.000" — çubuk dolu gri, ne kadar aştığı yazmıyor.

- "₺14.826 aşıyor (%16)" — kırmızı, çubuğun yanında
- Bütçeye sığmak için düşmesi gereken miktar da yazılır
- Üye listesinde en pahalı üye işaretli
- Üye satırlarına sinyal rozeti (A6) — hangisinin şu an iyi fiyatta olduğu
  setin içinde görünsün

**Kabul ölçütleri**

- [x] Aşımda kırmızı, altındayken yeşil
- [x] Bütçesiz sette hiçbiri görünmüyor

---

### F2 — Set fiyat geçmişi

**Tür:** arka uç + arayüz · 4 saat
**Neden:** Setin bugünkü toplamı var, *geçmişi* yok. "Bu PC geçen ay ne kadardı"
ürünün en doğal sorusu ve rakiplerde karşılığı olmayan grafik.

- `GET /api/setler/{id}/gecmis` — gün başına üye toplamı
- Üye fiyatı bilinmeyen günler **eksik işaretlenir**, sıfır sayılmaz — eksik
  toplamı çizmek yanıltır
- Bütçe hedefi yatay çizgi olarak grafikte

**Kabul ölçütleri**

- [x] Eksik günler grafikte kesik
- [x] Üye eklenip çıkarılınca geçmiş yeniden hesaplanıyor

---

### F3 — Mağaza karşılaştırma tablosu

**Tür:** arayüz · 3 saat
**Neden:** Detayda kaynaklar sadece host adı olarak listeleniyor. Üç mağazada
izlenen ürünün kararı burada verilir.

- Kolonlar: mağaza · güncel fiyat · son okuma · durum · **en ucuz** işareti · git
- Okunamayan kaynak **sebebiyle** görünür (bot duvarı / stokta yok / ölü link)
  — şu an 6 kaynak `ENGELLI`
- Bot duvarındaki kaynakta doğrudan "akakçe kaynağı ara" düğmesi (mevcut
  `KaynakOnerileri` akışına bağlanır)

**Kabul ölçütleri**

- [x] En ucuz mağaza işaretli
- [x] Her okunamayan kaynağın sebebi yazıyor

---

### F4 — Set şablonları

**Tür:** arayüz · 3 saat
**Neden:** `WatchSet.sablon` sütunu var ama arayüzde hiç kullanılmıyor — yarım
kalmış özellik.

- Set kurarken şablon: "PC Toplama" (CPU, GPU, RAM, SSD, PSU, kasa, monitör…),
  "Ev kurulumu", "Boş"
- Şablon **kontrol listesi** yaratır: hangi parça eksik görünür
- Eksik parça "henüz eklenmedi" olarak görünür, sette hedefi engellemez

**Kabul ölçütleri**

- [x] Şablonlu sette eksik parçalar listeleniyor
- [x] Şablonsuz set eskisi gibi çalışıyor

---

## EPİK G · Bildirimler

*3 task · ~6 saat*

### G1 — Güne göre grupla

**Tür:** arayüz · 2 saat
**Neden:** Düz liste; uyarı biriktikçe okunmaz hâle gelir.

- "Bugün · Dün · Bu hafta · Daha eski" başlıkları, yapışkan
- Sıralama **kararlı** kalmalı — sayfalama kırılmasın

### G2 — Türe göre süz

**Tür:** arka uç + arayüz · 2 saat

- Süzgeç: hedef · düşüş · set · bozuk kaynak · okunmamış
- `GET /api/uyarilar?tur=HEDEF` parametresi
- Ürüne göre daraltma: "yalnızca bu ürünün uyarıları"

**Kabul ölçütleri**

- [x] Süzgeçle sayfalama birlikte doğru çalışıyor
- [x] Geçersiz `tur` değerinde 422

### G3 — Uyarıdan tek tıkla eylem

**Tür:** arayüz · 2 saat
**Neden:** Uyarı geldi, kullanıcı ne yapacak? Şu an tek yol ürüne gidip elle
ayar değiştirmek.

- Her uyarıda: **Mağazaya git** · **7 gün sustur** · **Takipten çıkar**
- "Mağazaya git" o an **en ucuz** kaynağa gider, ilk eklenene değil
- Yıkıcı olan (takipten çıkar) onay ister

---

## EPİK H · Dışa aktarma ve bakım

*2 task · ~4 saat*

### H1 — CSV dışa aktarma

**Tür:** arka uç + arayüz · 2 saat

- `GET /api/izlemeler/{id}/gecmis.csv` ve tüm liste için `/api/izlemeler.csv`
- Ayraç **noktalı virgül**, ondalık **virgül** — Türkçe Excel böyle bekliyor;
  virgüllü CSV tek kolona düşer
- UTF-8 **BOM ile**, yoksa Excel Türkçe karakterleri bozuyor

**Kabul ölçütleri**

- [x] Türkçe Excel'de açınca kolonlar ayrı ve karakterler doğru
- [x] Başkasının verisi inmiyor

### H2 — Panel ilk açılış rehberi

**Tür:** arayüz · 2 saat
**Neden:** Boş panelde tek satır var. Yeni kullanıcı ne yapıştıracağını, ne
zaman sinyal geleceğini bilmiyor — A7'deki bulgunun devamı.

- Üç adım: link yapıştır → sinyal birikirken bekle → uyarı kur
- Örnek link (tıklayınca kutuya dolar)
- İlk ürün eklenince rehber kaybolur, geri gelmez

---

## 3. Çalışma sırası

Bağımlılıklar gerçek: A1 olmadan A4 yazılamaz, A olmadan D anlamsız.

| Sıra | Task | Neden bu sırada | Süre |
|---|---|---|---|
| 1 | A1 → A2 → A3 | Sütunlar + worker + doldurma. Bunlar bitmeden görünen hiçbir şey yapılamaz | 6sa |
| 2 | A4 → A6 → A7 → A8 | Sinyal listeye çıkar. **İlk görünür sıçrama burada** | 10sa |
| 3 | A5 + kıvılcım | Kart tamamlanır. Ayrı uç olduğu için A8'den sonra da eklenebilir | 3sa |
| 4 | B1 | İki saatlik iş, grafiği anında daha kullanışlı yapar | 2sa |
| 5 | C1 → C2 → C4 | Liste kontrolü. C4 sayaçları C2 süzgeçlerine bağlı | 8sa |
| 6 | D1 → D2 → D3 | Fırsatlar; A bitmişse neredeyse bedava | 6sa |
| 7 | E1 → E2 → E3 → E4 → E5 | Uyarı kurma. E5 atlanırsa bot ile web ayrışır | 14sa |
| 8 | B2 → B3 | Mağaza çizgileri. Bot duvarları bağlanmadan çoğu üründe tek çizgi kalır | 7sa |
| 9 | F1 → F3 → F2 → F4 | Set ve mağaza. F1 iki saatlik, en görünür olanı | 12sa |
| 10 | G1 → G2 → G3 · B4 → B5 · C3 · H1 → H2 | Cilalama; sıra kritik değil | 18sa |

### Paralel yürüyen iş

**Sekiz bot duvarı ürününe akakçe kaynağı bağlamak.** Arayüz katmanı değil ama
arayüzün göstereceği veriyi belirliyor: 21/35 üründe fiyat varken B2/B3'ün
mağaza çizgileri çoğu üründe tek çizgi olarak kalır.

**Worker'ın sürekli açık kalması.** Sinyal 7 günlük geçmiş istiyor, kıvılcım 90
gün. Şu an en uzun geçmiş **3 gün** — yani A epiği bittiğinde bile ekranlar bir
hafta boyunca "geçmiş biriktiriliyor" gösterecek. Bu bir arıza değil, A7 tam
olarak bunun için var.


---

## 4. Yapılmayacaklar

Klon yapmak, işe yaramayanı da kopyalamak değil. Bunlar bilinçli olarak dışarıda:

- **Satış sırası, Buy Box, teklif sayısı, satıcı istatistikleri.** Hepsi Amazon
  satıcısının araçları. Bizim kullanıcımız satıcı değil alıcı — bu grafikleri
  eklemek arayüzü Keepa'nın "bilgi çorbası" diye eleştirilen tarafına götürür.
- **Product Finder / katalog tarama.** Milyonlarca ürünlük katalog gerektirir.
  Bizim modelimiz "kullanıcı linki yapıştırır" — eksiklik değil, farklı ve daha
  savunulabilir bir konum.
- **Grafiği çizgi çorbasına çevirmek.** Üstünlüğümüz analizi *cümleye*
  çevirmek. Çizgi eklerken bu kaybedilmemeli (bkz. B3'ün varsayılanı).
- **Ücretli katman — şimdilik.** Ödeme, fatura, iade süreci demek. Okuma oranı
  %54'ken para almak konuşulmaz.

---

## 5. Kapanış denetimi — 31 Ağustos 2026

34 task "bitti" işaretlenmeden önce ölçütler **canlı koda karşı** koşturuldu.
Belgeye ve commit mesajlarına güvenilmedi.

### Nasıl doğrulandı

- **26 arka uç ölçütü** (A1, A4, A5, B2, B4, D1, G2, H1 + yetki) gerçek HTTP
  çağrıları, gerçek veritabanı ve SQLAlchemy sorgu sayacıyla tek tek
  koşturuldu — **26/26 geçti**. Sorgu bütçeleri ölçüldü, tahmin edilmedi:
  liste ucu 4 SELECT, kıvılcım ucu tek `price_readings` sorgusu, detay 7,
  fırsatlar 4.
- **21 arayüz ölçüt grubu** için her birinin dayandığı iddia bulundu
  (E2E ya da vitest). Ölçütü olan ama testi olmayan madde ÇIKMADI.
- **OpenAPI şemasındaki 37 ucun tamamı** test dosyalarına karşı tarandı.
  Üçü hiçbir testte geçmiyordu — `POST /api/uyarilar/hepsi-okundu`,
  `POST /api/auth/telegram/baglanti`, `DELETE /api/auth/telegram`. Üçü de
  arayüzde kullanılıyor; testleri yazıldı
  (`tests/test_kapsam_bosluklari.py`). En kritiği `hepsi-okundu`:
  kullanıcı süzgeci düşürüldüğünde BÜTÜN kullanıcıların uyarılarını okundu
  işaretliyor ve hiçbir hata vermiyor — mutasyonla doğrulandı.
- Çapraz kullanıcı erişimi dört uçta da 404; korumalı sekiz uç kimliksiz
  401.

### Denetimde çıkan üç güvenlik bulgusu — üçü de düzeltildi

1. **`X-Forwarded-For` ile hız sınırı tamamen atlatılabiliyordu.** ÖLÇÜLDÜ:
   her istekte farklı bir başlıkla 40 başarısız giriş denemesinin 40'ı da
   401 döndü, tek bir 429 çıkmadı (limit 8). Başlığa artık yalnızca
   `KEEPMONEY_GUVENILEN_VEKILLER` içindeki bir kaynaktan gelirse güvenilir.
2. **Parola sıfırlamak açık oturumları düşürmüyordu.** ÖLÇÜLDÜ: sıfırlamadan
   sonra eski token `/api/auth/ben`den hâlâ 200 alıyordu. `users.oturum_surumu`
   sayacı eklendi (göç `c5f2a71e8d40`).
3. **`/metrics` kimliksiz açıktı.** `KEEPMONEY_METRIK_TOKENI` geldi; üretimde
   token yoksa uç kapanıyor.

Ayrıca `compose.yaml` 8000 ve 9100'ü tüm arayüzlere yayınlıyordu; ikisi de
`127.0.0.1`e bağlandı.

### Yan bulgu: `users` tablosunu yeniden kuran göç patlıyor

`op.batch_alter_table("users")` SQLite'ta tabloyu yeniden kuruyor ve
`PRAGMA foreign_keys=ON` altında gerçek veri varken
`sqlite3.IntegrityError: FOREIGN KEY constraint failed` veriyor. Boş
veritabanında hiç görünmüyor. Yeni göç iki yönde de yerel `ALTER TABLE`
kullanıyor; `tests/test_gocler.py` bunu veriyle kalıcı olarak sınıyor.

### Ürün olarak yayına açmadan önce kalanlar — KOD İŞİ DEĞİL

- **KVKK/gizlilik metni ve kullanım şartları yok.** E-posta topluyoruz; bu
  repo hukuki metin üretmez. Yayına açmadan önce zorunlu.
- **Ters vekil + TLS kurulumu.** Uygulama HTTP konuşuyor, TLS sonlandırması
  vekilin işi. `KEEPMONEY_GUVENILEN_VEKILLER` o vekile göre doldurulmalı.
- **E-posta doğrulama zorunlu değil.** Bayrak var, gösteriliyor, ama hiçbir
  ucu kapatmıyor — bilinçli bırakıldı (bildirimler Telegram'dan gidiyor).
- **Ortaklık etiketleri boş.** Programlara kaydolunca `siteler/*.yaml`e yazılır.
- **Tek instance.** Hız sınırı ve Prometheus kayıt defteri süreç belleğinde.


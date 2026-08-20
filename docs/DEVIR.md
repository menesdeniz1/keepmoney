# Devir Dokümanı — KeepMoney

Bu belge, projeyi **bulut oturumundan lokale** taşırken yazıldı. Sohbet
geçmişi sıfırlanacağı için burada duran şey "ne var" değil, **"neden öyle" ve
"sırada ne var"**. Kod zaten okunabilir; kaybolan şey karardır.

Üç belge birlikte okunur:

| Belge | Ne anlatır |
|---|---|
| **DEVIR.md** (bu) | Durum, sıradaki iş, tuzaklar, çalışma ritmi |
| [`MIMARI.md`](MIMARI.md) | 57 tasarım kararı ve gerekçesi (K1–K57) |
| [`CALISTIRMA.md`](CALISTIRMA.md) | Kurulum, çalıştırma, seçici doğrulama, canlıya alma |

---

## 0. Yeni oturuma verilecek prompt

Aşağıdakini olduğu gibi yapıştır:

```
KeepMoney projesinde çalışıyoruz. Önce şunları oku:
  docs/DEVIR.md   — durum, sıradaki iş, tuzaklar (BURADAN BAŞLA)
  docs/MIMARI.md  — K1–K57 tasarım kararları
  docs/CALISTIRMA.md — kurulum ve çalıştırma

Ben Windows'tayım, PowerShell kullanıyorum, proje
C:\Users\enes\Desktop\myprojects\keepmoney altında. Ana dal: main.

DEVIR.md §4'teki "Sıradaki iş" listesinin ilk maddesinden başla.
```

---

## 1. Proje ne yapıyor

Türkiye pazarı için **Keepa benzeri fiyat takipçisi**. Kullanıcı bir ürün
linki yapıştırır; sistem fiyatı düzenli okur, geçmişini tutar, **"gerçekten
ucuzladı mı yoksa şişirilmiş indirim mi"** ayrımını yapar ve hedefe düşünce
haber verir.

Üç yüzü var: **web arayüzü** (React), **Telegram botu** (isteğe bağlı),
**tarama motoru** (worker).

Öncül proje: [`menesdeniz1/tracker`](https://github.com/menesdeniz1/tracker) —
tek dosyalık, Telegram-only, üretimde aylarca çalıştı. KeepMoney onun
katmanlı ve çok kullanıcılı yeniden yazımı. **tracker'ın öğrendiği bilgiler
kıymetlidir**; port sırasında birkaçı kaybolmuştu ve gerçek denemelerde
tek tek geri getirildi (bkz. §5).

---

## 2. Durum — ölçülmüş, tahmin değil

### Kod ve testler

- **627 test yeşil** (backend + arayüz + gerçek tarayıcıyla uçtan uca)
- **CI 7 iş**, hepsi yeşil: `test`, `windows`, `postgres`, `tarayici-motoru`,
  `uctan-uca`, `arayuz`, `imaj` (Docker imajı derlenip container ayağa
  kaldırılıyor, chromium ve arayüz doğrulanıyor)
- **57 mimari karar** belgeli (`MIMARI.md`)
- Son commit: `3c5f616`

### Gerçek linklerle okuma oranı

18 gerçek link, `betikler/kaynak_dene.py --dosya linkler.txt`:

| Site | Sonuç | Not |
|---|---|---|
| akakce.com | **3/3** | + 16 satıcı pazar derinliği okunuyor |
| amazon.com.tr | **6/7** | Kalan tek bilinmeyen (§4.2) |
| trendyol.com | **1/1** | |
| n11.com | **1/1** | |
| ikea.com.tr | **1/1** | Kural dosyası yok, varsayılan zincir |
| idefix.com | **1/1** | Kural dosyası yok, varsayılan zincir |
| hepsiburada.com | 0/1 | Bot duvarı 403 — **tasarım gereği akakçe'den okunuyor** |
| shop.nurus.com | 0/1 | Shopify bot duvarı |
| wraithesports.com | 0/1 | Shopify bot duvarı |
| vatanbilgisayar.com | 0/1 | **Link ölü** (HTTP 200 + "404 File not found") |

**Ham oran %72. Ama okunamayan 5 satırın 4'ü kod hatası DEĞİL:** üçü bot
duvarı (toplayıcıya yönlendirilir — Hepsiburada'nın fiyatını akakçe zaten
veriyor), biri kullanıcının verdiği ölü link. Gerçek bilinmeyen **1 tane**.

Bu ayrımı rapor artık kendisi yapıyor (§5.9).

### Uçtan uca doğrulanmış akışlar

Gerçek uvicorn + SQLite + gerçek HTTP ile denendi:

- Kayıt → giriş → ürün ekleme → listeleme
- **Kanonik URL birleştirme (K16):** aynı ASIN'in üç farklı biçimi
  (`/slug/dp/ASIN/ref=...`, `/gp/product/ASIN?th=1&psc=1&utm_...`) **tek
  kaynağa** düştü → `https://amazon.com.tr/dp/B0BSLHZKB6`, tek ürün
- Tarama turu (`Tarayici.tur_calistir`)
- **Bozuk kaynak uyarısı:** 3. üst üste hatada tam bir kez tetikleniyor,
  tekrarlamıyor

### Doğrulanmamış tek alan

**Zaman içindeki davranış.** Worker hiç günlerce çalışmadı. Grafikler
oluşuyor mu, uyarılar doğru anda mı geliyor, veritabanı nasıl büyüyor —
bunlar ancak çalıştırılarak öğrenilir. **Kalan en büyük bilinmeyen budur.**

---

## 3. Mimari — bir sayfada

```
sunum      api/ (FastAPI)      bot/ (aiogram)      arayuz/ (React 19 + Vite)
              │                    │
uygulama      └──── servisler/ ────┘        izleme, urun, uyari, setler, kullanici
                        │
alan          analiz · karar · fiyat · zaman        SAF PYTHON, bağımlılık yok
                        ▲
altyapı       models · db · ayikla · cekici · siteler · throttle · robots · toplayici
```

Bağımlılık **içe doğru**. Alan katmanı hiçbir şey bilmez; test edilmesi en
kolay ve en kritik yer orasıdır.

### Bilinmesi zorunlu dört kavram

**1. Kanonik URL = küresel ürün kimliği (K16).** İki kullanıcı aynı ürünü
farklı linkle eklerse **aynı kayda** düşmeli. Bölünme bu üründeki en pahalı
sessiz hatadır: fiyat geçmişi ikiye ayrılır, "en düşük fiyat" yanlış hesaplanır
ve kimse fark etmez. `servisler/izleme.py::url_normalize`.

**2. Güven zinciri.** `json-ld → secici → meta → regex`. Regex **son çare** ve
düşük güven: sayfadaki ilk `12.345,67 TL` kalıbını alır — taksit tutarı,
kargo bedeli veya sponsorlu ürün olabilir. `metin_alani` ile kapsamı daraltılır;
o seçici sayfada yoksa regex adımı **atlanır** (yanlış fiyattansa "yok" doğrudur).

**3. Yükselme merdiveni.** `requests → cloudscraper → playwright`. Kritik ayrım:
**başarılı ≠ kullanılabilir**. Bot duvarları HTTP 200 ve dolu gövdeyle gelir;
`_kullanilabilir()` içeriğe bakar, yoksa merdiven ilk basamakta dururdu.

**4. Toplayıcı önceliği (akakçe).** Tek sayfada N satıcının en ucuzu.
Hepsiburada/n11 gibi sert bot duvarlı mağazaların fiyatına ulaşmanın **en
sağlam yolu**. Ayrıca "kaç satıcı var, ikincisi kaça" bilgisi, fiyat geçmişi
olmayan üründeki **tek uyarı işaretidir** (K52).

---

## 4. Sıradaki iş — öncelik sırasıyla

### 4.1 ⭐ TEK TIK KURULUM VE ÇALIŞTIRMA (ilk yapılacak)

**Problem:** Kullanım şu an elle ve kırılgan. Kullanıcı iki ayrı PowerShell
penceresi açmak, ikisinde de `cd` yapıp sanal ortamı etkinleştirmek, sonra
iki ayrı komut çalıştırmak zorunda. Gerçek kullanımda tam da burada takıldı:
yeni pencere `C:\WINDOWS\system32`'de açıldı, `.\.venv\Scripts\Activate.ps1`
bulunamadı, komutlar sistem Python'ında çalıştı ve worker **tarayıcı motoru
olmadan** açıldı — hiçbir üründen fiyat gelmedi.

**Öncül projede bu vardı ve porta taşınmadı.** `tracker/kur.bat` ve
`tracker/calistir.bat` dosyalarına bak — çift tıkla çalışan, `cd /d "%~dp0"`
ile kendi klasörüne geçen, Python yoksa açık hata veren betikler. Aynı
yaklaşım buraya da gelmeli.

**Yapılacak:**

- `kur.bat` — çift tıkla ilk kurulum: Python kontrolü, `.venv` oluşturma,
  `pip install -r requirements.txt`, **playwright + chromium**, `.env`
  oluşturma + JWT anahtarı üretip içine yazma, `alembic upgrade head`,
  arayüz derleme (`npm ci && npm run build`), `statik/` kopyalama.
- `basla.bat` — çift tıkla çalıştırma: kendi klasörüne geçer, sanal ortamı
  kullanır (**aktive etmeye gerek bırakmadan**, doğrudan
  `.venv\Scripts\python.exe` çağırarak), API ve worker'ı **iki ayrı pencerede**
  başlatır (`start` komutu), sonra tarayıcıda `http://localhost:8000` açar.
- `dur.bat` — ikisini de kapatır.

**Tasarım kuralları:**
- `cd /d "%~dp0"` ilk satır olmalı — nereden çalıştırılırsa çalıştırılsın
  doğru klasöre geçsin (kullanıcının takıldığı yer tam olarak buydu).
- **Sanal ortamı aktive etmeye çalışma**, `.venv\Scripts\python.exe`'yi
  doğrudan çağır. `Activate.ps1` PowerShell çalıştırma politikasına takılıyor
  ve bu tuzağa iki kez düşüldü.
- Eksik olan her şey için **açık ve çalıştırılabilir** hata mesajı ver.
  Sessiz devam etme — worker'ın tarayıcısız açılıp hiçbir şey okumaması tam
  olarak bu yüzden oldu.
- Testleri de yaz: `.bat` içeriği doğrudan test edilemez ama betiklerin
  çağırdığı Python tarafı (anahtar üretme, ortam doğrulama) test edilebilir.
  Mümkünse mantığı `betikler/kurulum.py` içine al, `.bat` yalnızca onu çağırsın.

### 4.2 Amazon MSI monitör — tek gerçek bilinmeyen

`https://amazon.com.tr/dp/B0BSLHZKB6` — okunamıyor. Bilinenler:

- Sayfa **1451 KB**, başlık ve `h1` doğru → captcha değil, doğru ürün sayfası
- Altı `fiyat_secici` seçicisinin altısı da **0 eşleşme**
- `#centerCol` **var ama 1134 karakter** (buybox'lı normal sayfada binlerce)
- Kolon metninde ürün adı, puan, enerji sınıfı ve buybox'ın **"Güvenli işlem ·
  İade Politikası" dipnotu** var — ama fiyat satırı yok
- Fiyat adaylarının hepsi `sp_detail_* < anonCarousel1` (sponsorlu karusel)

**Denenen ve İŞE YARAMAYAN:** fiyat elemanı için ek bekleme eklendi
(`cekici.py::_fiyati_bekle`). Süre 4,8sn → 9,9sn çıktı, yani ek bekleme
çalıştı ama eleman hiç gelmedi. **Zamanlama hipotezi çürütüldü.** (Düzeltme
yine de kaldı: yavaş sayfalara karşı doğru bir koruma ve testi var.)

**Sıradaki adım:** `--incele` artık aday listesini kesmiyor ve yabancı
olmayanları öne alıyor; yeniden kaydedilmiş HTML'de bakılmalı. Sayfada
başka bir yerde (ör. "Diğer satıcılar") fiyat var mı?

**Ama acele etme:** akakçe aynı ürünü **25.999,00** okuyor ve 16 satıcı
gösteriyor. Ürünün pratik cevabı zaten var. Bu bir *merak*, blokaj değil.

### 4.3 Worker'ı günlerce çalıştır — asıl bilinmeyen

Kalan tek doğrulanmamış alan. `basla.bat` yazıldıktan sonra birkaç gün açık
bırak, sonra bak:

- Fiyat geçmişi grafikleri oluşuyor mu
- Uyarılar mantıklı mı — özellikle **yanlış "dibe vurdu" uyarısı** var mı
- `tarama_turu` log satırlarında `basarisiz` sayısı zamanla artıyor mu
- Veritabanı boyutu

### 4.4 Hiç gerçek sayfayla denenmemiş siteler

`incehesap`, `itopya`, `mediamarkt`, `cimri`, `tebilon`, `sinerji` — kural
dosyaları var ama **hiç gerçek linkle sınanmadı**. Seçiciler tracker'dan
geldi veya tahmin. `cimri_com.yaml` bu durumu açıkça yazıyor ve bir test
onu zorunlu tutuyor.

Kullanıcı zamanla link ekleyecek. **Sen kendin link uydurma** — gerçek
sayfayla doğrulanmamış seçici, doğrulanmış gibi görünür ve daha kötüdür.

### 4.5 Trendyol/Hepsiburada kanonik URL kuralı — KANIT BEKLİYOR

Amazon'da `kanonik_yol_kalibi` ile çözülen ürün-bölünmesi sorunu bu sitelerde
de olabilir (`-p-<id>` kimliği, değişken slug). **Ama kanıt yok.** Amazon'daki
bölünmeyi kullanıcının gerçek link listesi göstermişti.

**Yanlış yazılan bir kural iki AYRI ürünü birleştirir — bölmekten beter,
çünkü yanlış ürünün fiyatı doğru ürünün geçmişine yazılır.** Kanıt gelmeden
dokunma.

---

## 5. Tuzaklar — hepsi gerçek denemelerde yakalandı

Bunlar teorik değil; her biri çalışan bir sistemde ortaya çıktı ve çoğu
**sessizdi** (hata vermedi, yanlış sonuç üretti).

**5.1 — Sentetik test ≠ gerçek site.** 422 test yeşilken gerçek linklerin
%75'i okunamıyordu. Testler ayıklayıcının *doğruluğunu* ölçer, sitenin *bugün
ne döndürdüğünü* değil. `kaynak_dene.py` bu boşluk için var ve **atlanamaz**.

**5.2 — Kanonik URL bölünmesi.** `?srsltid=` (Google Shopping tıklama kimliği,
her tıklamada değişir), `/ref=` yol eki, `/slug/dp/ASIN` ile `/dp/ASIN` farkı.
Hepsi gerçek link listelerinde yakalandı. **Ama `variant=` ATILMAZ** —
Shopify'da varyant ayrı üründür.

**5.3 — Başarılı ≠ kullanılabilir.** Bot duvarları HTTP 200 döner. İki Shopify
mağazası 0,7 saniyede "bot koruması" sonucu vermişti — o süre tek bir
`requests` çağrısıdır, yani tarayıcı hiç denenmemişti.

**5.4 — Regex fiyatı "okundu" görünür ama arıza olabilir.** Seçicisi OLAN bir
sitede regex'e düşmek, seçicinin KIRILDIĞI anlamına gelir. Gerçek bir koşuda
Amazon'dan 9.999,23 okunurken akakçe aynı ürüne 6.370 diyordu.

**5.5 — Sessiz devre dışı kalma.** `metin_alani` sayfada yoksa hem regex son
çaresi hem "stokta yok" araması **sessizce kapanır**. `saticilar_secici`
kırılırsa "tek satıcı aykırı ucuz" koruması sessizce kapanır. Tanı aracı
ikisini de artık raporluyor.

**5.6 — Yumuşak 404.** vatanbilgisayar kaldırılmış ürüne **HTTP 200** ile
"404 - File or directory not found" başlıklı sayfa döndürüyor. Tek işaret
`<title>`.

**5.7 — Güvenlik sezgiselinde yanlış pozitif (K57).** Belgelerimizin önerdiği
komutla üretilmiş geçerli bir JWT anahtarı reddedildi (içinde şans eseri
"ornek" geçiyordu). Ölçüldü: **1/182.000**. Eşikler tahminle değil **ölçülerek**
seçilir; yanlış pozitifi azaltan her değişiklik "gerçek tehdidi hâlâ yakalıyor
muyum" karşı testiyle gelir.

**5.8 — Boş cevabın tek anlamı olmalı (K56).** Toplayıcı araması ağ hatasını,
bot duvarını ve gerçekten sonuç olmamasını aynı `200 []` ile bildiriyordu;
ekranda üçü de "eşleşme bulunamadı" oluyordu. Bir ağ hatası, ürünün hiçbir
yerde satılmadığı gibi görünüyordu.

**5.9 — Rapor her satırı arıza saymamalı.** 5 okunamayan satır, ürün beş
yerinden bozukmuş izlenimi veriyordu; gerçekte 1 gerçek iş vardı. Yanlış
önceliklendirme pahalıdır.

**5.10 — Kendi tanı aracımda eksik kanıttan kesin hüküm.** Aday listesi 8'de
kesiliyor ama "TÜM fiyatlar sponsorlu" hükmü o kesik liste üzerinden
veriliyordu. Sponsorlu karusel DOM'da erken geldiği için sekiz yeri de o
dolduruyordu.

**5.11 — Windows farklıdır.** Sistem tz veritabanı yok (`tzdata` zorunlu),
NTFS'te `:` içeren dosya adı sessizce alternate data stream'e yazar, stdout
cp1252 olduğu için Türkçe çıktı `--help`'te bile çökebilir. CI'da ayrı bir
`windows` işi var — **kaldırma**.

**5.12 — Playwright "opsiyonel" değil.** `requirements.txt`'te yorum satırında
duruyor çünkü API onu kullanmıyor. Ama **worker onsuz Türkiye'nin ana
sitelerinin hiçbirinden fiyat okuyamaz**. Gerçek kurulumda bu atlandı; worker
tek satır uyarı verip çalışmaya devam etti ve hiçbir üründen fiyat gelmedi.

---

## 6. Çalışma ritmi ve kurallar

### Kullanıcı hakkında

- Windows / PowerShell, `C:\Users\enes\Desktop\myprojects\keepmoney`
- Ana dal **`main`**. Sen commit'ler ve push'larsın, o `git pull` yapar
- Türkçe konuşuyor; **kod, yorum, commit mesajı, belge hepsi Türkçe**
- Uzun teorik anlatım istemiyor. **Somut adım ve gerekçe** istiyor
- Haklı olarak "optimumu bozma" diyor: **düzeltilemeyecek şeyi zorlama**

### Kod kuralları

- SOLID / DRY / KISS, katmanlı mimari, bağımlılık içe doğru
- Yorumlar **NEDEN**'i anlatır, NE'yi değil. Gerçek bir vakadan geliyorsa
  o vakayı yaz — bu depodaki yorumların çoğu böyle ve değeri buradan geliyor
- Modern kütüphaneler, güncel sürümler
- Saat dilimi: **Europe/Istanbul**, Türkiye pazarı, TL

### Asla yapılmayacaklar

Görünürde başarı üretmek için: testi devre dışı bırakmak, kırık testi
gerekçesiz silmek, özelliği yorum satırına almak, istisnayı yutmak, işlevi
sahteyle değiştirmek, cevabı sabit kodlamak, lint kuralını global kapatmak,
güvensiz tip bastırma eklemek, güvenlik uyarısını yok saymak, doğrulamayı
kaldırmak, derleyici hatasını gizlemek, yer tutucu veri döndürmek,
**çalıştırmadan "bitti" demek**.

Gizli bilgi (anahtar, token, parola) **asla** commit edilmez. `.env` git'e
girmez; `.env.example` yalnızca güvenli yer tutucu içerir.

### Her değişiklikten sonra

```powershell
pytest -q                    # 627 test
ruff check .
cd arayuz ; npm run lint ; npx tsc --noEmit ; npm test ; cd ..
```

Push ettikten sonra **CI'ı KONTROL ET**. Bir dönem üç commit boyunca CI
kırmızıydı ve fark edilmedi — çünkü yalnızca yerel testler koşturuluyordu.

### Gerçek link denemesi

```powershell
python betikler/kaynak_dene.py --dosya linkler.txt --html-kaydet hata_html
python betikler/kaynak_dene.py --incele hata_html\<dosya>.html
```

`--incele` ağa çıkmaz; kaydedilmiş HTML'i istediğin kadar çözümleyebilirsin.
Seçici yazarken gereken döngü budur.

---

## 7. Hızlı dosya haritası

| Yol | Ne |
|---|---|
| `keepmoney/ayikla.py` | Fiyat/başlık/stok çıkarımı, güven zinciri, pazar derinliği |
| `keepmoney/cekici.py` | Yükselme merdiveni, SSRF korumalı yönlendirme, Playwright |
| `keepmoney/karar.py` | Şüpheli fiyat, aykırı pazar, uyarı kararları |
| `keepmoney/servisler/izleme.py` | **Kanonik URL** (K16), kaynak ekleme |
| `keepmoney/worker.py` | Tarama turu, bozuk kaynak tespiti, uyarı üretimi |
| `keepmoney/toplayici.py` | Akakçe araması (öneri sunar, **otomatik bağlamaz**) |
| `keepmoney/siteler/*.yaml` | Site kuralları — düzeltme kod değil config işidir |
| `betikler/kaynak_dene.py` | **Tanı aracı.** En çok kullanılan dosya |
| `arayuz/src/` | React 19 + TS + Vite + TanStack Query |

---

*Son güncelleme: bu belge yazıldığında son commit `3c5f616`, 627 test yeşil,
CI 7/7 yeşil.*

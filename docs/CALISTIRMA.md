# Çalıştırma Kılavuzu

Bu belge **sıfırdan çalışır hale getirme** ve **canlıya alma** adımlarını
anlatır. Mimari kararların gerekçesi için [`MIMARI.md`](MIMARI.md).

Sıra önemli: 1 → 2 → 3 → 4. Üçüncü adım (gerçek linklerle seçici doğrulama)
**atlanamaz** — kodun test edilemeyen tek yanı orasıdır.

---

## 0. Önce elinde ne olmalı

| Gerekli mi | Ne | Nereden | Yoksa ne olur |
|---|---|---|---|
| **Zorunlu** | Python 3.12+ ve Node 22+ | — | Hiçbir şey çalışmaz |
| **Zorunlu** | JWT imza anahtarı | Aşağıdaki komut | Üretimde uygulama **açılmaz** (bilerek) |
| Yerelde opsiyonel<br>Canlıda zorunlu | Sunucu + alan adı + HTTPS | Hetzner/DO/AWS + Cloudflare | Sadece kendi bilgisayarından erişirsin |
| Opsiyonel | Telegram bot token'ı | Telegram'da [@BotFather](https://t.me/BotFather) → `/newbot` | Bot çalışmaz; web arayüzü çalışır |
| Opsiyonel | SMTP hesabı | Resend / Postmark / Amazon SES / Gmail App Password | "Parolamı unuttum" **sessizce** çalışmaz — bağlantı yalnızca loga yazılır |

JWT anahtarını **elle yazma**, üret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Uygulama zayıf anahtarı açılışta reddeder (kısa, tekrarlı ya da "changeme"
içeren değerler). Sebebi: HMAC anahtarı bir parola değil, rastgele bit
dizisidir; zayıfsa saldırgan istediği kullanıcı adına geçerli token üretir.

---

## 1. Yerelde ilk çalıştırma (~5 dakika)

### Windows: çift tıkla (önerilen)

Üç dosya var, üçü de depo kökünde:

| Dosya | Ne yapar |
|---|---|
| **`kur.bat`** | Sanal ortam, paketler, **playwright + chromium**, `.env` + JWT anahtarı, veritabanı şeması, arayüz derlemesi — sonra hepsini **doğrular** |
| **`basla.bat`** | Ortamı kontrol eder, API ve tarama worker'ını **ayrı pencerelerde** başlatır, API cevap verince tarayıcıyı açar |
| **`dur.bat`** | İkisini de kapatır (chromium alt süreçleri dahil) |

İlk sefer `kur.bat`, sonrasında yalnızca `basla.bat`. Depo güncellendiğinde
(`git pull`) tekrar `kur.bat` çalıştır: adımların hepsi tekrar çalıştırılabilir
ve **var olan `.env` anahtarına dokunmaz**.

Bu betikler elle kurulumun kısayolu değil, **tuzaklarına karşı yazılmış hali**:

- `cd /d "%~dp0"` ilk satır — çift tıkla açılan pencere yanlış klasörde
  başlıyordu ve hiçbir göreli yol tutmuyordu,
- sanal ortam **etkinleştirilmiyor**, `.venv\Scripts\python.exe` tam yoluyla
  çağrılıyor — `Activate.ps1` çalıştırma politikasına takılıyor,
- **chromium'un varlığı ayrıca kontrol ediliyor**; eksikse `basla.bat`
  BAŞLATMIYOR. Sebebi aşağıdaki kutu.

Ortamın durumunu tek başına sormak istersen:

```powershell
.\.venv\Scripts\python.exe betikler\kurulum.py dogrula
```

```
 + python paketleri   15 paket
 + saat dilimi        Europe/Istanbul
 + .env               JWT anahtarı yerinde
 + veritabanı şeması  güncel (9b47605c0346)
 + tarayıcı motoru    chromium: chrome-win64
 + arayüz             statik/index.html
```

### macOS: çift tıkla + 7/24 servis

Aynı üç dosyanın macOS karşılığı: **`kur.command`**, **`basla.command`**,
**`dur.command`**. İlk seferde Finder "izin verilmedi" derse Terminal'de:

```bash
chmod +x kur.command basla.command dur.command betikler/macos/kur-servis.sh
```

**Mac'i kişisel sunucu yapmak (7/24):**

```bash
./betikler/macos/kur-servis.sh          # kur ve başlat
./betikler/macos/kur-servis.sh --durum  # çalışıyor mu
./betikler/macos/kur-servis.sh --kaldir # durdur ve kaldır
```

Bu betik `launchd` ile dört iş kurar: `api`, `tarayici`, `bot` (token
varsa) ve her gece 03:30'da **yedek**. Servisler açılışta kalkar ve
**çökerse kendiliğinden yeniden başlar** (`KeepAlive`). Loglar
`data/loglar/` altında.

> **Docker neden değil:** 8 GB'lık bir M1'de Docker Desktop tek başına
> ~2 GB yiyor; üstüne chromium (istek başına ~250 MB) eklenince makine
> sürünür. Tek kullanıcıda SQLite zaten yeterli ve yedeği tek dosya.
> `compose.yaml` duruyor — çok kullanıcılı/sunucu kurulumu için hâlâ
> doğru yol o.

> ### ⚠️ Mac uyursa tarama DURUR
>
> Sistem Ayarları → Kilit Ekranı → "Ekran kapalıyken uyut" = **Asla**,
> ya da `sudo pmset -a sleep 0 disksleep 0`. Kapak kapalıyken çalışması
> için güç kablosu takılı olmalı.

**Telefondan bakmak (aynı Wi-Fi):** `.env` içine

```bash
KEEPMONEY_DINLEME=0.0.0.0
```

yaz, servisi yeniden kur. `basla.command` çalışırken Mac'in adresini
ekrana basar (`http://192.168.x.x:8000`). Telefondan o adrese gir.

> `0.0.0.0` **aynı ağdaki herkes erişebilir** demektir. Ev ağında sorun
> değil; ortak Wi-Fi'da (kafe, otel, yurt) kullanma. Doğrudan internete
> **açma** — hız sınırı ters vekil arkasında olmayı varsayıyor (K24).

Aşağısı **elle kurulum**: Linux/macOS için, ve Windows'ta bir adım
patladığında ne olduğunu görmek için.

**Linux / macOS:**

```bash
git clone https://github.com/menesdeniz1/keepmoney && cd keepmoney

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install playwright && playwright install --with-deps chromium   # ZORUNLU, bkz. aşağıda

cp .env.example .env          # JWT anahtarını içine yaz
mkdir -p data                 # SQLite dosyası buraya
alembic upgrade head          # şemayı kur
```

**Windows (PowerShell):** komutlar AYNI DEĞİL. Gerçek bir kurulumda
`python3`, `source` ve `cp` "tanınmıyor" hatası verdi — Windows'ta bunlar
yok. Doğrusu:

```powershell
git clone https://github.com/menesdeniz1/keepmoney
cd keepmoney

py -3 -m venv .venv                    # `python3` değil, `py`
.\.venv\Scripts\Activate.ps1          # `source` değil
pip install -r requirements.txt
pip install playwright ; playwright install chromium   # ZORUNLU, bkz. aşağıda

Copy-Item .env.example .env            # `cp` değil
New-Item -ItemType Directory -Force data | Out-Null
alembic upgrade head
```

`Activate.ps1` "betik çalıştırma devre dışı" derse, o oturum için izin ver:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

Bundan sonraki tüm komutlarda `python` ve `pytest` doğrudan çalışır (sanal
ortam etkinken). Çıktıyı dosyaya yönlendireceksen `>` yerine
`| Out-File -Encoding utf8 rapor.txt` kullan — PowerShell'in varsayılan
kodlaması Türkçe karakterleri bozar.

> ### ⚠️ Tarayıcı motoru "opsiyonel" DEĞİL
>
> `requirements.txt` içinde playwright yorum satırında duruyor, çünkü API onu
> kullanmıyor. Ama **tarama worker'ı onsuz Türkiye'nin ana sitelerinin
> hiçbirinden fiyat okuyamaz**: akakçe, Amazon, Trendyol, n11, Hepsiburada,
> cimri, tebilon — hepsi `render: true`.
>
> Gerçek bir kurulumda tam olarak bu oldu: `pip install -r requirements.txt`
> yapıldı, worker açıldı ve tek satır uyarı verip çalışmaya devam etti —
> ürünler tarandı, hiçbirinden fiyat gelmedi. Uyarı doğruydu ama ekranın
> yukarısında kalıyordu:
>
> ```
> [warning] tarayici_motoru_yok  etkilenen=['akakce.com', 'amazon.com.tr', ...]
>                                sonuc='bu sitelerden fiyat okunamayacak'
> ```
>
> Kurulu olup olmadığını doğrula:
>
> ```bash
> python -c "import playwright; print('tarayıcı motoru VAR')"
> ```
>
> **Worker'ı sanal ortam ETKİNKEN başlat.** İki ayrı terminalde çalıştığı için
> birini aktive etmeyi unutmak kolay; unutulursa yukarıdaki uyarıyla aynı
> sonuç çıkar (paketler o Python'da yoktur). Komut isteminde `(.venv)` yazmalı.

İki terminal:

```bash
# 1) API
uvicorn keepmoney.api.app:app --reload            # http://localhost:8000

# 2) Arayüz (geliştirme sunucusu, hot reload)
cd arayuz && npm install && npm run dev           # http://localhost:5173
```

Aç: <http://localhost:5173> → kayıt ol → bir ürün linki yapıştır.

> **Fiyat hemen görünmez.** Ürünü ekleyen istek sayfayı çekmez; tarama
> worker'ı çeker. İlk fiyatı görmek için worker'ı da çalıştır:
>
> ```bash
> python -m keepmoney.zamanlayici        # sürekli tarama döngüsü
> ```

API dokümanı: <http://localhost:8000/docs>

### Arayüzü API ile aynı adresten sunmak (üretimdeki biçim)

Geliştirmede Vite ayrı portta çalışır. Üretimde arayüz **derlenir** ve API
aynı kaynaktan sunar — CORS sorunu kalmaz, CSP dar tutulabilir, çerez
`SameSite=lax` ile sorunsuz gider:

```bash
cd arayuz && npm run build && cp -r dist ../statik && cd ..
uvicorn keepmoney.api.app:app                     # arayüz artık :8000'de
```

`statik/index.html` yoksa arayüz **mount edilmez** (yerel geliştirmede
istenen davranış budur). Docker imajı bu adımı kendisi yapar.

---

## 2. Testleri çalıştırma

Dört ayrı katman var; hepsi CI'da koşuyor ([`ci.yml`](../.github/workflows/ci.yml)).

```bash
# Backend — ağ gerektirmez, ~1 dk
pytest -q                                # 595 test

# Arayüz
cd arayuz && npx tsc -b && npx vitest run && npm run lint

# Gerçek tarayıcı gerektirenler (Playwright kurulu olmalı)
pip install playwright && playwright install --with-deps chromium
pytest -q tests/test_playwright.py       # JS ile fiyat yükleyen sayfalar
pytest -q tests/test_e2e_arayuz.py       # gerçek tarayıcı + gerçek sunucu

# PostgreSQL'e karşı aynı paket (üretim veritabanı bu)
docker run -d --name kmpg -e POSTGRES_PASSWORD=km -e POSTGRES_USER=km \
  -e POSTGRES_DB=km -e POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale=C.UTF-8" \
  -p 5432:5432 postgres:17-alpine
KEEPMONEY_TEST_VERITABANI_URL=postgresql+psycopg://km:km@127.0.0.1/km pytest -q
```

> `POSTGRES_INITDB_ARGS` şart. Kodlama belirtilmezse `SQL_ASCII` veritabanı
> oluşabiliyor; psycopg metin yerine bytes döndürüyor ve sürücü katmanı
> patlıyor — üstelik Türkçe karakterler sessizce bozuluyor.

Şema ile migrasyonlar uyuşuyor mu (kolon ekleyip migrasyon üretmeyi unutmak
üretimde eski şemayla çalışmak demektir):

```bash
alembic upgrade head && alembic check
```

---

## 3. ⚠️ Seçici doğrulaması — canlıya çıkmadan önce ZORUNLU

Testlerin kapatamadığı **tek** boşluk bu. Test paketi kayıtlı HTML'e karşı
koşar: "ayıklayıcı doğru yazılmış mı" sorusunu cevaplar, "trendyol.com bugün
hâlâ bu HTML'i mi veriyor" sorusunu **cevaplamaz**. İkincisi ancak gerçek ağa
çıkarak ölçülür.

Ölçmeden canlıya alınırsa ürün sessizce boş çalışır: kullanıcı ekranda bir
şey görür, arkada hiçbir fiyat yazılmamıştır.

```bash
# Site başına 5-10 gerçek ürün linki yaz (her satıra bir tane)
cat > linkler.txt <<'EOF'
https://www.trendyol.com/...
https://www.hepsiburada.com/...
https://www.vatanbilgisayar.com/...
EOF

python betikler/kaynak_dene.py --dosya linkler.txt --html-kaydet hata_html/
```

> **Sanal ortam HER YENİ terminalde yeniden etkinleştirilir.** Etkin değilse
> araç `ModuleNotFoundError` verir — hata koddaymış gibi görünür ama değildir.
> Araç bunu fark edip çalıştırılacak komutu söylüyor; yine de en sık düşülen
> tuzak budur.
>
> ```powershell
> .\.venv\Scripts\Activate.ps1     # Windows
> source .venv/bin/activate         # Linux / macOS
> ```

Çıktı şuna benzer:

```
 + trendyol.com          48.999,90 TL  [json-ld]     requests    1.2sn  Ekran Kartı RTX 5080
 - itopya.com            fiyat okunamadı — `render: true` dene  requests  0.9sn  ...

──────────────────────────────────────────────────────────────────────────
OKUMA ORANI: 8/10  (%80)

Site başına:
  trendyol.com               5/5  TAMAM
  itopya.com                 3/5  KISMİ

Fiyat nereden geldi: json-ld=6, secici=2
```

**Nasıl okunur:**

| Sonuç | Anlamı | Ne yapmalı |
|---|---|---|
| `[json-ld]` | En sağlam kaynak | Bir şey yapma |
| `[secici]` | Site kuralındaki CSS seçici tuttu | Bir şey yapma |
| `[regex]` | ⚠️ Sayfadaki *herhangi* bir sayı olabilir (kargo, taksit) | O siteye `fiyat_secici` yaz |
| `fiyat okunamadı` | Seçici kırık ya da fiyat JS ile geliyor | Aşağı bak |
| `engellendi` | Bot koruması | `render: true` dene; olmuyorsa siteyi çıkar |
| `robots.txt yasaklıyor` | Site izin vermiyor | Siteyi çıkar — buna saygı gösteriyoruz |

### Kırık bir siteyi düzeltmek

Kaydedilen HTML'i **ağa çıkmadan** çözümle — çıkarım zincirinin hangi adımı
neden tuttu/tutmadı, tek tek gösterir:

```bash
python betikler/kaynak_dene.py --incele hata_html/amazon.com.tr-94749959.html
```

```
2) Site seçicisi    : #corePriceDisplay_desktop_feature_div span.a-price ...
   - #corePriceDisplay_desktop_feature_div span.a-price .a-offscreen  → 0 eşleşme
   + #corePrice_desktop span.a-price .a-offscreen  → 1 eşleşme: ['15.049,00 TL']

── Fiyat taşıyan elemanlar (ilk 8) ──
      15.049,00  ←  corePrice_desktop     üst: —
       1.099,00  ←  a-price               üst: oneri_karuseli
```

Sonra `keepmoney/siteler/<domain>.yaml` dosyasını düzelt (yoksa
`_SABLON.yaml`'dan kopyala):

1. **`BOT KORUMASI SAYFASI`** diyorsa seçici yazmanın anlamı yok →
   `render: true` dene; o da tutmazsa siteyi listeden çıkar.
2. **Fiyat taşıyan elemanlar listesinde doğru tutarı görüyorsan**, onun
   `üst:` sütunundaki id'yi kullanarak `fiyat_secici` yaz. Kapsayıcıyı **dar
   tut** — geniş bir seçici öneri karuselindeki başka bir ürünün fiyatını
   yakalar ve bu en sinsi hata türüdür: fiyat okunur ama yanlış üründen.
3. **Liste boşsa** fiyat JS ile geliyor → `render: true`.
4. `--incele` ile tekrar çalıştır (ağa çıkmaz, anında sonuç), doğru olunca
   `--dosya` ile gerçek koşuyu yap.

Bu döngü bilerek çevrimdışı: her denemede siteye istek atmak, tam da
doğrulama yaparken IP'ni yasaklatmanın en hızlı yoludur.

**Kabul eşiği:** genel oran **%90+** ve hiçbir site `KIRIK` değil. Bu
sağlanmadan canlıya alma — çıkış kodu 0/1 olduğu için bunu CI'da eşik olarak
da kullanabilirsin.

Bu ölçüm **tek seferlik değildir**. Siteler HTML'ini haber vermeden
değiştirir; ayda bir tekrarla (aşağıdaki Prometheus ölçümü bunu otomatik
yakalar ama betik nerede kırıldığını doğrudan söyler).

---

## 3.5 Toplayıcıyı (akakçe) kullan — bot duvarını aşmanın yolu

Ölçümde Hepsiburada ve n11 **gerçek tarayıcıyla bile 403** dönüyor. O
mağazaların fiyatına ulaşmanın sağlam yolu toplayıcı sayfasıdır ve akakçe
bizi engellemiyor.

Arayüzde ürün detayında **"Başka mağazalarda ara"** düğmesi var: akakçe'de
aynı ürünü arar, adayları listeler, **sen doğrusunu seçersin**. Otomatik
eşleştirme bilerek yok — "RTX 5070 Ti Prime" ile "Prime OC" ayrı ürünlerdir
ve yanlış eşleştirme, yanlış ürünün fiyatını doğru ürünün geçmişine yazar.
O hata sessizdir ve geri alınamaz.

Toplayıcı kaynak eklendiğinde iki şey birden kazanılır:

- Sistem her turda tüm kaynakları okuyup **en ucuzunu** bildirir.
- **Pazar derinliği** gelir: "🏪 14 satıcı · 2.si 41.500". Bu, fiyat geçmişi
  henüz oluşmamış üründe elindeki **tek** uyarı işaretidir — en ucuz fiyat
  ikinciden orantısız ucuzsa, o muhtemelen hatalı girilmiş tek bir listedir.
  Koruma katmanı da aynı sinyali kullanıyor (bkz. MIMARI K52).

---

## 4. Canlıya alma (Docker)

```bash
cp .env.example .env
```

`.env` içinde **mutlaka** doldurulacaklar:

```bash
KEEPMONEY_ORTAM=uretim
KEEPMONEY_JWT_GIZLI_ANAHTAR=<üretilen 48 baytlık değer>
POSTGRES_PAROLA=<güçlü rastgele parola>
KEEPMONEY_CORS_KAYNAKLARI=https://alanadin.com      # '*' üretimde YASAK
KEEPMONEY_SITE_ADRESI=https://alanadin.com          # e-postadaki bağlantıların tabanı

# Telegram kullanacaksan İKİSİ de gerekli — bot adı yanlışsa bağlama
# akışı sessizce çalışmaz (deep-link yanlış hesaba gider)
KEEPMONEY_TELEGRAM_BOT_TOKEN=<BotFather token>
KEEPMONEY_TELEGRAM_BOT_ADI=<botun @kullanıcı adı, @ olmadan>

# E-posta yoksa parola sıfırlama SESSİZCE çalışmaz (açılışta uyarır)
KEEPMONEY_SMTP_SUNUCU=smtp.saglayici.com
KEEPMONEY_SMTP_PORT=587
KEEPMONEY_SMTP_KULLANICI=...
KEEPMONEY_SMTP_PAROLA=...
KEEPMONEY_EPOSTA_GONDEREN=KeepMoney <noreply@alanadin.com>

# TERS VEKİLİN AĞI — yazılmazsa `X-Forwarded-For` YOK SAYILIR ve tüm
# istekler vekilin IP'sinden geliyormuş gibi görünür (IP başına sayan
# limitler herkes için tek kovaya düşer). Docker ağı için tipik değer:
KEEPMONEY_GUVENILEN_VEKILLER=172.16.0.0/12

# /metrics token'ı. BOŞ BIRAKILIRSA ÜRETİMDE UÇ KAPANIR (404).
KEEPMONEY_METRIK_TOKENI=<token_urlsafe(32) çıktısı>
```

```bash
docker compose up -d          # veritabanı + göçler + api + tarayıcı + bot
docker compose logs -f api
curl -fsS localhost:8000/saglik
```

Dört süreç kalkar: `veritabani`, `gocler` (tek seferlik), `api` (:8000),
`tarayici` (:9100 ölçüm ucu), `bot`.

**Portlar YALNIZCA `127.0.0.1`e bağlı.** Önceden tüm ağ arayüzlerine
açılıyorlardı; uygulama düz HTTP konuşuyor ve hız sınırı ters vekil arkasında
olmayı varsayıyor, yani o kurulum TLS'siz ve frensiz bir sunucu demekti.
Dışarıdan erişim ters vekil üzerinden olur (aşağıda).

### Önüne ters vekil koy

Konteyner düz HTTP konuşur. TLS sonlandırma, HTTP/2 ve gerçek istemci IP'si
için önüne Caddy/nginx koy:

```
alanadin.com {
    reverse_proxy localhost:8000
}
```

> **`KEEPMONEY_GUVENILEN_VEKILLER` DOLDURULMALI.** Hız sınırı gerçek
> istemci IP'sini `X-Forwarded-For`dan okuyor ama başlığa **yalnızca bu
> listedeki bir kaynaktan gelirse** güveniyor. Liste boşsa başlık tamamen
> yok sayılır: uygulama çalışır, ama tüm istekler vekilin IP'sinden
> geliyormuş gibi görünür ve IP başına sayan limitler (kayıt) herkes için
> tek kovaya düşer.
>
> Bu koruma bir ARIZADAN geldi ve ölçüldü: başlığa koşulsuz güvenilirken her
> istekte farklı bir `X-Forwarded-For` yazarak 40 başarısız giriş denemesinin
> 40'ı da geçti, tek bir 429 çıkmadı (limit 8). Yani parola deneme freni
> fiilen yoktu.

---

## 5. Canlıda ne izlenir

İki ayrı Prometheus hedefi var — **ayrı süreç = ayrı kayıt defteri**, tarama
sayaçları API'nin `/metrics`inde **görünmez**:

```
api:8000/metrics        HTTP trafiği
tarayici:9100/metrics   tarama sağlığı  ← asıl bakılacak yer
```

Elle bakmak için:

`/metrics` artık **token istiyor** (kimliksiz açıktı). `.env`de
`KEEPMONEY_METRIK_TOKENI` tanımlıysa Prometheus şu başlıkla toplamalı:

```yaml
authorization: { type: Bearer, credentials: <KEEPMONEY_METRIK_TOKENI> }
```

Üretimde token BOŞ bırakılırsa uç 404 döner (açılışta uyarılır) — kimliksiz
açık bırakmaktansa kapalı.

```bash
curl -s -H "Authorization: Bearer $KEEPMONEY_METRIK_TOKENI"      localhost:9100/metrics | grep keepmoney_kaynak_okuma
curl -s localhost:9100/metrics | grep keepmoney_fiyat_guveni
```

| Ölçüm | Neden önemli | Alarm |
|---|---|---|
| `keepmoney_kaynak_okuma_toplam{sonuc="ok"}` payı | Scraping'in sessizce bozulması bu üründeki **en büyük risk** | Bir domainde `ok` oranı %50'nin altına inerse |
| `keepmoney_fiyat_guveni_toplam{guven="regex"}` | Regex payının artması, seçicilerin bozulmaya başladığının **erken** sinyali | Pay artış eğilimindeyse |
| `keepmoney_bayat_urun` | 24 saattir okunamayan ürün = kullanıcı bayat fiyata bakıyor | Sürekli artıyorsa |
| `keepmoney_bekleyen_uyari` | Telegram gönderici tıkandı | Sürekli artıyorsa |

Sistem kendi kendini de savunur: bir kaynak üst üste 3 kez hata verir ya da
2 kez şüpheli fiyat döndürürse kullanıcıya `KAYNAK_BOZUK` uyarısı gider.

---

## 6. Yedekleme — atlanamaz

Bu üründe asıl değer **fiyat geçmişidir ve yeniden üretilemez**. Kod
kaybolursa yeniden yazılır, sunucu kaybolursa yenisi kurulur; iki yıllık
fiyat hafızası kaybolursa geri getirmenin yolu yoktur.

```bash
crontab -e
30 3 * * * cd /opt/keepmoney && YEDEK_DIZIN=/mnt/yedek ./betikler/yedekle.sh >> /var/log/km-yedek.log 2>&1
```

`YEDEK_DIZIN` **başka bir makinede** ya da nesne deposunda olmalı — aynı
diskteki yedek, yedek değildir.

**Ayda bir geri yükleme provası yap.** Denenmemiş yedek, yedek değil
temennidir:

```bash
./betikler/geri-yukle.sh /mnt/yedek/keepmoney-20260815-033000.dump
```

---

## 7. Bilinen sınırlar

Bunlar bilinçli kararlar, eksik değil — ama bilmeden canlıya çıkma:

- **Tek instance varsayımı.** Hız sınırı süreç belleğinde tutuluyor. İki API
  kopyası çalıştırırsan efektif limit iki katına çıkar. Çok instance'a
  geçince Redis'e taşınmalı ([MIMARI.md K24](MIMARI.md)).
- **`tarayici` servisini ÇOĞALTMA.** `docker compose up --scale tarayici=2`
  tek satır ama sessizce zarar verir: tarama kuyruğunda (`Product.
  sonraki_kontrol`) kilit ya da sahiplenme YOK, iki worker aynı ürünleri
  seçer. Sonuç: aynı okuma iki kez `price_readings`e yazılır (geçmiş
  bozulur), mağazalara giden istek iki katına çıkar (IP engeli riski) ve
  aynı uyarı iki kez üretilebilir. Ölçekleme önce kuyruğa sahiplenme
  (`SELECT ... FOR UPDATE SKIP LOCKED` ya da bir kiralama sütunu) eklemeyi
  gerektirir.
- **Seçici bakımı süreklidir.** Siteler HTML'ini haber vermeden değiştirir.
  Ayda bir `kaynak_dene.py` çalıştır.
- **KVKK/gizlilik metni yok.** Kullanıcı verisi (e-posta) topluyorsun;
  yayına açmadan önce hukuki metin gerekli. Bu repo hukuki metin üretmez.
  **Yayına açmanın önündeki tek kod-dışı engel budur.**
- **SMTP'siz üretimde parola sıfırlama ÇALIŞMAZ ve bunu kimse fark etmez.**
  Açılışta uyarılıyor ama başlatma engellenmiyor. Bu durumda uç
  "gönderildi" der, e-posta hiç gitmez. (Token'ın loga yazılması AYRI bir
  açıktı ve kapatıldı — üretimde gövde artık loglanmıyor.)
- **E-posta doğrulama zorunlu değil.** `eposta_dogrulandi` bayrağı var,
  Ayarlar sayfasında gösteriliyor ve yeniden gönderilebiliyor — ama hiçbir
  ucu kapatmıyor. Bilinçli: bildirimler Telegram'dan gidiyor, e-posta yalnızca
  parola sıfırlama kanalı. Ödeme/paylaşım eklenirse bu kapı kapatılmalı.
- **Çıkış (logout) token'ı iptal etmiyor.** Çerez silinir ama token süresi
  (7 gün) dolana kadar geçerli kalır. Parola değişimi ise TÜM oturumları
  düşürüyor (`users.oturum_surumu`). Gerçek "her yerden çıkış" için aynı
  sayaç kullanılabilir; şimdilik kullanılmayan altyapı olurdu.
- **Ortaklık (affiliate) etiketleri boş.** Programlara kaydolduktan sonra
  ilgili `siteler/*.yaml` dosyalarına yazılır. Kanonik URL'ye asla
  dokunulmaz — etiket yalnızca kullanıcı mağazaya giderken eklenir.
- **Kapasite ölçüldü, tek süreçle sınırlı.** Panel 115 rps, ürün detayı
  55 rps (tek uvicorn süreci, SQLite, 36.000 okuma). Uçların kendi maliyeti
  5-8 ms; darboğaz süreç sayısı. Kendi ölçümün için:
  `python betikler/yuk_testi.py --kullanici 50 --istek 2000 --es-zaman 32`

  **`--workers` EKLEME.** Hız sınırı süreç belleğinde tutuluyor (dört süreç
  = efektif limit dört katı) ve Prometheus kayıt defteri süreç başına
  (`/metrics` zıplar). Yatay ölçekleme önce bu ikisini süreç dışına taşımayı
  gerektirir — bkz. [MIMARI K54](MIMARI.md).

  Asıl ölçek sınırı zaten API'de değil taramada: `render: true` siteler
  istek başına ~8 sn ve ~250 MB tüketiyor.

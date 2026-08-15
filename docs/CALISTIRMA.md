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

```bash
git clone https://github.com/menesdeniz1/keepmoney && cd keepmoney

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # JWT anahtarını içine yaz
mkdir -p data                 # SQLite dosyası buraya
alembic upgrade head          # şemayı kur
```

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
pytest -q

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

Kırık bir siteyi düzeltmek: `keepmoney/siteler/<domain>.yaml` dosyasını aç
(yoksa `_SABLON.yaml`'dan kopyala).

1. `--html-kaydet` ile kaydedilen HTML'i aç, `application/ld+json` ara.
   Varsa ve fiyat içindeyse zaten bulunması gerekirdi → `render: true` yap
   (fiyat JS ile sonradan geliyor demektir).
2. Yoksa fiyatın olduğu elemanın CSS seçicisini `fiyat_secici` alanına yaz.
3. Betiği o site için tekrar çalıştır.

**Kabul eşiği:** genel oran **%90+** ve hiçbir site `KIRIK` değil. Bu
sağlanmadan canlıya alma — çıkış kodu 0/1 olduğu için bunu CI'da eşik olarak
da kullanabilirsin.

Bu ölçüm **tek seferlik değildir**. Siteler HTML'ini haber vermeden
değiştirir; ayda bir tekrarla (aşağıdaki Prometheus ölçümü bunu otomatik
yakalar ama betik nerede kırıldığını doğrudan söyler).

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
```

```bash
docker compose up -d          # veritabanı + göçler + api + tarayıcı + bot
docker compose logs -f api
curl -fsS localhost:8000/saglik
```

Dört süreç kalkar: `veritabani`, `gocler` (tek seferlik), `api` (:8000),
`tarayici` (:9100 ölçüm ucu), `bot`.

### Önüne ters vekil koy

Konteyner düz HTTP konuşur. TLS sonlandırma, HTTP/2 ve gerçek istemci IP'si
için önüne Caddy/nginx koy:

```
alanadin.com {
    reverse_proxy localhost:8000
}
```

> Hız sınırı `X-Forwarded-For` başlığına bakar. Bu başlık **istemci
> tarafından uydurulabilir**; yalnızca güvendiğin bir vekilin arkasındayken
> anlamlıdır (vekil başlığı kendisi yazar). Konteyneri doğrudan internete
> açarsan hız sınırı atlatılabilir.

---

## 5. Canlıda ne izlenir

İki ayrı Prometheus hedefi var — **ayrı süreç = ayrı kayıt defteri**, tarama
sayaçları API'nin `/metrics`inde **görünmez**:

```
api:8000/metrics        HTTP trafiği
tarayici:9100/metrics   tarama sağlığı  ← asıl bakılacak yer
```

Elle bakmak için:

```bash
curl -s localhost:9100/metrics | grep keepmoney_kaynak_okuma
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
- **Seçici bakımı süreklidir.** Siteler HTML'ini haber vermeden değiştirir.
  Ayda bir `kaynak_dene.py` çalıştır.
- **KVKK/gizlilik metni yok.** Kullanıcı verisi (e-posta) topluyorsun;
  yayına açmadan önce hukuki metin gerekli. Bu repo hukuki metin üretmez.
- **Ortaklık (affiliate) etiketleri boş.** Programlara kaydolduktan sonra
  ilgili `siteler/*.yaml` dosyalarına yazılır. Kanonik URL'ye asla
  dokunulmaz — etiket yalnızca kullanıcı mağazaya giderken eklenir.
- **Yük testi yapılmadı.** Kaç eşzamanlı kullanıcı kaldırdığı ölçülmedi.
  İlk kullanıcılarla birlikte `keepmoney_http_sure_saniye` izlenmeli.

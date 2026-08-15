# Mimari Kararlar

Bu belge **neden** böyle yapıldığını tutar. Kod ne yaptığını zaten söylüyor; buradaki kararlar ise ileride "bu neden böyle?" diye sorulduğunda cevap versin diye yazıldı. Bir kararı değiştirmeden önce gerekçesini oku.

---

## K1 — Küresel ürün / kişisel izleme ayrımı

**Karar:** Fiyat ve fiyat geçmişi **küresel** (`Product` / `Source` / `PriceReading`); hedef, susturma, set üyeliği **kişisel** (`Watch`).

**Alternatif (reddedildi):** `setprice`'ta olduğu gibi ürünü kullanıcıya bağlamak (`user_id` + `unique(user_id, url)`).

**Neden reddedildi — iki bağımsız sebep:**

1. **Maliyet.** 500 kişi aynı ekran kartını izliyorsa o sayfa 500 kez taranır. Scraping bu ürünün en pahalı kalemi; kullanıcı sayısıyla doğrusal büyüyen bir maliyet, ücretsiz bir servisi imkânsız kılar. Küresel modelde aynı sayfa **1 kez** taranır ve ürün paylaşımı arttıkça **kullanıcı başına maliyet düşer**.

2. **Değer.** Kişiye özel geçmişte yeni kullanıcı ilk gün boş grafik görür ve "bu iyi fiyat mı" sorusuna en az 5 gün cevap alamaz — yani ürünün ana vaadi ilk hafta çalışmaz. Küresel geçmişte kullanıcı ürünü eklediği an aylarca geriye giden grafiği görür.

**Bedeli:** Ürün kimliği artık paylaşılan bir kaynak. Bir kullanıcının ürün adını düzenlemesi herkesi etkiler → ad/kategori düzenlemesi ya moderasyona ya da kişisel bir "takma ad" alanına ihtiyaç duyacak. Bu bilinçli bir borç, Faz 3'te ele alınacak.

---

## K2 — Ürün ≠ URL

**Karar:** `Product` mantıksal üründür; `Source` onun bir mağazadaki sayfasıdır. Bir ürün N kaynak taşır, güncel fiyat bunların **en ucuzudur**.

**Neden:** Kullanıcının aradığı şey "şu ürün en ucuz nerede" — tek mağazayı izlemek sorunun yarısını çözer. Ayrıca dayanıklılık: bir kaynak ölse (404) veya bot duvarına takılsa ürün kör kalmaz.

**Ek fayda:** Toplayıcı siteler (`Source.toplayici = True`) tek sayfada N satıcının en ucuzunu verir — N mağaza taramaktan çok daha ucuz. Ölçeklenmede tercih edilen yol budur.

---

## K3 — Analiz katmanı saf fonksiyonlardan oluşur

**Karar:** `analiz.py` ve `karar.py` veritabanı, ORM, ağ veya framework bilmez. Girdi: veri sınıfları. Çıktı: veri sınıfları.

**Neden:**
- **Tek tanım.** Tarama worker'ı, API ve Telegram botu aynı fonksiyonu çağırır; üç yerde üç farklı "dip bölgesi" tanımı oluşamaz. (Öncül projelerde tam olarak bu olmuştu: `tracker`'ın `fiyat_baglami`'si ile `setprice`'ın `detect_bottom_zone`'u farklı şeyler hesaplıyordu.)
- **Test edilebilirlik.** 82 testin çoğu kurulum gerektirmeden, gerçek senaryolarla çalışıyor.
- **Taşınabilirlik.** SQLite → Postgres geçişi bu katmanı hiç etkilemez.

---

## K4 — Tüm analiz günlük minimumlar üzerinden

**Karar:** Hiçbir istatistik ham okuma listesi üzerinden hesaplanmaz; önce gün başına tek değere (o günün en düşüğü) indirgenir.

**Neden:** Tarama sıklığı ürüne göre değişir. Sık taranan ürün günde 48 okuma, seyrek taranan 2 okuma üretir. Ham listede birincinin fiyatları medyanı domine eder ve "günlerin %70'inden ucuz" gibi bir ifade anlamını yitirir. Gün başına tek değer, ürünler arası karşılaştırmayı da tutarlı kılar.

---

## K5 — Koruma katmanı: yanlış alarm > kaçırılmış fırsat

**Karar:** Şüpheli fiyat bildirime dönüşmez; ikinci okumayla doğrulanır. Aşırı sapmalarda 2-okuma onayı bile geçersizdir.

**Neden:** Kullanıcı bir kez "5.000 TL'ye düştü!" bildirimi alıp sayfada 50.000 TL görürse ürüne bir daha güvenmez. Kaçırılan bir fırsatın maliyeti ise sıfıra yakın — fiyat genelde bir süre düşük kalır.

**"Aşırı şüpheli" neden ayrı bir kategori:** Bozuk bir kaynak **düzelene kadar kendisiyle tutarlı kalır**. İki ardışık okumanın örtüşmesi doğruluk kanıtı değildir. İki gerçek vaka bu kuralı doğurdu:

- Bir mağaza linki genel kategori sayfasına düşmüştü; regex oradan hedefin çok altında **sabit** 1.260 TL okuyordu. Sayfa hep aynı yanlış değeri döndürdüğü için "tutarlı" sayılıp iki kez yanlış alarm gitti.
- Güvenilir bir json-ld kaynağında tek bir pazaryeri satıcısı ürünü gerçek değerinin 11 katına listelemişti; site bunu saatlerce "en ucuz" gösterdi. Kaynak güvenilirdi, veri hatalıydı.

Bu yüzden `dogrula()` üç durum döner: `temiz` / `beklemede` / `bozuk` — sonuncusundan çıkış yalnızca güvenilir kaynaktan makul bir okumayla mümkündür.

---

## K6 — Sahte indirim tespiti iki şartlıdır

**Karar:** Bull-trap için hem (a) fiyatın 90 günün medyanından %10+ pahalı olması, hem (b) son 14 günde daha yüksek bir fiyat görülmüş olması gerekir.

**Neden:** `setprice`'taki tek şartlı sürüm ("önceki fiyattan düşük ve medyandan pahalı") normal fiyat dalgalanmasını da tuzak sayıyordu — her küçük düşüş yanlış pozitif üretiyordu. İki şartın kesişimi "gerçekten bir indirim anlatısı var mı" sorusunu sorar.

---

## K7 — Telegram bağlama: deep-link token, elle chat ID değil

**Karar:** Kullanıcı chat ID'sini elle yazmaz. Web tek kullanımlık token üretir → `t.me/bot?start=<token>` → bot doğrular ve `chat_id`'yi kendisi yazar. `User.telegram_chat_id` tekil (unique).

**Neden:** Bot yalnızca bildirim gönderiyorken elle giriş zararsızdı. Ama bot **yazma yetkisi** kazandığı anda (hedef değiştirme, ürün silme) gelen mesajın `chat_id`'sinden kullanıcı çözülecek. Herkesin elle doldurabildiği bir alan bu durumda doğrudan hesap ele geçirme yoludur.

---

## K8 — Kuyrukta bekleme yerine erteleme

**Karar:** Bir hostun kuyruk beklemesi 180 saniyeyi aşacaksa o kontrol **atlanır**, beklenmez.

**Neden:** Cezalı bir hostun sırasını bekleyen görev worker slotunu dakikalarca işgal eder. Birkaç slot birden cezalı hosta denk gelince tüm tarama saatlerce kilitlenir — `tracker`'ın loglarında 15-57 dakikalık açıklanamayan sessizlikler tam olarak buydu.

---

## K9 — SQLite ile başla

**Karar:** Varsayılan SQLite; `KEEPMONEY_VERITABANI_URL` ile Postgres'e geçilir.

**Neden:** Asıl darboğaz her zaman scraping olacak, veritabanı değil. SQLite tek makinede birkaç bin kullanıcıyı taşır. Postgres'e geçiş noktası net: tarama worker'ını ayrı makineye alacağın gün — SQLite'ın tek yazar kısıtı orada bağlar.

*Güncelleme (Faz 2):* Migrasyon için Alembic kuruldu (bkz. K15). Katman zaten soyut olduğu için geçiş tek satırlık ayar değişikliği.

---

## K10 — Saat dilimi: DB'de UTC, her yerde Türkiye saati

**Karar:** Veritabanına naive UTC yazılır; kullanıcıya gösterilen ve analizde kullanılan her şey `Europe/Istanbul`. Tek dönüşüm noktası `zaman.py`.

**Neden önemli:** "Gün" sınırı günlük minimum hesabını doğrudan belirler. UTC gününe göre gruplasaydık, Türkiye saatiyle 01:00'de görülen bir fiyat düşüşü bir *önceki* günün minimumuna yazılırdı — kullanıcı "dün 48.500'dü" derken Türkiye gününü kastediyor, "son 30 günün dibi" bildirimi yanlış günü işaret ederdi.

**Neden DB'de UTC:** SQLite saat dilimi bilgisini saklamaz; yarı-aware bir şema en kötü seçenektir (bazı satırlar aware, bazıları değil). Tüm DB değerleri koşulsuz UTC kabul edilir.

**Kural:** Kodda `datetime.now()` / `date.today()` yasak — `zaman.py` fonksiyonları kullanılır. Linter'da DTZ kuralları bu yüzden kapalı (politika tek yerde, her modülde susturma gerekmesin diye).

---

## K11 — Koruma durumu kaynağa ait, kullanıcıya değil

**Karar:** 2-okuma doğrulaması ve "bozuk kaynak" sayacı `Source` tablosunda tutulur; cooldown/susturma `Watch`'ta.

**Neden:** "Bu okuma güvenilir mi?" nesnel bir sorudur — cevabı her kullanıcı için aynıdır. Kullanıcı başına tutulsaydı aynı şüpheli fiyat her izleyici için ayrı ayrı doğrulanır, N kat gereksiz istek atılırdı. "Bildirim gitmeli mi?" ise özneldir (kimin hedefi, kimin susturması) — o Watch'ta kalır.

---

## K12 — Tarama sıklığı sabit değil, uyarlanabilir

**Karar:** Her ürünün kendi `kontrol_araligi_dk` değeri var, her taramadan sonra yeniden hesaplanıyor: hedefe %10'dan yakınsa 30 dk, bir haftadır %1'den az oynadıysa 24 saat, aksi halde 3 saat. Sıra `izleyen_sayisi`'na göre — çok izlenen ürün önce.

**Neden:** Ölçeklenmenin tek gerçek kaldıracı bu. Her ürünü saatte bir taramak 500 kullanıcıda imkânsız; ama izlenen ürünlerin çoğu aylarca kıpırdamıyor. Bütçe yetmediğinde en çok kişiyi etkileyen ürünün güncel kalması, herkesin eşit derecede bayat kalmasından iyidir.

---

## Öncül projelerden ne alındı, ne alınmadı

### `tracker`'dan alındı
`parse_tl` (TL binlik/ondalık ayrımı) · şüpheli + aşırı şüpheli koruması · 2-okuma doğrulaması · `HostThrottle` + üstel geri çekilme + erteleme · çoklu kaynak/en-ucuz seçimi · 90 günlük fiyat bağlamı · 30-gün-dibi sinyali · set toplamı kavramı

### `setprice`'tan alındı
Çok kullanıcılı ürün vizyonu · set/şablon kavramı · bull-trap fikri (şartı sıkılaştırılarak) · alert türleri · domain sağlık takibi

### Bilerek alınmadı
- **Excel katmanı** — proje artık DB merkezli, Excel köprüsü ölü ağırlık
- **AI karar motoru** — şimdilik hayır. Deterministik analiz `iyi_firsat` sinyalini zaten üretiyor; LLM katmanı ücretsiz kotalarla ölçeklenmez ve açıklanabilirliği düşürür. İleride "gerekçe metni yaz" rolüyle geri gelebilir, karar verici olarak değil.
- **Benchmark/performans skoru** — canlı veri kaynağı olmadan elle küratörlü 37 satırlık liste, kapsamı dar ve bakımı belirsiz bir özellikti
- **Celery/Redis** — tek worker süreci bu ölçekte yeterli; kuyruk altyapısı gerçek bir darboğaz görülmeden eklenmeyecek

---

## K13 — Katmanlar: bağımlılık yönü içeri doğru

**Karar:** Dört katman, tek yönlü bağımlılık.

```
SUNUM      api/ (rotalar) · [Faz 4] telegram botu
UYGULAMA   servisler/ — use-case'ler, iş kuralları
ALAN       analiz · karar · fiyat · zaman — SAF, sıfır bağımlılık
ALTYAPI    models · db · ayikla · cekici · siteler · throttle
```

**Kurallar:**
- `servisler/` içinde `fastapi` import edilmez. Aynı fonksiyonları Telegram botu da çağıracak; kural iki yerde yazılmasın.
- Rotalar iş kuralı içermez — servis çağırır, istisnayı HTTP koduna çevirir.
- Alan katmanı ORM bilmez; girdisi ve çıktısı veri sınıflarıdır.

**Neden:** Öncül projelerin en pahalı hatası, iş mantığının rota fonksiyonlarına yayılmasıydı — `setprice`'ta link çözümleme bloğu iki endpoint'te **birebir kopyalanmıştı** (~50 satır). Bot eklendiğinde üçüncü kopya kaçınılmazdı.

---

## K14 — API şemaları ORM modellerinden ayrı

**Karar:** `semalar.py` (Pydantic v2) ile `models.py` (SQLAlchemy) ayrı.

**Neden:** Veritabanı şeması iç mesele, API sözleşmesi dış mesele. `Watch.son_bildirim_ts` gibi iç alanlar dışarı sızmamalı; `yorum` gibi hesaplanan alanlar DB'de olmadığı halde dışarı verilmeli. Tek sınıfa bindirmek zamanla ya API'yi ya şemayı rehin alır.

---

## K15 — Alembic, `create_all` değil

**Karar:** Şema değişikliği migrasyonla yapılır. `create_all` yalnızca geliştirme ortamında, testlerde ve ilk kurulumda.

**Neden:** `create_all` VAR OLAN tabloyu güncellemez — modele kolon eklersin, üretimde sessizce eski şemayla çalışmaya devam eder ve hata ancak o kolona yazmaya kalkınca çıkar. `setprice`'ın "hafif otomatik migrasyon"u (ALTER TABLE ile kolon ekleme) bu yaranın üstünü kapatan bir yamaydı; kolon silme/tip değiştirme desteklemiyordu. Alembic `render_as_batch=True` ile SQLite'ta da tam yetenekli.

**Doğrulama:** `alembic check` — model ile migrasyonların uyuşup uyuşmadığını CI'da denetler.

---

## K16 — Kanonik URL, küresel ürün modelinin can damarı

**Karar:** Ekleme sırasında URL normalize edilir: şema/host sabitlenir, takip parametreleri (`utm_*`, `gclid`, `sellerId`, `boutiqueId`…) atılır.

**Neden:** Aynı ürünün linki kampanya etiketleriyle geliyor. Normalize edilmezse aynı sayfa N kez taranır (maliyet), fiyat geçmişi N'e bölünür (analiz bozulur) ve kullanıcı aynı ürünü iki kez ekleyebilir. K1'deki paylaşım kazancı tamamen buna bağlı.

---

## K17 — Ürün adı önce URL'den, sonra gerçek başlıktan

**Karar:** İzleme eklenirken ağa ÇIKILMAZ; ad URL'den türetilir ve `ad_gecici=True` işaretlenir. İlk başarılı taramada gerçek başlıkla değiştirilir, bayrak düşer.

**Neden:** İstek içinde sayfa çekmek kullanıcıyı 10-20 saniye bekletir ve mağaza yavaşsa istek zaman aşımına uğrar. Bayrak, kullanıcının sonradan düzelttiği adın taramalarca ezilmesini de önler.

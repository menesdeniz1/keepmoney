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

---

## K18 — Yapılandırma tek kaynaktan; CI bunu denetler

**Karar:** Her ayar `ayarlar.py`'de tiplenmiş olarak tanımlıdır. Kodun başka hiçbir yerinde `os.environ` okunmaz — `db.py` dahil.

**Nasıl öğrenildi:** `ayarlar.py` eklendiğinde `db.py` eski hâliyle kaldı ve `os.environ["DATABASE_URL"]`i kendisi okumaya devam etti. İki doğruluk kaynağı oluştu: testler bir dosyaya, Alembic başka dosyaya yazdı. Yerelde hiçbir belirti yoktu (her iki dosya da vardı); CI temiz makinede `table domain_health already exists` ile patladı.

**Alınan önlemler:**
- `db.py` artık `ayarlar().veritabani_url` okuyor; regresyon testi ikisinin eşitliğini doğruluyor.
- `init_db()` yalnızca `ortam == "gelistirme"` iken çalışıyor. Testler kendi oturumlarını enjekte ediyor, dosya veritabanına hiç dokunmuyorlar.
- CI'da `alembic check` var: model ile migrasyon ayrışırsa build kırılır.

**Ders:** Yerelde geçen ama CI'da patlayan hata, neredeyse her zaman *kirli durumun gizlediği* bir hatadır. Temiz makinede çalışmayan şey aslında hiç çalışmıyordur.

---

## K19 — JWT anahtarı en az 32 bayt (RFC 7518 §3.2)

**Karar:** Üretimde kısa anahtar uygulamayı AÇILIŞTA durdurur; geliştirmede uyarı verir.

**Nasıl fark edildi:** PyJWT test çalıştırmasında `InsecureKeyLengthWarning` üretti — CI'ya koyduğum anahtar 16 baytlıktı. Uyarı testte çıktı ama aynı hata üretimde de yapılabilirdi ve orada sessiz kalırdı.

**Neden ölümcül:** HS256'da kırılan imza anahtarı, istediğin kullanıcı adına geçerli token üretmek demektir — yani tam hesap devralma. Doğrulamanın yeri açılış anıdır.

---

## K20 — Anahtar politikası: uzunluk değil, entropi

**Karar:** JWT imza anahtarı üretimde üç kontrolden geçer — en az **256 bit (32 bayt)**, en az 12 farklı karakter, ve şablon değeri içermemek. Uygulama kendi ürettiğinde **384 bit (48 bayt)** üretir.

**Sayı nereden geliyor:** RFC 7518 §3.2, HS256 için anahtarın "hash çıktısı kadar (256 bit) ya da daha büyük" olmasını **zorunlu** kılar. OWASP ve büyük kimlik sağlayıcılarının dokümanları aynı sayıyı verir. 256 bit tabandır, tartışmalı değildir.

**Neden 384 bit üretiyoruz:** Tabanı tam sınırda kullanmak, ileride HS384'e geçmek gerekirse anahtar yenilemek demektir. 16 bayt fazlanın maliyeti sıfır.

**Asıl mesele uzunluk değil:** İlk sürüm yalnızca bayt sayıyordu. `"a" * 64` bu kontrolden geçiyordu — 512 bit uzunluk, ~5 bit gerçek entropi. Anahtar bir **parola değil**, rastgele bir bit dizisidir; CSPRNG'den üretilmelidir. Entropiyi bir string'den kesin ölçmek mümkün değil, ama açıkça zayıf olanı yakalamak mümkün: tek karakterden ibaret olanlar ve `.env.example`'dan kopyalanıp unutulmuş `changeme` türü değerler.

**Neden açılışta patlatıyoruz:** Zayıf imza anahtarı = istediğin kullanıcı adına geçerli token üretmek = tam hesap devralma. Bu hatanın ortaya çıkacağı bir sonraki an, saldırının gerçekleştiği andır. Doğrulamanın yeri açılış anıdır.

**Sonraki adım (henüz yapılmadı):** Anahtar rotasyonu — imzalama için tek "aktif" anahtar, doğrulama için eski anahtarların da kabul edildiği bir liste. Kullanıcı sayısı anlamlı hâle gelince eklenecek; şimdi eklemek kullanılmayan karmaşıklık olurdu.

---

## K21 — CORS'un env'den okunması: neden `NoDecode`?

**Karar:** `Annotated[list[str], NoDecode]` + `field_validator`. Hem `a.com,b.com` hem `["a.com"]` biçimi çalışır. Üretimde `*` reddedilir.

**Sorun neydi:** pydantic-settings, karmaşık tipleri (list, dict) ortam değişkeninden okurken **JSON olarak çözmeye çalışır** ve bunu doğrulayıcılardan ÖNCE yapar. Yani `mode="before"` validator'ım hiç çalışmıyordu; `KEEPMONEY_CORS_KAYNAKLARI=https://a.com,https://b.com` `SettingsError` veriyordu. Ayar pratikte yalnızca JSON dizisiyle verilebiliyordu.

**Yaygın üç yaklaşım — üçü de meşru:**

| Yaklaşım | Artı | Eksi |
|---|---|---|
| **`NoDecode` + validator** *(seçtiğimiz)* | Kütüphanenin resmî hook'u; alan gerçek `list[str]` kalır | pydantic-settings'e özgü bir kavram bilmek gerekir |
| Alanı `str` tut, `@property` ile böl | En az sihir, en okunaklı | Tip artık sözleşmeyi anlatmıyor; iki isim gerekir |
| Hiç uğraşma, env'e JSON yaz | Sıfır kod | Deploy eden kişiye `["https://a.com"]` yazdırmak; tırnak/kaçış hataları |

Birinciyi seçtik çünkü alanın tipi `list[str]` kalıyor — API sözleşmesi ve IDE ipuçları doğru çalışıyor.

**Not:** Birçok ekip CORS'u uygulamada hiç yönetmez, ters vekilde (nginx/Caddy/Traefik) çözer. Bu da geçerli; tek sunuculu FastAPI kurulumunda uygulamada tutmak daha basit.

**`*` neden üretimde yasak:** `allow_origins=["*"]` ile `allow_credentials=True` birlikte **kullanılamaz** — CORS spesifikasyonu yasaklar, tarayıcı isteği reddeder. Starlette yapılandırmayı sessizce kabul eder; hata ancak üretimde "neden çalışmıyor" olarak görülür. Açılışta yakalamak çok daha ucuz.

---

## K22 — Oturum httpOnly çerezde, localStorage'da değil

**Karar:** Giriş, token'ı `httpOnly` + `SameSite=lax` çerez olarak kurar. API **iki** kaynağı da kabul eder: çerez (tarayıcı) ve `Authorization: Bearer` (programatik istemci, CLI, testler).

**Neden:** SPA'larda JWT'yi `localStorage`'da tutmak yaygındır ama zayıftır — sayfaya sızan herhangi bir üçüncü parti script token'ı okuyup dışarı gönderebilir. `httpOnly` çerezi JavaScript ne okuyabilir ne yazabilir. `SameSite=lax`, CSRF'in büyük kısmını kapatır (GET dışı istekler çapraz siteden çerez taşımaz). `secure` yalnızca üretimde açık, çünkü yerelde HTTP kullanılıyor ve secure çerez tarayıcıya hiç ulaşmaz.

**İkisini birden desteklemek** yaygın profesyonel kalıptır: web'e en güvenli yolu verir, entegrasyonlara standart yolu bırakır.

**Yapılmadı:** Token iptali (kara liste). `/cikis` çerezi siler ama token süresi dolana kadar teknik olarak geçerli kalır. Gerçek iptal, her istekte bir kara liste sorgusu demektir; kullanıcı sayısı anlamlı olunca eklenecek.

---

## K23 — Uyarı iletimi: outbox kalıbı

**Karar:** Worker `Alert` satırını yazar (`telegram_gonderildi=False`); ayrı bir gönderici döngüsü iletir ve bayrağı çevirir.

**Neden:** Worker'ın içinden HTTP çağırmak iki şeyi birden riske atar — Telegram yavaşsa tarama turu uzar, hata anında uyarı buharlaşır. Outbox kalıbı bunun standart cevabıdır: üretim ile iletim ayrı sorumluluklardır, arada dayanıklı bir kayıt vardır.

Gönderim başarısızsa bayrak çevrilmez → sonraki turda yeniden denenir. Telegram'ı bağlamamış kullanıcının uyarısı web'de duruyor; bayrağı çevirilir ki her turda boşuna denenmesin.

---

## K24 — Kuyruk (Redis/Celery/arq) YOK

**Karar değişikliği:** Önceki planda arq vardı; uygularken yanlış araç olduğu görüldü.

**Neden:** Kuyruk altyapısı, *"kullanıcı bir iş tetikler, N worker paylaşır"* problemini çözer. Bizim iş bu değil: periyodik olarak **sırası gelmiş** ürünleri taramak. Sıranın kendisi zaten veritabanında — `Product.son_kontrol + kontrol_araligi_dk`. Yani **DB kuyruğun ta kendisi.** Üstüne Redis koymak aynı bilgiyi ikinci bir yerde tutmak, yeni bir arıza noktası eklemek ve bir bileşen daha işletmek demekti.

**Geçiş yolu açık:** İkinci worker gerektiğinde `taranacak_urunler`'e Postgres'in `SELECT ... FOR UPDATE SKIP LOCKED`'ı eklenir — kuyruk kütüphanesi olmadan yatay ölçekleme. O gün gelmeden altyapı kurmak, kullanılmayan karmaşıklıktır.

---

## K25 — Ortaklık (affiliate): kanonik URL'ye dokunulmaz

**Karar:** Ortaklık etiketi **tıklama anında** eklenir; `Source.url` temiz kalır.

**Neden mimari:** `Source.url` kanonik anahtardır (K16) — iki kullanıcının aynı ürüne düşmesi ona bağlı. Etiketi kalıcı yazsak: aynı ürün farklı etiketlerle farklı satırlara bölünür, scraper mağazaya ortaklık parametresiyle gider (gereksiz, bazı programlarda kural ihlali), ve etiket değişince tüm geçmiş bağı kopar.

**Üç kural testle korunuyor:**
1. **Tarafsızlık** — ortaklık, "en ucuz" seçimini etkilemez. `karar.en_iyi_kaynak` yalnızca fiyata bakar ve `affiliate` modülünü hiç tanımaz.
2. **Şeffaflık** — link arayüzde "ortaklık" rozetiyle işaretlenir, `rel="sponsored"` taşır ve altında açıklama vardır. Fiyat tavsiyesi veren bir üründe gizli komisyon, ürünün tüm iddiasını çürütür.
3. **Başkasının kodu ezilmez** — URL'de zaten bir ortaklık parametresi varsa dokunulmaz; bu, programdan atılma sebebidir.

---

## K26 — PWA: uygulama kabuğu önbelleklenir, API YANITLARI ASLA

**Karar:** `vite-plugin-pwa` ile precache; `/api`, `/metrics`, `/saglik` önbellek dışı.

**Neden elle service worker yazılmadı:** Bayat uygulama kabuğu, elle yazılan SW'lerin en yaygın hatasıdır — kullanıcı günlerce eski sürümü görür ve "temizle" demeden düzelmez. Plugin precache manifestini derlemeden üretir ve otomatik günceller.

**Neden API önbelleğe alınmaz:** Bu ürünün tüm iddiası fiyatın *güncel* olması. Önbellekten dünkü fiyat servis edilirse kullanıcı "dip" sanıp alır. Çevrimdışı çalışması gereken tek şey kabuktur.

---

## K27 — SSRF: her sıçrama doğrulanır, tek kapı yetmez

**Karar:** `aglar.py` tek doğrulama noktası; `url_sorunu()` şemayı, yazılı IP'yi ve **çözülmüş tüm A/AAAA kayıtlarını** denetler. Yönlendirmeler elle takip edilir ve **her adımda** yeniden doğrulanır.

**Tehdit:** Kullanıcı keyfi URL veriyor, sunucu ona istek atıyor — SSRF'in ders kitabı tanımı (OWASP A10). `https://169.254.169.254/latest/meta-data/iam/security-credentials/` bulut IAM anahtarlarını döndürür ve sayfa başlığı ürün adı olarak kullanıcıya geri gösterildiği için bu kör bir SSRF bile değil, doğrudan sızdırma kanalı.

**Neden tek kapı yetmedi (yaşandı):** İlk düzeltmede yalnızca `requests` yolu kapatıldı. `cloudscraper` yolunda tek bir `dogrula(url)` vardı ve yönlendirmeleri kütüphane takip ediyordu; Playwright yolunda tarayıcının kendisi takip ediyordu. Yani halka açık bir adres 302 ile iç ağa sapabiliyordu. **Ders:** koruma, ağa çıkan HER yolda olmalı ve kopyalanmamalı. Yönlendirme döngüsü artık requests/cloudscraper arasında paylaşılıyor, Playwright'ta ise yönlendirme ve alt kaynaklar dahil her istek `route` süzgecinden geçiyor.

**Kabul edilen artık risk:** DNS rebinding (doğrulama ile bağlantı arasında DNS cevabının değişmesi). Tam çözüm çözülen IP'ye bağlanıp Host başlığını elle vermek; requests'te ek taşıyıcı gerektiriyor. Pencere dar, yüzey sınırlı — kayda geçirildi.

---

## K28 — Hız sınırı bellekte, Redis'te değil (şimdilik)

**Karar:** Giriş/kayıt için süreç içi kayan pencere sayacı. IP+e-posta anahtarı.

**Neden yeterli:** Amaç kararlı bir saldırganı durdurmak değil — o mümkün değil. Amaç sözlük saldırısını **ekonomik olmaktan çıkarmak**. Tek instance'ta bu doğru çalışır ve sıfır bağımlılık getirir.

**Sınırı açıkça yazıyoruz:** Çok instance'ta her biri kendi sayacını tutar, efektif limit N katına çıkar; yeniden başlatmada sayaç sıfırlanır. Çok instance'a geçilen gün Redis'e taşınacak. Tek sayaç için bugünden koca bir bileşen işletmek, K24'teki kuyruk kararıyla aynı gerekçeyle reddedildi.

---

## K29 — Ölçümler: her SÜREÇ kendi ucunu yayınlar

**Karar:** `api` → `/metrics` (HTTP ölçümleri), `tarayici` → `:9100/metrics` (tarama ve kapsam ölçümleri). Prometheus iki hedefi ayrı toplar.

**Yakalanan hata:** Tarama sayaçları (`kaynak_okuma`, `fiyat_guveni`, `bayat_urun`…) `tarayici` sürecinde artıyordu ama `/metrics` yalnızca `api` sürecinde sunuluyordu. `prometheus_client`in kayıt defteri **süreç içidir** — API bu sayaçları hiçbir zaman göremezdi. Kod doğruydu, sayaçlar artıyordu, panolar boş kalıyordu. Bu, ölçüm olmamasından daha kötüdür: "ölçüyoruz" sanılır. Ürünün baştan beri yazdığı bir numaralı risk (scraping'in sessizce bozulması) tam da bu ölçümlerle görülecekti.

**Etiket kuralı:** HTTP ölçümlerinde **rota şablonu** (`/api/izlemeler/{izleme_id}`) kullanılır, ham yol değil. Ham yol her izleme kimliği için yeni bir zaman serisi doğurur — Prometheus'u şişiren en yaygın hata. Eşleşmeyen yol (404) hiç ölçülmez, yoksa rastgele URL deneyen bir tarayıcı tek başına ölçüm deposunu doldurur.

---

## K30 — Tarama kuyruğu: `sonraki_kontrol` sütunu

**Karar:** Sıradaki tarama zamanı satırda tutulur ve indekslenir; seçim `WHERE sonraki_kontrol IS NULL OR sonraki_kontrol <= now()`.

**Neden sütun:** `son_kontrol + kontrol_araligi_dk` her satırda farklı bir aralık demek ve bu hesabın SQLite ile PostgreSQL'de taşınabilir bir yazımı yok. Sonuç sütunda tutulunca seçim tek indeksli karşılaştırmaya iniyor. Aksi hâlde her tur (dakikada bir) **tüm ürün tablosu belleğe çekilip Python'da süzülüyordu** — 50 üründe fark edilmez, 50.000 üründe tarayıcıyı tek başına dize getirir. İş kuyruklarının `next_run_at`/`visible_at` deseni; K24'te yazılan "DB kuyruğun kendisidir" kararının eksik kalan yarısı.

**`son_kontrol`dan ayrı tutulur:** İkincisi "en son ne zaman okundu" olgusudur ve arayüzde gösterilir. Eskiden yeni bir abone geldiğinde `son_kontrol` sıfırlanıyordu — yani başkasının aylardır izlediği ürün, herkes için "hiç kontrol edilmemiş" görünüyordu.

---

## K31 — Bozuk kaynak bildirimi ÜRÜN seviyesinde

**Karar:** "Fiyat okunamıyor" uyarısı, ürünün **hiçbir** kaynağından fiyat gelmediğinde üretilir; kaynak başına değil.

**Yakalanan hata:** `KAYNAK_BOZUK` uyarı türü modelde tanımlı, arayüzde etiketi hazır, `karar.dogrula` "bozuk" deyip durumu işaretliyordu — ama **Alert satırını yazan kod hiç yoktu**. Kaynak sessizce bozulunca kullanıcı bayat fiyata bakmaya devam ediyordu. Aynı şekilde `hata_serisi` artırılıp sıfırlanıyor ama hiçbir kararda okunmuyordu.

**Neden ürün seviyesinde:** Bir kaynak bozulsa da ürünün başka çalışan kaynağı varsa kullanıcı doğru fiyatı görmeye devam eder; ona bildirim göndermek gürültüdür. Haber değeri, ekrandaki fiyatın o andan itibaren **bayat** olmasındadır. Tek turluk arıza da gürültüdür (site bakımda olabilir) — üst üste tekrarlayan arıza haberdir. `bozuk_uyarildi` bayrağı tekrar bildirimi engeller, kaynak düzelince düşer.

---

## K32 — Host aralığı: koruma, koruduğu yolla aynı renkte olmalı

**Karar:** `HostThrottle` API'si **senkrondur** ve tarama yolundan doğrudan çağrılır.

**Yakalanan hata:** Sıraya girme `async with throttle.slot(host)` biçiminde asenkron bir bağlam yöneticisiydi; oysa `Tarayici.kaynak_oku` senkron ve `asyncio.to_thread` içinden çalışıyor. O arayüzü çağırmak **yapısal olarak mümkün değildi** ve hiç çağrılmadı. Sonuç: modülün kendi başlığında "ölçekli scraping'de tek başarısızlık noktası budur" diye yazan korumanın birinci maddesi üretimde hiç devreye girmiyordu — tarayıcı bir turda aynı siteye 50 isteği arka arkaya atıyordu, yani korumanın engellemek için yazıldığı şeyin tam kendisi. Ceza (ikinci madde) çalışıyordu, aralık çalışmıyordu.

**Genel ders:** Bir korumanın eşzamanlılık modeli, koruduğu kod yolununkiyle uyuşmuyorsa o koruma **yoktur**. Testlerde `HostThrottle(min_gap=0)` enjekte ediliyor — bağımlılığın dışarıdan verilmesinin somut faydası.

---

## K33 — Kısmi güncelleme (PATCH) semantiği tek yerde

**Karar:** `servisler/ortak.alanlari_uygula` — beyaz liste + "açık `null` = temizle".

**İki hata birden:** (1) Alanlar `hasattr(nesne, ad)` ile kabul ediliyordu, yani modelin her sütunu yazılabilirdi; şema bilinmeyen anahtarı düşürdüğü için sömürülebilir değildi ama korumayı tesadüfe bırakmak toplu atama açığının klasik reçetesidir. (2) `None` "dokunulmadı" sayıldığı için bir kez konan hedef fiyat/bütçe API'den **bir daha silinemiyordu**.

**Neden ortak modül:** Aynı desen iki serviste kopyalanmıştı; biri düzeltilip diğeri geride kaldı. Rotalar `exclude_unset=True` ile çağırdığından bir anahtarın **varlığı** kullanıcının o alana bilerek dokunduğu anlamına gelir — kuralın tek bir yerde yaşaması gerekiyordu.

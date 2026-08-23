# Arayüz planı — Keepa refleksleri, KeepMoney farkı

*23 Ağustos 2026. Uygulama tohumlanmış bir kopyada gerçek tarayıcıyla açılıp
yedi ekranın görüntüsü alınarak incelendi; Keepa'nın özellikleri araştırıldı.*

## Konum

Hedef **Keepa'nın kopyası değil.** İki yerde zaten öndeyiz ve bu korunmalı:

- **Çok mağaza tek ürün.** Keepa yalnızca Amazon izler. Kanonik URL katmanı
  (K16) aynı ürünü farklı mağazalarda tek kimlik altında topluyor.
- **Bütçeli setler.** Rakiplerde karşılığı yok.

Keepa'dan alınacak olan **refleksler**: fiyatın iyi olup olmadığını ürünü
açmadan anlamak, grafiği zaman aralığıyla okumak, fırsatları tek yerde görmek.

## En büyük kusur — ölçüldü

**Analiz motoru panelde görünmüyor.** `analiz.fiyat_baglami()` dip/ucuz/pahalı
sinyalini, 90 günün dibini, medyanı, yüzdeliği, trendi ve sahte indirim
tespitini üretiyor. Ürün detayında güzelce gösteriliyor. Panelde **hiç yok** —
kart yalnızca ad, satıcı, son kontrol, fiyat ve varsa hedefe kalan mesafe
gösteriyor (`arayuz/src/bilesenler/IzlemeKarti.tsx`).

`worker.py:424` her taramada bu bağlamı hesaplıyor, uyarı kararı için
kullanıyor ve **atıyor**; `Product` tablosunda saklayan sütun yok. Yani sinyali
karta koymak yeni hesap değil, **zaten hesaplananı saklamak** meselesi — liste
ucunun ürün başına geçmiş sorgusu açmasına da gerek kalmaz.

## Katman 1 — veri hazır, çoğu arayüz işi

| # | İş | Emek | Göç |
|---|---|---|---|
| 1.1 | Kartta sinyal rozeti + 90 günlük kıvılcım + medyana göre % fark | 1 gün | ✔ |
| 1.2 | Grafikte zaman aralığı: `7g · 30g · 90g · 1y · Tümü` | 2 saat | — |
| 1.3 | Mağaza başına ayrı çizgi (`PriceReading.source_id` zaten yazılıyor, API tek seriye eziyor) | 1 gün | — |
| 1.4 | Listeyi sıralama/süzme (ucuzluk, hedefe yakınlık, sete göre, mağazaya göre) | 4 saat | — |
| 1.5 | Üst kutucukları işe yarar yapmak ("Hedefte 0" ve "Liste toplamı" yerine dip sayısı, bugünkü değişim) | 3 saat | — |
| 1.6 | Set kartında bütçe aşım miktarı + en pahalı üye işareti | 2 saat | — |

## Katman 2 — az arka uç + arayüz

| # | İş | Emek | Not |
|---|---|---|---|
| 2.1 | **Fırsatlar sayfası** — takip edilen her şey kendi geçmişine göre sıralı | 4 saat | 1.1'e bağımlı |
| 2.2 | Yüzdeye göre uyarı ("%15 düşerse") + Keepa'nın *rearm*'ı (uyarıyı N gün sonra yeniden kur) | 1 gün | göç |
| 2.3 | Grafikte stok boşlukları (`STOKTA_YOK` modelde var, grafik bilmiyor) | 4 saat | — |
| 2.4 | Mağaza karşılaştırma tablosu (kaynaklar şu an sadece listeleniyor) | 4 saat | — |
| 2.5 | Bildirimleri güne göre gruplama + türe göre süzme | 3 saat | — |
| 2.6 | CSV dışa aktarma | 2 saat | — |

## Katman 3 — ürünleşme

| # | İş | Emek | Risk |
|---|---|---|---|
| 3.1 | Tarayıcı eklentisi — Keepa'nın asıl dağıtım kanalı; bizde tek mağazaya değil herhangi birine takılır | 1 hafta | orta |
| 3.2 | Sekiz bot duvarı ürününü akakçe üzerinden bağlamak | 1 gün | düşük |
| 3.3 | Barkod okuyucu (PWA `BarcodeDetector`; HTTPS şart) | 3 gün | orta |
| 3.4 | Herkese açık ürün sayfaları (ürün kimliği zaten küresel); önce KVKK/şartlar | 1 hafta | yüksek |

## Bilinçli olarak YAPILMAYACAKLAR

- **Satış sırası, Buy Box, teklif sayısı, satıcı istatistikleri.** Amazon
  satıcısının araçları. Kullanıcımız alıcı. Eklemek arayüzü Keepa'nın
  eleştirilen "bilgi çorbası" tarafına götürür.
- **Product Finder / katalog tarama.** Milyonlarca ürünlük katalog gerektirir.
  Bizim modelimiz "kullanıcı linki yapıştırır" — eksiklik değil, farklı konum.
- **Grafiği çizgi çorbasına çevirmek.** Üstünlüğümüz analizi *cümleye*
  çevirmek. Çizgi eklerken bu kaybedilmemeli.
- **Ücretli katman — şimdilik.** Okuma oranı %54'ken para alınmaz.

## Önerilen sıra

1. **Worker'ı birkaç gün çalıştır** (DEVIR §4.1) — hâlâ tek doğrulanmamış alan.
2. **3.2** — sekiz bot duvarı ürünü. Arayüz katmanı değil ama arayüzün
   göstereceği veriyi belirliyor; %54 okuma oranıyla hiçbir tasarım iyi
   görünmez.
3. **1.1 → 1.2 → 1.4** — panel Keepa refleksiyle okunur hâle gelir (~2 gün).
4. **2.1** — Fırsatlar; 1.1'in üstüne neredeyse bedava biner.
5. **1.3** — mağaza başına çizgi; 3.2 bitmeden çoğu üründe tek çizgi kalır.
6. **1.5, 1.6, 2.2–2.6** — cilalama turu.
7. **3.1** — eklenti. Ancak yukarısı bittiğinde: eklenti insanları uygulamaya
   sokar, uygulama hazır olmalı.

Katman 1'in tamamı iki–üç günlük iş ve **tek bir yeni bağımlılık
gerektirmiyor.** Algılanan kalitedeki en büyük sıçrama orada.

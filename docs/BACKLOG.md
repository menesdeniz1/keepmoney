# Yapım listesi — Keepa refleksli arayüz

*24 Ağustos 2026. Ayrıntılı hâli (kabul ölçütleri, şema taslakları, test
notları) paylaşılan belgede; burası çalışma sırası ve özet.*

**Her task için:** `pytest` tamamı · `ruff check .` · `npx tsc -b` ·
`npx eslint src --max-warnings=0` · `alembic check` yeşil olmadan kapanmaz.
Arayüz değiştiyse `npm run build` + `dist` → `statik/`. Yeni davranışın testi
yoksa task bitmemiştir.

## A · Sinyali görünür yapmak (8 task, ~2,5 gün)

`analiz.fiyat_baglami()` sinyali üretiyor, `worker.py:424` hesaplayıp
**atıyor**, panelde hiç görünmüyor. Epiğin tamamı bunu düzeltiyor.

| # | İş | Tür |
|---|---|---|
| A1 | `Product`'a `sinyal, dip90, medyan90, yuzdelik, gecmis_gun, baglam_ts` + göç | DB |
| A2 | Worker hesapladığını yazsın (okunamayan taramada eski değer korunur) | arka uç |
| A3 | `betikler/baglam_doldur.py` — geçmişten geriye dönük doldurma, ağ isteği yok | arka uç |
| A4 | `UrunOzet`'e beş alan — liste ucu sinyali döndürsün, ek sorgu yok | arka uç |
| A5 | `GET /api/izlemeler/kivilcimlar?gun=90` — TEK sorgu, izleme id → fiyat dizisi | arka uç |
| A6 | `SinyalRozeti.tsx` — üç durum, yalnız renkle değil metinle de | arayüz |
| A7 | **"Geçmiş biriktiriliyor" hâli** — `gecmis_gun < 7` iken rozet yerine sayaç | arayüz |
| A8 | Kartı yeniden kur: rozet + `Kivilcim.tsx` + medyana fark | arayüz |

## B · Grafik (5 task, ~2 gün)

| # | İş | Tür |
|---|---|---|
| B1 | Zaman aralığı: `7g·30g·90g·1y·Tümü`, varsayılan 90g, seçim kalıcı | arayüz |
| B2 | `UrunDetay.seriler` — kaynak bazlı seri (`gecmis` kalır) | arka uç |
| B3 | Mağaza başına çizgi + aç/kapa; **varsayılan birleşik**, düğmeyle ayrılır | arayüz |
| B4 | Stok boşlukları — `STOKTA_YOK` grafikte kesik çizgi | ikisi |
| B5 | Tooltip: medyana fark, hangi mağaza, stok; dokunmatikte çalışsın | arayüz |

## C · Liste kontrolü (4 task, ~1 gün, tamamı istemci)

| # | İş |
|---|---|
| C1 | Sıralama — varsayılan "en iyi fırsat", null'lar sonda, `localeCompare('tr')` |
| C2 | Süzme — sinyal/set/mağaza/durum + arama; boş sonuç **sebebini** söyler (K56) |
| C3 | Kart ↔ tablo görünümü; 768px altında her zaman kart |
| C4 | Üst kutucuklar: "Hedefte 0" ve "Liste toplamı" yerine dip sayısı, bugünkü değişim, en büyük düşüş |

## D · Fırsatlar sayfası (3 task, ~5 saat, A'ya bağımlı)

| # | İş |
|---|---|
| D1 | `GET /api/firsatlar` — `gecmis_gun < en_az_gun` olan HİÇ girmez; sahte indirim girer ama **işaretli** |
| D2 | `Firsatlar.tsx` + gezinmede ikinci sıra; mobilde beşinci sekme sığıyor mu |
| D3 | Üç boş durumu ayır: ürün yok / geçmiş yetersiz / iyi fiyat yok |

## E · Uyarı kurma (5 task, ~2 gün)

| # | İş | Tür |
|---|---|---|
| E1 | `Watch.dusus_yuzdesi`, `Watch.yeniden_kur_gun` + göç | DB |
| E2 | Worker yüzde kuralı; sıra **acil → hedef → yüzde → dip**, referans 90g medyan | arka uç |
| E3 | Uyarı kurma arayüzü + canlı önizleme ("%15 → ~₺2.428 ve altı") | arayüz |
| E4 | Rearm görünür olsun — "3 gün sonra yeniden uyarır", tek tıkla yeniden kur | ikisi |
| E5 | Bot tarafına da aynı kurallar; ölü düğme testi yeni düğmeleri kapsasın | arka uç |

## F · Set ve mağaza (4 task, ~1,5 gün)

| # | İş |
|---|---|
| F1 | Bütçe aşımı: "₺14.826 aşıyor (%16)"; üye satırlarına sinyal rozeti |
| F2 | `GET /api/setler/{id}/gecmis` — set toplamının geçmişi; eksik günler **kesik** |
| F3 | Mağaza karşılaştırma tablosu; okunamayan kaynak **sebebiyle** görünür |
| F4 | Set şablonları — `WatchSet.sablon` sütunu var, arayüzde hiç kullanılmıyor |

## G · Bildirimler (3 task, ~6 saat)

| # | İş |
|---|---|
| G1 | Güne göre gruplama; sıralama kararlı kalmalı (K44) |
| G2 | Türe göre süzme + `?tur=` parametresi |
| G3 | Uyarıdan tek tık: mağazaya git (en ucuza) · 7 gün sustur · takipten çıkar |

## H · Dışa aktarma ve bakım (2 task, ~4 saat)

| # | İş |
|---|---|
| H1 | CSV — ayraç `;`, ondalık `,`, UTF-8 BOM (Türkçe Excel) |
| H2 | Panel ilk açılış rehberi — üç adım, örnek link |

## Sıra

1. **A1 → A2 → A3** (6sa) — sütunlar+worker+doldurma; bunlar olmadan görünen hiçbir şey yapılamaz
2. **A4 → A6 → A7 → A8** (10sa) — **ilk görünür sıçrama burada**
3. **A5 + kıvılcım** (3sa)
4. **B1** (2sa) — iki saatte grafiği kullanışlı yapar
5. **C1 → C2 → C4** (8sa)
6. **D1 → D2 → D3** (6sa) — A bitmişse neredeyse bedava
7. **E1 → E5** (14sa)
8. **B2 → B3** (7sa) — bot duvarları bağlanmadan çoğu üründe tek çizgi kalır
9. **F1 → F3 → F2 → F4** (12sa)
10. **Kalanlar** (18sa) — cilalama, sıra kritik değil

**Paralel:** sekiz bot duvarı ürününe akakçe kaynağı bağlamak + worker'ın
sürekli açık kalması. Sinyal 7 günlük geçmiş istiyor, kıvılcım 90 gün; şu an
en uzun geçmiş 3 gün. A epiği bittiğinde bile ekranlar bir hafta
"geçmiş biriktiriliyor" gösterecek — arıza değil, A7 tam bunun için var.

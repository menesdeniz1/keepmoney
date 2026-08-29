/**
 * BACKLOG E3 — uyarı kurma arayüzü. Saf mantık (canlı önizleme, geçmiş
 * yeterlilik kontrolü, özet cümlesi), `siralama.ts`/`suzme.ts` ile aynı
 * katman ayrımı — test kolaylığı ve `react-refresh/only-export-components`
 * kuralından kaçınma.
 *
 * VERİ MODELİ: Hedef fiyat ve yüzde düşüş BİRBİRİNİ DIŞLAMAZ, İKİSİ BİRDEN
 * kurulabilir — worker.py (BACKLOG E2) tam da bunun için bir ÖNCELİK
 * sırası uyguluyor (acil → hedef → yüzde → dip): yalnızca TEK bir seçenek
 * hiç kurulabilseydi öncelik sırasına gerek kalmazdı. "Dip kırılınca"
 * KAPATILABİLEN bir seçenek DEĞİL — `Watch`te bunu temsil eden bir sütun
 * yok, worker her zaman uyguluyor; arayüzde sahte bir anahtar göstermek
 * yerine her zaman-açık bir bilgi satırı olarak sunuluyor.
 */
import type { Izleme } from '../api/tipler'
import { tl } from './bicim'

/**
 * `/api/firsatlar`'daki `FIRSAT_ESIGI_GUN` ile AYNI durum, FARKLI eşik:
 * worker.py'nin yüzde kuralı `baglam.gun_sayisi >= 7` şartına tabi (DIP
 * kuralıyla aynı eşik, BACKLOG E2) — hiçbir API alanında dışa açılmıyor,
 * burada elle eşleniyor. `worker.py`deki sayı değişirse burası da
 * güncellenmeli.
 */
export const YUZDE_ESIGI_GUN = 7

export const YENIDEN_KUR_SECENEKLERI: { deger: number; etiket: string }[] = [
  { deger: 3, etiket: '3 gün' },
  { deger: 7, etiket: '7 gün' },
  { deger: 30, etiket: '30 gün' },
  { deger: 0, etiket: 'hiç' },
]

// `Watch.yeniden_kur_gun`da `NULL` = "varsayılan" (E1'in model yorumu).
// Kullanıcı özellikle bir süre SEÇTİĞİNDE bunu her zaman AÇIK bir değer
// olarak göndeririz (null değil) — "seçtim" ile "hiç dokunmadım" farklı
// niyetlerdir.
export const YENIDEN_KUR_VARSAYILAN = 7

/** Kabul ölçütü: "Yüzde seçilince canlı önizleme". `medyan90 * (1 -
 *  yüzde/100)` — E2'nin worker.py'de kullandığı AYNI formül. */
export function yuzdeOnizlemesi(
  medyan90: number | null,
  yuzde: number | null,
): number | null {
  if (medyan90 == null || yuzde == null || !Number.isFinite(yuzde) || yuzde <= 0) {
    return null
  }
  return medyan90 * (1 - yuzde / 100)
}

/** Kabul ölçütü: "Geçmiş yetersizken yüzde seçeneği pasif". */
export function yuzdeKullanilabilirMi(gecmisGun: number | null): boolean {
  return gecmisGun != null && gecmisGun >= YUZDE_ESIGI_GUN
}

export interface UyariTaslagi {
  hedefFiyat: number | null
  yuzde: number | null
  yenidenKurGun: number
}

/** Mevcut izlemeden başlangıç taslağı çıkarır — sayfa ilk açıldığında
 *  form GERÇEK kayıtlı durumla başlasın diye. */
export function taslakBaslangici(izleme: Pick<Izleme, 'hedef_fiyat' | 'dusus_yuzdesi' | 'yeniden_kur_gun'>): UyariTaslagi {
  return {
    hedefFiyat: izleme.hedef_fiyat,
    yuzde: izleme.dusus_yuzdesi,
    yenidenKurGun: izleme.yeniden_kur_gun ?? YENIDEN_KUR_VARSAYILAN,
  }
}

/** Kabul ölçütü: "Özet cümlesi seçili kuralları doğru anlatıyor".
 *
 * İKİSİ BİRDEN kuruluysa "ya da" ile birleşir (BACKLOG'un kendi örneği:
 * "₺5.500 altına inince ya da 90 günlük medyanın %15 altına düşünce").
 * HİÇBİRİ kurulu değilse yalnızca dip kuralı anlatılır — rearm cümlesi bu
 * durumda EKLENMEZ: DIP, `_hatirlatma_zamani`/cooldown KULLANMIYOR
 * (worker.py'de `son_bildirim_ts` güncellenmiyor), yani "N gün susar"
 * DIP-yalnız modda gerçeği yansıtmaz.
 */
export function ozetCumlesi(taslak: UyariTaslagi, medyan90: number | null): string {
  const kosullar: string[] = []

  if (taslak.hedefFiyat != null) {
    kosullar.push(`${tl(taslak.hedefFiyat)} altına inince`)
  }
  if (taslak.yuzde != null) {
    const esik = yuzdeOnizlemesi(medyan90, taslak.yuzde)
    kosullar.push(
      `90 günlük medyanın %${taslak.yuzde} altına düşünce` +
        (esik != null ? ` (yaklaşık ${tl(esik)} ve altı)` : ''),
    )
  }

  if (kosullar.length === 0) {
    return 'Ürün 90 günün ya da tüm zamanların dibini kırınca haber verilir.'
  }

  const rearm =
    taslak.yenidenKurGun === 0
      ? 'bir daha haber verilmez'
      : `uyarıdan sonra ${taslak.yenidenKurGun} gün susar`
  return `${kosullar.join(' ya da ')} haber verilir; ${rearm}.`
}

/** Kaydet'e basınca sunucuya gidecek PATCH gövdesi — açık `null`, boş
 *  bırakılan alanı TEMİZLER (mevcut PATCH sözleşmesi, `ortak.py`). */
export function taslaktanPatchGovdesi(taslak: UyariTaslagi) {
  return {
    hedef_fiyat: taslak.hedefFiyat,
    dusus_yuzdesi: taslak.yuzde,
    yeniden_kur_gun: taslak.yenidenKurGun,
  }
}

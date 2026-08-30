/**
 * BACKLOG C4 — panel üst kutucukları. Saf mantık, `UstKutucuklar.tsx`
 * bunu tüketir; `siralama.ts`/`suzme.ts` ile aynı katman ayrımı.
 */
import type { Izleme } from '../api/tipler'
import { turkiyeGunAnahtari } from './bicim'

export function dipteKacUrun(izlemeler: Izleme[]): number {
  return izlemeler.filter((i) => i.urun.sinyal === 'dip').length
}

function ayniTurkiyeGunuMu(iso: string, simdi: Date): boolean {
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return turkiyeGunAnahtari(d) === turkiyeGunAnahtari(simdi)
}

/**
 * "Bugün M fiyat değişti". `kivilcimlar` (varsayılan 90 günlük, panelin
 * zaten çektiği veri — YENİ istek AÇILMAZ) bugünü her zaman kapsar; asıl
 * soru bu ürünün BUGÜN gerçekten okunup okunmadığı — `son_kontrol` bunu
 * söylüyor. Okunmuş ama fiyatı DEĞİŞMEMİŞ ürün sayılmaz: kıvılcımın son
 * iki günü aynıysa "değişti" değildir.
 */
export function bugunDegisenSayisi(
  izlemeler: Izleme[],
  kivilcimlar: Record<string, number[]> | undefined,
  simdi: Date = new Date(),
): number {
  if (!kivilcimlar) return 0
  let sayac = 0
  for (const i of izlemeler) {
    if (!i.urun.son_kontrol || !ayniTurkiyeGunuMu(i.urun.son_kontrol, simdi)) continue
    const veri = kivilcimlar[String(i.id)]
    if (!veri || veri.length < 2) continue
    if (veri[veri.length - 1] !== veri[veri.length - 2]) sayac++
  }
  return sayac
}

export interface EnBuyukDusus {
  izlemeId: number
  ad: string
  tutar: number
}

/**
 * "Son 30 günde en büyük düşüş" — `kivilcimlar30` AYRI bir 30 günlük
 * istekten gelir (bkz. `kancalar.ts::useKivilcimlar30Gun`), varsayılan
 * 90 günlük veriden DEĞİL: kıvılcım dizisi tarih taşımıyor, 90 günlük
 * diziden "son 30 gün"ü doğru kesmenin yolu yok.
 *
 * Dizinin İLK değeri ile SON değeri karşılaştırılır (aynı felsefe
 * `kivilcimDegisim.ts` ile) — yükselip sonra düşen bir ürünün ARADAKİ
 * en büyük düşüşünü değil, PENCERENİN BAŞI/SONU farkını yakalar. Yalnızca
 * GERÇEKTEN düşen (`tutar > 0`) ürünler adaydır.
 */
export function enBuyukDusus(
  izlemeler: Izleme[],
  kivilcimlar30: Record<string, number[]> | undefined,
): EnBuyukDusus | null {
  if (!kivilcimlar30) return null
  let enIyi: EnBuyukDusus | null = null
  for (const i of izlemeler) {
    const veri = kivilcimlar30[String(i.id)]
    if (!veri || veri.length < 2) continue
    const ilk = veri[0]
    const son = veri[veri.length - 1]
    // `kivilcimDegisim.ts`'teki AYNI muhafaza — `noUncheckedIndexedAccess`
    // dizi elemanını `undefined` sayar, `veri.length >= 2` bunu pratikte
    // engeller ama tip sistemine bunu göstermenin yolu bu.
    if (ilk === undefined || son === undefined) continue
    const tutar = ilk - son
    if (tutar > 0 && (enIyi === null || tutar > enIyi.tutar)) {
      enIyi = { izlemeId: i.id, ad: i.urun.ad, tutar }
    }
  }
  return enIyi
}

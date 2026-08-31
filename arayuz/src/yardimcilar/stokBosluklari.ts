/**
 * BACKLOG B4 — grafikte stok boşlukları. Saf mantık: art arda gelen
 * "stokta yok" günlerini tek bir aralığa indirger (`FiyatGrafigi.tsx` bunu
 * arka planda soluk taramalı bir `ReferenceArea` olarak çizer). Ayrı
 * dosyada olması bilinçli — `grafikAraligi.ts` ile AYNI gerekçe: saf
 * fonksiyon, recharts'a dokunmadan test edilebilir.
 */
import type { FiyatNoktasi } from '../api/tipler'

export interface StokBosluguAraligi {
  baslangic: string
  bitis: string
}

/**
 * `veri` GÜNE GÖRE SIRALI olmalı (backend zaten böyle döner). Art arda
 * `stokta: false` olan noktalar TEK aralığa birleşir — grafikte her gün
 * ayrı bir `ReferenceArea` yerine tek bir taramalı blok görünsün diye.
 */
export function stokBosluklariniBul(
  veri: Pick<FiyatNoktasi, 'gun' | 'stokta'>[],
): StokBosluguAraligi[] {
  const araliklar: StokBosluguAraligi[] = []
  let baslangic: string | null = null
  let onceki: string | null = null

  for (const nokta of veri) {
    if (!nokta.stokta) {
      if (baslangic === null) baslangic = nokta.gun
      onceki = nokta.gun
    } else if (baslangic !== null) {
      araliklar.push({ baslangic, bitis: onceki! })
      baslangic = null
    }
  }
  if (baslangic !== null) araliklar.push({ baslangic, bitis: onceki! })

  return araliklar
}

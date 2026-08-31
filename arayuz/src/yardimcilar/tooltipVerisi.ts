/**
 * BACKLOG B5 — grafik tooltip'ini zenginleştirir: tarih · fiyat · o günkü
 * medyana göre fark · hangi mağaza · stok durumu. Saf mantık — `FiyatGrafigi.
 * tsx` bunu hem fare hover'ında (recharts'ın `Tooltip content`i) hem
 * dokunmatik "sabitle" modunda AYNI şekilde kullanır, ikisi arasında
 * ıraksama olmasın diye.
 */
import type { Kaynak } from '../api/tipler'

export interface TooltipVerisi {
  gun: string
  fiyat: number | null
  stokta: boolean
  /** `null` = o gün için medyan bilinmiyor (yeterli geçmiş yok). */
  medyanFarki: number | null
  /** `null` = hangi mağazadan geldiği bilinmiyor (çok kaynaklı BİRLEŞİK
   *  görünüm — bkz. `FiyatGrafigi.tsx`, B3'ün "Mağazalara ayır"ı tam bu
   *  soruyu cevaplamak için var). */
  magaza: string | null
  tumZamanlarDibiMi: boolean
}

/** Kullanıcıya satıcı ismi host'tan daha anlamlı; yoksa host'a düşer. */
export function magazaAdi(kaynak: Pick<Kaynak, 'satici' | 'host'>): string {
  return kaynak.satici ?? kaynak.host
}

export function tooltipVerisiOlustur(
  nokta: { gun: string; fiyat: number | null; stokta: boolean },
  opts: {
    medyan90?: number | null
    tumZamanlarDibiTarih?: string | null
    magaza?: string | null
  } = {},
): TooltipVerisi {
  const medyan90 = opts.medyan90
  const medyanFarki = nokta.fiyat != null && medyan90 != null && medyan90 !== 0
    ? ((nokta.fiyat - medyan90) / medyan90) * 100
    : null
  return {
    gun: nokta.gun,
    fiyat: nokta.fiyat,
    stokta: nokta.stokta,
    medyanFarki,
    magaza: opts.magaza ?? null,
    tumZamanlarDibiMi: !!opts.tumZamanlarDibiTarih && nokta.gun === opts.tumZamanlarDibiTarih,
  }
}

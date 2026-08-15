/** Biçimleme yardımcıları — hepsi tr-TR. */

const TL = new Intl.NumberFormat('tr-TR', {
  style: 'currency',
  currency: 'TRY',
  maximumFractionDigits: 2,
})

const TL_KISA = new Intl.NumberFormat('tr-TR', {
  style: 'currency',
  currency: 'TRY',
  maximumFractionDigits: 0,
})

export function tl(deger: number | null | undefined): string {
  if (deger === null || deger === undefined) return '—'
  return TL.format(deger)
}

export function kisaTl(deger: number | null | undefined): string {
  if (deger === null || deger === undefined) return '—'
  return TL_KISA.format(deger)
}

/** Sunucu naive UTC gönderir; kullanıcıya Türkiye saatiyle gösterilir. */
export function tarih(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return d.toLocaleDateString('tr-TR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'Europe/Istanbul',
  })
}

export function goreliZaman(iso: string | null | undefined): string {
  if (!iso) return 'hiç'
  const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  const dakika = (Date.now() - d.getTime()) / 60000
  if (dakika < 1) return 'az önce'
  if (dakika < 60) return `${Math.round(dakika)} dk önce`
  if (dakika < 60 * 48) return `${Math.round(dakika / 60)} saat önce`
  return `${Math.round(dakika / 1440)} gün önce`
}

export function yuzde(deger: number): string {
  const ok = deger < 0 ? '↓' : '↑'
  return `${ok}%${Math.abs(deger).toFixed(1).replace('.', ',')}`
}

/** Hedefe kalan mesafe — kullanıcı "ne kadar kaldı" diye soruyor. */
export function hedefeKalan(
  guncel: number | null,
  hedef: number | null,
): { hedefte: boolean; fark: number } | null {
  if (guncel === null || hedef === null) return null
  return { hedefte: guncel <= hedef, fark: guncel - hedef }
}

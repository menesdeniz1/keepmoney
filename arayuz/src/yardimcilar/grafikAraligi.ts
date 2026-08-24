/**
 * BACKLOG B1 — grafik zaman aralığı seçimi. Saf mantık; `FiyatGrafigi.tsx`
 * bunu import eder. Ayrı dosyada olması bilinçli: aynı fonksiyonlar
 * component dosyasından export edilseydi ESLint `react-refresh/
 * only-export-components` uyarısı verirdi (Fast Refresh yalnızca bir
 * dosya SADECE component export ettiğinde çalışır) — `bicim.ts` ile aynı
 * ayrım (saf mantık / UI).
 */
import type { FiyatNoktasi } from '../api/tipler'

export type GrafikAraligi = '7g' | '30g' | '90g' | '1y' | 'tumu'

export const GRAFIK_ARALIK_SECENEKLERI: {
  deger: GrafikAraligi
  etiket: string
  gun: number | null
}[] = [
  { deger: '7g', etiket: '7g', gun: 7 },
  { deger: '30g', etiket: '30g', gun: 30 },
  { deger: '90g', etiket: '90g', gun: 90 },
  { deger: '1y', etiket: '1y', gun: 365 },
  { deger: 'tumu', etiket: 'Tümü', gun: null },
]

export const GRAFIK_ARALIK_ANAHTARI = 'km:grafik-araligi'
// Analiz penceresiyle AYNI (analiz.py::MIN_GUN'un baktığı 90 günlük pencere
// ile tutarlı) — grafik açıldığında gördüğün ile "bu iyi fiyat mı" sorusunun
// cevabı aynı zaman dilimine bakmış olsun.
export const GRAFIK_ARALIK_VARSAYILAN: GrafikAraligi = '90g'

export function grafikAraligiGecerliMi(deger: string | null): deger is GrafikAraligi {
  return GRAFIK_ARALIK_SECENEKLERI.some((s) => s.deger === deger)
}

export function grafikBaslangicAraligi(): GrafikAraligi {
  try {
    const kayitli = localStorage.getItem(GRAFIK_ARALIK_ANAHTARI)
    return grafikAraligiGecerliMi(kayitli) ? kayitli : GRAFIK_ARALIK_VARSAYILAN
  } catch {
    // Gizli sekme / depolama kapalı — sessizce varsayılana düş.
    return GRAFIK_ARALIK_VARSAYILAN
  }
}

/** Bugünden `gun` gün öncesinin ISO tarihi ("YYYY-MM-DD") — `FiyatNoktasi.gun`
 * ile AYNI biçim, sözlük sırasıyla doğrudan karşılaştırılabilir. */
export function grafikSinirTarihi(gun: number): string {
  const d = new Date()
  d.setDate(d.getDate() - gun)
  return d.toISOString().slice(0, 10)
}

export function grafikAraligaGoreSuz(
  gecmis: FiyatNoktasi[],
  gun: number | null,
): FiyatNoktasi[] {
  if (gun === null) return gecmis
  const sinir = grafikSinirTarihi(gun)
  return gecmis.filter((n) => n.gun >= sinir)
}

/**
 * Bir aralık düğmesi ne zaman ANLAMSIZ (devre dışı)? Veri, o aralığın
 * BAŞLANGICINDAN daha geriye gitmiyorsa — yani seçmek "Tümü" ile AYNI
 * sonucu verir. "Tümü" bu kuralın DIŞINDA: ne kadar veri olursa olsun
 * her zaman geçerli bir seçimdir, asla "yetersiz" olamaz.
 */
export function grafikAraligiYetersiz(
  gecmis: FiyatNoktasi[],
  gun: number | null,
): boolean {
  if (gun === null) return false
  const enEski = gecmis[0]
  if (!enEski) return true
  return enEski.gun >= grafikSinirTarihi(gun)
}

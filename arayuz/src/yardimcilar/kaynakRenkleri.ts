/**
 * BACKLOG B3 — mağaza başına çizgi. Saf mantık: renk/desen ataması,
 * çoklu-seri grafiği için birleşik veri tablosu, en ucuz kaynağın tespiti.
 * `FiyatGrafigi.tsx` bunları çizmek için kullanır — recharts bileşenleri
 * bu depoda birim testli değil (bkz. FiyatGrafigi.tsx'in kendisi de test
 * edilmiyor), o yüzden burada test edilebilir kısmı ayırıyoruz.
 */
import type { KaynakSerisi } from '../api/tipler'

// Tailwind "600" tonları — FiyatGrafigi.tsx'teki SINYAL_RENGI ile aynı
// doygunluk düzeyi: hem açık hem karanlık temada çizgi olarak okunur.
const RENK_PALETI = [
  '#0ea5e9', // mavi
  '#16a34a', // yeşil
  '#dc2626', // kırmızı
  '#9333ea', // mor
  '#ea580c', // turuncu
  '#0d9488', // teal
  '#db2777', // pembe
  '#65a30d', // olive
]

// Yalnızca 2'den FAZLA kaynakta devreye girer (BACKLOG: "ikiden fazla
// kaynakta renk körlüğü için çizgi deseni de değişir") — 1-2 kaynakta
// renk tek başına yeterince ayırt edici, gereksiz karmaşıklık katmıyoruz.
const DESEN_PALETI = ['4 3', '2 2', '8 3 2 3', '1 3', '6 2 2 2']

/** Host adının basit, kararlı bir hash'i — kaynak eklenip çıkınca (dizideki
 *  SIRA değişince) renkler KAYMASIN diye index yerine bu kullanılır. */
function hostHash(host: string): number {
  let h = 0
  for (let i = 0; i < host.length; i++) {
    h = (h * 31 + host.charCodeAt(i)) >>> 0
  }
  return h
}

export interface KaynakStili {
  renk: string
  desen?: string
}

export function kaynakStili(host: string, toplamKaynakSayisi: number): KaynakStili {
  const renk = RENK_PALETI[hostHash(host) % RENK_PALETI.length]!
  if (toplamKaynakSayisi <= 2) return { renk }
  const desen = DESEN_PALETI[hostHash(host) % DESEN_PALETI.length]!
  return { renk, desen }
}

/** Her kaynağın kendi günlerini tek bir geniş tabloya birleştirir —
 *  recharts'ın çoklu-çizgi deseni: `{ gun, k12: 1000, k7: 950 }`. Bir
 *  kaynağın o gün noktası yoksa alan hiç yazılmaz (undefined) — recharts
 *  bunu `connectNulls=false` ile zaten kesik çizer. BACKLOG B4 — nokta VAR
 *  ama stokta yoksa `fiyat: null` gelir, AYNI şekilde kesik çizilir. */
export function birlesikVeri(
  seriler: KaynakSerisi[],
): Record<string, number | string | null>[] {
  const gunler = new Set<string>()
  for (const s of seriler) for (const n of s.noktalar) gunler.add(n.gun)

  return Array.from(gunler).sort().map((gun) => {
    const satir: Record<string, number | string | null> = { gun }
    for (const s of seriler) {
      const nokta = s.noktalar.find((n) => n.gun === gun)
      if (nokta) satir[anahtar(s.kaynak_id)] = nokta.fiyat
    }
    return satir
  })
}

export function anahtar(kaynakId: number): string {
  return `k${kaynakId}`
}

/**
 * BACKLOG B3 kabul ölçütü: "kaynak gizlenince y ekseni kalanlara göre
 * ölçekleniyor". Gizli kaynağın hiçbir noktası aralığa katılmaz — ölçek
 * yalnızca GÖRÜNÜR çizgilere göre daralır/genişler. Hiç görünür kaynak
 * kalmazsa null (grafik bileşeni bunu 0-0'a düşürür).
 */
export function gorunurFiyatAraligi(
  seriler: KaynakSerisi[],
  gizliKaynaklar: ReadonlySet<number>,
): { enDusuk: number; enYuksek: number } | null {
  // BACKLOG B4 — stok-yok noktalarının `fiyat: null`i buraya karışırsa
  // `Math.min(...[10, null])` `null`ı 0'a çevirip aralığı bozar; süzülür.
  const fiyatlar = seriler
    .filter((s) => !gizliKaynaklar.has(s.kaynak_id))
    .flatMap((s) => s.noktalar.map((n) => n.fiyat))
    .filter((f): f is number => f != null)
  if (fiyatlar.length === 0) return null
  return { enDusuk: Math.min(...fiyatlar), enYuksek: Math.max(...fiyatlar) }
}

/** Bir serinin EN SON bilinen (null olmayan) fiyatı — BACKLOG B4: dizinin
 *  son noktası stok-yok boşluğu olabilir, o zaman `fiyat: null` gelir ve
 *  "en ucuz" karşılaştırması `null < sayı` gibi anlamsız bir işleme düşer. */
function sonFiyat(s: KaynakSerisi): number | null {
  for (let i = s.noktalar.length - 1; i >= 0; i--) {
    const f = s.noktalar[i]!.fiyat
    if (f != null) return f
  }
  return null
}

/** En son günün en düşük fiyatını taşıyan kaynak — "şu an en ucuz mağaza
 *  hangisi" sorusunun cevabı, F1/F3'teki "en ucuz" tanımıyla aynı ilke
 *  (canlı/güncel duruma bakar, tarihsel en düşüğe değil). */
export function enUcuzKaynakId(seriler: KaynakSerisi[]): number | null {
  const doluSeriler = seriler
    .map((s) => ({ s, fiyat: sonFiyat(s) }))
    .filter((x): x is { s: KaynakSerisi; fiyat: number } => x.fiyat != null)
  if (doluSeriler.length === 0) return null
  return doluSeriler.reduce((en, x) => (x.fiyat < en.fiyat ? x : en)).s.kaynak_id
}

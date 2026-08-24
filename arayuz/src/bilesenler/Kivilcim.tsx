import type { Sinyal } from '../api/tipler'

/**
 * Kart üzerindeki minik fiyat grafiği (BACKLOG A8).
 *
 * KÜTÜPHANE KULLANILMADI — bilerek: recharts bu boyutta (35 örnekte) ağır,
 * `FiyatGrafigi.tsx` tam da bu yüzden ayrı bir kod bölmesinde (lazy) yükleniyor
 * ve YALNIZCA detay sayfasında. Panelde 35 recharts örneği donma yaratırdı.
 * İnline SVG'nin burada tek maliyeti birkaç sayı hesabı.
 *
 * ANİMASYON YOK — bilerek: `prefers-reduced-motion` kuralına aykırı bir
 * "çizilme" efekti eklemek yerine hiç eklenmedi; kabul ölçütünü baştan
 * karşılıyor, ayrı bir media query dalına gerek kalmadı.
 */

const GENISLIK = 56
const YUKSEKLIK = 20
const DUSEY_BOSLUK = 2.5 // işaretçi dairesi üstten/alttan taşmasın

const RENK: Record<Sinyal, string> = {
  dip: 'text-green-600 dark:text-green-400',
  ucuz: 'text-yellow-600 dark:text-yellow-400',
  pahali: 'text-red-600 dark:text-red-400',
}
const NOTR_RENK = 'text-slate-400 dark:text-slate-600'

export default function Kivilcim({
  veri,
  sinyal,
}: {
  veri: number[] | undefined
  sinyal: Sinyal | null
}) {
  // Yer ÖNCEDEN AYRILMIŞ: veri gelmeden (ya da hiç gelmeden) önce de aynı
  // boşluk duruyor — kıvılcım ucu 500 ms gecikse bile kart sıçramıyor.
  if (!veri || veri.length < 2) {
    return <span style={{ display: 'inline-block', width: GENISLIK, height: YUKSEKLIK }} />
  }

  const enDusuk = Math.min(...veri)
  const enYuksek = Math.max(...veri)
  const aralik = enYuksek - enDusuk || 1 // hepsi aynı fiyatsa sıfıra bölme yok

  const noktalar = veri.map((fiyat, i) => {
    const x = (i / (veri.length - 1)) * GENISLIK
    const y =
      YUKSEKLIK -
      DUSEY_BOSLUK -
      ((fiyat - enDusuk) / aralik) * (YUKSEKLIK - 2 * DUSEY_BOSLUK)
    return [x, y] as const
  })

  const sonNokta = noktalar[noktalar.length - 1]
  // Mantıksal olarak imkânsız (`veri.length >= 2` üstte kontrol edildi,
  // `noktalar` aynı uzunlukta) — ama `!` ile bastırmak yerine gerçek bir
  // guard: tip güvenliği çalışma zamanı güvenliğinden ayrılmasın.
  if (!sonNokta) return null
  const [sonX, sonY] = sonNokta

  return (
    <svg
      viewBox={`0 0 ${GENISLIK} ${YUKSEKLIK}`}
      width={GENISLIK}
      height={YUKSEKLIK}
      className={sinyal ? RENK[sinyal] : NOTR_RENK}
      role="img"
      aria-label="90 günlük fiyat eğilimi"
    >
      <polyline
        points={noktalar.map(([x, y]) => `${x},${y}`).join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={sonX} cy={sonY} r={1.6} fill="currentColor" />
    </svg>
  )
}

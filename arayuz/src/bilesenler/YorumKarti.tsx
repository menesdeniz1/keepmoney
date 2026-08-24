/**
 * "Bu iyi bir fiyat mı?" kartı — ürünün kullanıcıya dokunduğu yer.
 *
 * ÖNEMLİ: yorum metni burada ÜRETİLMEZ, backend'den gelir. Aynı cümle web'de,
 * Telegram bildiriminde ve e-postada birebir aynı çıkmalı (bkz. analiz.yorum).
 * Metni istemcide kurmak, üç yerde üç farklı ifade demek olurdu.
 */
import { AlertTriangle, TrendingDown, TrendingUp, Minus } from 'lucide-react'

import type { Baglam } from '../api/tipler'
import { tl } from '../yardimcilar/bicim'

const SINYAL_STILI: Record<Baglam['sinyal'], string> = {
  dip: 'border-green-300 bg-green-50 dark:border-green-900 dark:bg-green-950/40',
  ucuz: 'border-yellow-300 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950/40',
  pahali: 'border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/40',
}

const TREND_IKON = {
  dusuyor: TrendingDown,
  yukseliyor: TrendingUp,
  sabit: Minus,
} as const

const TREND_METNI = {
  dusuyor: 'Fiyat düşüş eğiliminde',
  yukseliyor: 'Fiyat yükseliş eğiliminde',
  sabit: 'Fiyat yatay seyrediyor',
} as const

export default function YorumKarti({
  baglam,
  gecmisGun,
}: {
  baglam: Baglam | null
  /**
   * BACKLOG A7: panel kartındaki SinyalRozeti ile AYNI CÜMLE — "geçmiş
   * biriktiriliyor". `gecmis_gun` `UrunOzet`'ten (A4) geldiği için `baglam`
   * null olsa bile biliniyor; jenerik "birkaç gün içinde" yerine somut
   * sayı gösterilebilir. Sabit bir eşik ("N/7 gün" gibi) YAZILMIYOR — bkz.
   * SinyalRozeti.tsx'teki aynı gerekçe: backend eşiği (`analiz.MIN_GUN`)
   * hiçbir API alanında dışa açılmıyor.
   */
  gecmisGun: number | null
}) {
  if (!baglam) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm
                      text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
        {gecmisGun
          ? <>Geçmiş biriktiriliyor — {gecmisGun} günlük veri var, birkaç gün
              daha içinde bu fiyatın iyi olup olmadığını söyleyebileceğim.</>
          : <>Geçmiş biriktiriliyor — henüz hiç fiyat okunmadı, ilk tarama
              turundan sonra veri birikmeye başlar.</>}
      </div>
    )
  }

  const TrendIkonu = TREND_IKON[baglam.trend_yonu]

  return (
    <div className={`rounded-lg border p-4 ${SINYAL_STILI[baglam.sinyal]}`}>
      <p className="text-base font-medium leading-relaxed">{baglam.yorum}</p>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-slate-500 dark:text-slate-400">90 günün dibi</dt>
          <dd className="font-mono font-medium">{tl(baglam.dip90)}</dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Medyan</dt>
          <dd className="font-mono font-medium">{tl(baglam.medyan90)}</dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Tüm zamanlar dibi</dt>
          <dd className="font-mono font-medium">{tl(baglam.tum_zamanlar_dibi)}</dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-400">Ucuzluk yüzdeliği</dt>
          <dd className="font-mono font-medium">%{baglam.yuzdelik}</dd>
        </div>
      </dl>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-600
                      dark:text-slate-400">
        <span className="inline-flex items-center gap-1">
          <TrendIkonu size={14} />
          {TREND_METNI[baglam.trend_yonu]}
        </span>
        <span>{baglam.gun_sayisi} günlük veri</span>
        {baglam.sahte_indirim && (
          <span className="inline-flex items-center gap-1 rounded bg-red-100 px-2 py-0.5
                           font-medium text-red-800 dark:bg-red-950 dark:text-red-300">
            <AlertTriangle size={13} />
            Sahte indirim şüphesi
          </span>
        )}
      </div>
    </div>
  )
}

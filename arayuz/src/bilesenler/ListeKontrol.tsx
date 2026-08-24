import type { SiralamaSecenegi } from '../yardimcilar/siralama'
import { SIRALAMA_SECENEKLERI } from '../yardimcilar/siralama'

/**
 * Panel liste kontrolü (BACKLOG C1). Şimdilik yalnızca sıralama; C2
 * (süzme çipleri) aynı satıra eklenecek — bu yüzden ayrı, adı genel
 * "ListeKontrol" (yalnızca "Siralama" değil).
 */
export default function ListeKontrol({
  secili,
  onDegistir,
}: {
  secili: SiralamaSecenegi
  onDegistir: (secenek: SiralamaSecenegi) => void
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor="panel-siralama" className="text-slate-500 dark:text-slate-400">
        Sırala:
      </label>
      <select
        id="panel-siralama"
        value={secili}
        onChange={(e) => onDegistir(e.target.value as SiralamaSecenegi)}
        className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm
                   dark:border-slate-700 dark:bg-slate-950"
      >
        {SIRALAMA_SECENEKLERI.map((s) => (
          <option key={s.deger} value={s.deger}>
            {s.etiket}
          </option>
        ))}
      </select>
    </div>
  )
}

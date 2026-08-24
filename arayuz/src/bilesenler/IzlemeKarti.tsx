import { Link } from 'react-router-dom'
import { BellOff, Lock, PauseCircle } from 'lucide-react'

import type { Izleme } from '../api/tipler'
import SinyalRozeti from './SinyalRozeti'
import { goreliZaman, hedefeKalan, kisaTl, tl } from '../yardimcilar/bicim'

export default function IzlemeKarti({ izleme }: { izleme: Izleme }) {
  const { urun } = izleme
  const durum = hedefeKalan(urun.guncel_fiyat, izleme.hedef_fiyat)
  const susturulmus =
    izleme.sustur_bitis !== null && new Date(`${izleme.sustur_bitis}Z`) > new Date()

  return (
    <Link
      to={`/izleme/${izleme.id}`}
      className="block rounded-lg border border-slate-200 bg-white p-4 transition
                 hover:border-slate-300 hover:shadow-sm dark:border-slate-800
                 dark:bg-slate-900 dark:hover:border-slate-700"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-medium">{urun.ad}</h3>
          <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
            {urun.guncel_satici ?? 'bilinmiyor'} ·{' '}
            {goreliZaman(urun.son_kontrol)}
          </p>
          {/* BACKLOG A7: sinyal ürüne tıklamadan görünsün. `null` iken
              SinyalRozeti kendiliğinden nötr "geçmiş biriktiriliyor" hâlini
              çiziyor — burada ayrıca dallanmaya gerek yok. */}
          <div className="mt-1.5">
            <SinyalRozeti
              sinyal={urun.sinyal}
              yuzdelik={urun.yuzdelik}
              gecmisGun={urun.gecmis_gun}
            />
          </div>
        </div>

        <div className="shrink-0 text-right">
          <div className="font-mono text-lg font-semibold">
            {tl(urun.guncel_fiyat)}
          </div>
          {durum && (
            <div
              className={`text-xs font-medium ${
                durum.hedefte
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-slate-500 dark:text-slate-400'
              }`}
            >
              {durum.hedefte
                ? '🎯 hedefte'
                : `hedefe ${kisaTl(durum.fark)} kaldı`}
            </div>
          )}
        </div>
      </div>

      {(susturulmus || !izleme.aktif || izleme.kilitli) && (
        <div className="mt-2 flex gap-2 text-xs text-slate-500 dark:text-slate-400">
          {!izleme.aktif && (
            <span className="inline-flex items-center gap-1">
              <PauseCircle size={13} /> duraklatıldı
            </span>
          )}
          {susturulmus && (
            <span className="inline-flex items-center gap-1">
              <BellOff size={13} /> susturuldu
            </span>
          )}
          {izleme.kilitli && (
            <span className="inline-flex items-center gap-1">
              <Lock size={13} /> {tl(izleme.kilitli_fiyat)} sabit
            </span>
          )}
        </div>
      )}
    </Link>
  )
}

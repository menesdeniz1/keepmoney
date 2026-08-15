import { Link } from 'react-router-dom'

import { useHepsiOkundu, useUyariOkundu, useUyarilar } from '../api/kancalar'
import type { UyariTuru } from '../api/tipler'
import { goreliZaman } from '../yardimcilar/bicim'

const TUR_ETIKETI: Record<UyariTuru, string> = {
  HEDEF: '🎯 Hedef',
  DIP: '📉 Dip',
  SAHTE_INDIRIM: '🎭 Sahte indirim',
  SET_HEDEF: '📦 Set bütçesi',
  KAYNAK_BOZUK: '⚠️ Kaynak',
}

export default function Uyarilar() {
  const { data: uyarilar } = useUyarilar()
  const okundu = useUyariOkundu()
  const hepsi = useHepsiOkundu()

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Bildirimler</h1>
        <button
          onClick={() => hepsi.mutate()}
          className="text-sm text-slate-500 hover:underline"
        >
          Hepsini okundu işaretle
        </button>
      </div>

      <div className="space-y-2">
        {uyarilar?.map((u) => (
          <div
            key={u.id}
            className={`rounded-lg border p-4 ${
              u.okundu
                ? 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900'
                : 'border-slate-300 bg-slate-50 dark:border-slate-700 dark:bg-slate-800'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs text-slate-500">{TUR_ETIKETI[u.tur]}</div>
                <h3 className="mt-0.5 font-medium">{u.baslik}</h3>
                <p className="mt-1 whitespace-pre-line text-sm text-slate-600
                              dark:text-slate-400">{u.mesaj}</p>
              </div>
              <span className="shrink-0 text-xs text-slate-400">
                {goreliZaman(u.created_at)}
              </span>
            </div>
            <div className="mt-2 flex gap-3 text-xs">
              {u.watch_id != null && (
                <Link to={`/izleme/${u.watch_id}`} className="text-slate-500 hover:underline">
                  Ürüne git
                </Link>
              )}
              {!u.okundu && (
                <button onClick={() => okundu.mutate(u.id)}
                        className="text-slate-500 hover:underline">
                  Okundu
                </button>
              )}
            </div>
          </div>
        ))}
        {uyarilar?.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center
                        text-sm text-slate-500 dark:border-slate-700">
            Henüz bildirim yok. Fiyat hedefine indiğinde burada göreceksin.
          </p>
        )}
      </div>
    </div>
  )
}

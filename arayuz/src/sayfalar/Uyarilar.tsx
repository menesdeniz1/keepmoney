import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useHepsiOkundu, useUyariOkundu, useUyarilar } from '../api/kancalar'
import type { UyariTuru } from '../api/tipler'
import { goreliZaman } from '../yardimcilar/bicim'
import { GRUP_BASLIGI, uyarilariGrupla } from '../yardimcilar/uyariGruplama'
import { SUZGEC_SECENEKLERI, suzgeciCoz, type UyariSuzgeci } from '../yardimcilar/uyariSuzgecleri'

const TUR_ETIKETI: Record<UyariTuru, string> = {
  HEDEF: '🎯 Hedef',
  YUZDE: '📉 Yüzde düşüş',
  DIP: '📉 Dip',
  SAHTE_INDIRIM: '🎭 Sahte indirim',
  SET_HEDEF: '📦 Set bütçesi',
  KAYNAK_BOZUK: '⚠️ Kaynak',
}

export default function Uyarilar() {
  const [suzgec, setSuzgec] = useState<UyariSuzgeci>('tumu')
  const [searchParams, setSearchParams] = useSearchParams()
  // BACKLOG G2 — "Ürüne göre daraltma": İzleme Detayı'ndan `?watch_id=`
  // ile gelinir. URL'de yaşıyor (bileşen state'inde değil) — sayfa
  // yenilense ya da bağlantı paylaşılsa bile daraltma korunur.
  const watchIdParam = searchParams.get('watch_id')
  const watchId = watchIdParam ? Number(watchIdParam) : null

  const { tur, sadeceOkunmamis } = suzgeciCoz(suzgec)
  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useUyarilar({ sadeceOkunmamis, tur, watchId })
  const okundu = useUyariOkundu()
  const hepsi = useHepsiOkundu()
  const uyarilar = data?.pages.flat()
  const bolumler = uyarilariGrupla(uyarilar ?? [])
  const suzgecAktif = suzgec !== 'tumu' || watchId != null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Bildirimler</h1>
        <button
          onClick={() => hepsi.mutate()}
          disabled={hepsi.isPending || !uyarilar?.some((u) => !u.okundu)}
          className="text-sm text-slate-500 hover:underline
                     disabled:cursor-not-allowed disabled:opacity-40"
        >
          Hepsini okundu işaretle
        </button>
      </div>

      <div role="group" aria-label="Bildirimleri süz" className="flex flex-wrap gap-1.5">
        {SUZGEC_SECENEKLERI.map((s) => (
          <button
            key={s.deger}
            type="button"
            aria-pressed={suzgec === s.deger}
            onClick={() => setSuzgec(s.deger)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              suzgec === s.deger
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
            }`}
          >
            {s.etiket}
          </button>
        ))}
        {watchId != null && (
          <button
            type="button"
            onClick={() => setSearchParams({})}
            className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-3 py-1
                       text-xs font-medium text-indigo-700 hover:bg-indigo-200
                       dark:bg-indigo-950 dark:text-indigo-300 dark:hover:bg-indigo-900"
          >
            yalnızca bu ürünün bildirimleri ✕
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-500">Yükleniyor…</p>}

      <div className="space-y-2">
        {/* BACKLOG G1 — SIRALAMA KORUNUR: `bolumler` yalnızca zaten sıralı
            listeyi bölümlüyor, hiçbir öğeyi taşımıyor (bkz.
            `uyariGruplama.ts`) — sayfalama bu yüzden kırılmaz. */}
        {bolumler.map((bolum) => (
          <div key={bolum.grup}>
            <h2
              className="sticky top-14 z-[5] -mx-1 bg-slate-50/95 px-1 py-1.5
                        text-xs font-semibold uppercase tracking-wide text-slate-500
                        backdrop-blur dark:bg-slate-950/95 dark:text-slate-400"
            >
              {GRUP_BASLIGI[bolum.grup]}
            </h2>
            <div className="space-y-2">
              {bolum.ogeler.map((u) => (
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
            </div>
          </div>
        ))}
        {hasNextPage && (
          <button
            onClick={() => void fetchNextPage()}
            disabled={isFetchingNextPage}
            className="w-full rounded-lg border border-slate-300 py-2 text-sm
                       text-slate-600 hover:bg-slate-50 disabled:opacity-50
                       dark:border-slate-700 dark:text-slate-400
                       dark:hover:bg-slate-900"
          >
            {isFetchingNextPage ? 'Yükleniyor…' : 'Daha eski bildirimler'}
          </button>
        )}
        {uyarilar?.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center
                        text-sm text-slate-500 dark:border-slate-700">
            {suzgecAktif
              ? 'Bu süzgeçte bildirim yok.'
              : 'Henüz bildirim yok. Fiyat hedefine indiğinde burada göreceksin.'}
          </p>
        )}
      </div>
    </div>
  )
}

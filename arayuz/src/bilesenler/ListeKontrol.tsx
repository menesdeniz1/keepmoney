import { LayoutGrid, Table2, X } from 'lucide-react'

import type { KmSet } from '../api/tipler'
import type { GorunumTercihi } from '../yardimcilar/gorunum'
import {
  aktifCipler,
  DURUM_SECENEKLERI,
  SINYAL_SUZGEC_SECENEKLERI,
  SUZGEC_BOS,
  suzgecBosMu,
  type DurumEtiketi,
  type SuzgecDurumu,
} from '../yardimcilar/suzme'
import type { SiralamaSecenegi } from '../yardimcilar/siralama'
import { SIRALAMA_SECENEKLERI } from '../yardimcilar/siralama'

/**
 * Panel liste kontrolü: sıralama (BACKLOG C1) + süzme (BACKLOG C2) +
 * kart/tablo görünüm seçimi (BACKLOG C3) aynı satırda — ilk yazıldığında
 * (C1) bilerek genel "ListeKontrol" adı verilmişti, tam bunun için.
 */
export default function ListeKontrol({
  secili,
  onDegistir,
  suzgec,
  onSuzgecDegistir,
  magazalar,
  setler,
  gorunum,
  onGorunumDegistir,
  gorunumSecimiGorunurMu,
}: {
  secili: SiralamaSecenegi
  onDegistir: (secenek: SiralamaSecenegi) => void
  suzgec: SuzgecDurumu
  onSuzgecDegistir: (suzgec: SuzgecDurumu) => void
  magazalar: string[]
  setler: KmSet[]
  gorunum: GorunumTercihi
  onGorunumDegistir: (secenek: GorunumTercihi) => void
  // BACKLOG C3 kabul ölçütü: "telefonda tablo seçeneği hiç görünmüyor" —
  // düğmenin kendisi DOM'a hiç girmiyor, yalnızca CSS ile gizlenmiyor.
  gorunumSecimiGorunurMu: boolean
}) {
  function setAdi(id: number): string | undefined {
    return setler.find((s) => s.id === id)?.ad
  }

  function durumDegistir(etiket: DurumEtiketi) {
    onSuzgecDegistir({
      ...suzgec,
      durumlar: suzgec.durumlar.includes(etiket)
        ? suzgec.durumlar.filter((d) => d !== etiket)
        : [...suzgec.durumlar, etiket],
    })
  }

  const cipler = aktifCipler(suzgec, setAdi)

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="panel-arama" className="sr-only">
          Ürün ara
        </label>
        <input
          id="panel-arama"
          type="text"
          value={suzgec.arama}
          onChange={(e) => onSuzgecDegistir({ ...suzgec, arama: e.target.value })}
          placeholder="Ürün ara…"
          className="w-36 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm
                     dark:border-slate-700 dark:bg-slate-950"
        />

        <label htmlFor="panel-sinyal-suzgec" className="sr-only">
          Sinyale göre süz
        </label>
        <select
          id="panel-sinyal-suzgec"
          value={suzgec.sinyal}
          onChange={(e) =>
            onSuzgecDegistir({
              ...suzgec,
              sinyal: e.target.value as SuzgecDurumu['sinyal'],
            })
          }
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm
                     dark:border-slate-700 dark:bg-slate-950"
        >
          {SINYAL_SUZGEC_SECENEKLERI.map((s) => (
            <option key={s.deger} value={s.deger}>
              {s.etiket}
            </option>
          ))}
        </select>

        {setler.length > 0 && (
          <>
            <label htmlFor="panel-set-suzgec" className="sr-only">
              Sete göre süz
            </label>
            <select
              id="panel-set-suzgec"
              value={suzgec.setId ?? ''}
              onChange={(e) =>
                onSuzgecDegistir({
                  ...suzgec,
                  setId: e.target.value === '' ? null : Number(e.target.value),
                })
              }
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm
                         dark:border-slate-700 dark:bg-slate-950"
            >
              <option value="">Tüm setler</option>
              {setler.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.ad}
                </option>
              ))}
            </select>
          </>
        )}

        {magazalar.length > 0 && (
          <>
            <label htmlFor="panel-magaza-suzgec" className="sr-only">
              Mağazaya göre süz
            </label>
            <select
              id="panel-magaza-suzgec"
              value={suzgec.magaza ?? ''}
              onChange={(e) =>
                onSuzgecDegistir({
                  ...suzgec,
                  magaza: e.target.value === '' ? null : e.target.value,
                })
              }
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm
                         dark:border-slate-700 dark:bg-slate-950"
            >
              <option value="">Tüm mağazalar</option>
              {magazalar.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </>
        )}

        <div className="flex flex-wrap gap-1" role="group" aria-label="Duruma göre süz">
          {DURUM_SECENEKLERI.map((d) => {
            const secildi = suzgec.durumlar.includes(d.deger)
            return (
              <button
                key={d.deger}
                type="button"
                aria-pressed={secildi}
                onClick={() => durumDegistir(d.deger)}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
                  secildi
                    ? 'border-slate-900 bg-slate-900 text-white dark:border-white dark:bg-white dark:text-slate-900'
                    : 'border-slate-300 text-slate-600 dark:border-slate-700 dark:text-slate-400'
                }`}
              >
                {d.etiket}
              </button>
            )
          })}
        </div>

        <div className="ml-auto flex items-center gap-2">
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

          {gorunumSecimiGorunurMu && (
            <div
              role="group"
              aria-label="Görünüm"
              className="flex overflow-hidden rounded-md border border-slate-300 dark:border-slate-700"
            >
              <button
                type="button"
                aria-pressed={gorunum === 'kart'}
                onClick={() => onGorunumDegistir('kart')}
                title="Kart görünümü"
                className={`p-1.5 ${
                  gorunum === 'kart'
                    ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900'
                    : 'bg-white text-slate-500 dark:bg-slate-950 dark:text-slate-400'
                }`}
              >
                <LayoutGrid size={15} />
                <span className="sr-only">Kart görünümü</span>
              </button>
              <button
                type="button"
                aria-pressed={gorunum === 'tablo'}
                onClick={() => onGorunumDegistir('tablo')}
                title="Tablo görünümü"
                className={`p-1.5 ${
                  gorunum === 'tablo'
                    ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900'
                    : 'bg-white text-slate-500 dark:bg-slate-950 dark:text-slate-400'
                }`}
              >
                <Table2 size={15} />
                <span className="sr-only">Tablo görünümü</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {cipler.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {cipler.map((c) => (
            <button
              key={c.anahtar}
              type="button"
              onClick={() => onSuzgecDegistir(c.kaldir(suzgec))}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5
                         py-1 text-xs text-slate-700 hover:bg-slate-200
                         dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            >
              {c.etiket}
              <X size={12} aria-hidden="true" />
              <span className="sr-only">süzgecini kaldır</span>
            </button>
          ))}
          {!suzgecBosMu(suzgec) && (
            <button
              type="button"
              onClick={() => onSuzgecDegistir(SUZGEC_BOS)}
              className="text-xs text-slate-500 hover:underline dark:text-slate-400"
            >
              Hepsini temizle
            </button>
          )}
        </div>
      )}
    </div>
  )
}

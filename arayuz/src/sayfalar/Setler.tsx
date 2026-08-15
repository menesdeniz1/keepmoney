import { useState } from 'react'
import { Trash2 } from 'lucide-react'

import { useSetOlustur, useSetSil, useSetler } from '../api/kancalar'
import { tl } from '../yardimcilar/bicim'

export default function Setler() {
  const { data: setler } = useSetler()
  const olustur = useSetOlustur()
  const sil = useSetSil()
  const [ad, setAd] = useState('')
  const [butce, setButce] = useState('')

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-xl font-semibold">Setler</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Ürünleri bütçeli koleksiyonlarda topla. Parçalar tek tek hedefte
          olmasa bile <strong>toplam</strong> bütçenin altına inince haber verilir.
        </p>
      </section>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!ad.trim()) return
          olustur.mutate(
            { ad: ad.trim(), butce: butce ? Number(butce) : null },
            { onSuccess: () => { setAd(''); setButce('') } },
          )
        }}
        className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4
                   sm:flex-row dark:border-slate-800 dark:bg-slate-900"
      >
        <input
          value={ad} onChange={(e) => setAd(e.target.value)}
          placeholder="Set adı (örn. PC Toplama)" required maxLength={60}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm
                     dark:border-slate-700 dark:bg-slate-950"
        />
        <input
          type="number" min="1" value={butce}
          onChange={(e) => setButce(e.target.value)} placeholder="Bütçe ₺"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                     sm:w-40 dark:border-slate-700 dark:bg-slate-950"
        />
        <button className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium
                           text-white dark:bg-white dark:text-slate-900">
          Set kur
        </button>
      </form>

      <div className="space-y-3">
        {setler?.map((s) => {
          const oran = s.hedef_butce ? Math.min(100, (s.toplam / s.hedef_butce) * 100) : 0
          return (
            <div key={s.id}
                 className="rounded-lg border border-slate-200 bg-white p-4
                            dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-medium">{s.ad}</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {s.uye_sayisi} ürün
                    {s.eksik_uye > 0 && ` · ${s.eksik_uye} tanesi henüz okunamadı`}
                  </p>
                </div>
                <div className="text-right">
                  <div className="font-mono font-semibold">{tl(s.toplam)}</div>
                  {s.hedef_butce != null && (
                    <div className={`text-xs ${s.hedefte ? 'text-green-600' : 'text-slate-500'}`}>
                      {s.hedefte ? '🎯 bütçe altında' : `bütçe ${tl(s.hedef_butce)}`}
                    </div>
                  )}
                </div>
              </div>

              {s.hedef_butce != null && (
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100
                                dark:bg-slate-800">
                  <div
                    className={`h-full ${s.hedefte ? 'bg-green-500' : 'bg-slate-400'}`}
                    style={{ width: `${oran}%` }}
                  />
                </div>
              )}

              <button
                onClick={() => sil.mutate(s.id)}
                className="mt-3 inline-flex items-center gap-1 text-xs text-red-600
                           hover:underline"
              >
                <Trash2 size={13} /> Seti sil (ürünler silinmez)
              </button>
            </div>
          )
        })}
        {setler?.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center
                        text-sm text-slate-500 dark:border-slate-700">
            Henüz set yok.
          </p>
        )}
      </div>
    </div>
  )
}

import { Link } from 'react-router-dom'

import { useFirsatlar, useKivilcimlar } from '../api/kancalar'
import type { Izleme } from '../api/tipler'
import Kivilcim from '../bilesenler/Kivilcim'
import SinyalRozeti from '../bilesenler/SinyalRozeti'
import { goreliZaman, tl, yuzde } from '../yardimcilar/bicim'

/**
 * BACKLOG D2 — Keepa'nın Deals'ının uyarlanmışı: kullanıcının izlediklerinden
 * şu an iyi fiyatta olanlar, tek sayfada.
 *
 * BACKLOG'UN "SAHTE İNDİRİM ROZETİ" VE "EN SON NE ZAMAN BU KADAR UCUZDU"
 * MADDELERİ BİLEREK YOK — D1'de kullanıcıyla netleştirilen kararın doğal
 * devamı: ikisi de yalnızca `analiz.fiyat_baglami()`nin CANLI hesabında var
 * (`Baglam.sahte_indirim`, `Baglam.en_dusuk_gun`), A1'in stoklanan
 * sütunlarında YOK — buraya eklemek D1'in "ek sorgu yok" ilkesini bozardı.
 * A1'in kendi gerekçesi ("kart bunları göstermiyor, gösteren detay sayfası
 * zaten canlı hesaplıyor") bu satıra da uygulanıyor: satıra tıklayınca
 * zaten detay sayfası ikisini de gösteriyor.
 */
export default function Firsatlar() {
  const { data: firsatlar, isLoading } = useFirsatlar()
  const { data: kivilcimlar } = useKivilcimlar()

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-xl font-semibold">Fırsatlar</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {firsatlar
            ? `${firsatlar.length} ürün şu an iyi fiyatta.`
            : 'Takip ettiğin ürünlerden şu an iyi fiyatta olanlar.'}
        </p>
      </section>

      {isLoading && <p className="text-sm text-slate-500">Yükleniyor…</p>}

      {firsatlar && firsatlar.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 p-8
                        text-center text-sm text-slate-500 dark:border-slate-700">
          Şu an iyi fiyatta ürün yok.
        </div>
      )}

      {firsatlar && firsatlar.length > 0 && (
        <div className="space-y-2">
          {firsatlar.map((f) => (
            <FirsatSatiri key={f.id} izleme={f} kivilcimVerisi={kivilcimlar?.[String(f.id)]} />
          ))}
        </div>
      )}
    </div>
  )
}

function FirsatSatiri({
  izleme,
  kivilcimVerisi,
}: {
  izleme: Izleme
  kivilcimVerisi: number[] | undefined
}) {
  const { urun } = izleme
  const medyanFarki =
    urun.medyan90 != null && urun.guncel_fiyat != null
      ? ((urun.guncel_fiyat - urun.medyan90) / urun.medyan90) * 100
      : null

  return (
    <Link
      to={`/izleme/${izleme.id}`}
      className="flex min-w-0 items-center gap-3 rounded-lg border border-slate-200 bg-white
                 p-3 transition hover:border-slate-300 hover:shadow-sm
                 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
    >
      <div className="min-w-0 flex-1">
        <SinyalRozeti sinyal={urun.sinyal} yuzdelik={urun.yuzdelik} gecmisGun={urun.gecmis_gun} />
        <h2 className="mt-1 truncate text-sm font-medium">{urun.ad}</h2>
        <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
          {urun.guncel_satici ?? 'bilinmiyor'} · {goreliZaman(urun.son_kontrol)}
        </p>
      </div>

      <div className="shrink-0 text-right">
        <div className="font-mono text-base font-semibold">{tl(urun.guncel_fiyat)}</div>
        {medyanFarki !== null && (
          <div
            className={`text-xs ${
              medyanFarki < 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-slate-500 dark:text-slate-400'
            }`}
          >
            medyana göre {yuzde(medyanFarki)}
          </div>
        )}
      </div>

      <div className="shrink-0">
        <Kivilcim veri={kivilcimVerisi} sinyal={urun.sinyal} />
      </div>
    </Link>
  )
}

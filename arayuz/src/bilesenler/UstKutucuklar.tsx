import { Link } from 'react-router-dom'

import type { Izleme } from '../api/tipler'
import { tl } from '../yardimcilar/bicim'
import type { SiralamaSecenegi } from '../yardimcilar/siralama'
import { SUZGEC_BOS, type SuzgecDurumu } from '../yardimcilar/suzme'
import { bugunDegisenSayisi, dipteKacUrun, enBuyukDusus } from '../yardimcilar/ustKutucuklar'

const KUTU_SINIFI =
  'block w-full rounded-lg border border-slate-200 bg-white p-3 text-left ' +
  'transition hover:border-slate-300 hover:shadow-sm dark:border-slate-800 ' +
  'dark:bg-slate-900 dark:hover:border-slate-700'

/**
 * BACKLOG C4 — eski "İzlenen · Hedefte · Liste toplamı" satırının yerine.
 * ESKİ üçlü kaldırıldı ("Liste toplamı" BACKLOG'un kendi gerekçesiyle: kimse
 * hepsini birden almayacak, anlamlı olduğu yer Setler sayfası — "Hedefte"
 * de aynı satırda anlamsızlaşıyordu, neredeyse hep sıfırdı). YENİ üçü,
 * ikisi C2/C1'in MEVCUT mekanizmalarını AÇAN kısayollar (yeni bir ekran
 * durumu icat etmiyor), üçüncüsü doğrudan ürüne gider.
 */
export default function UstKutucuklar({
  izlemeler,
  kivilcimlar,
  kivilcimlar30,
  onSuzgecDegistir,
  onSiralamaDegistir,
}: {
  izlemeler: Izleme[]
  kivilcimlar: Record<string, number[]> | undefined
  kivilcimlar30: Record<string, number[]> | undefined
  onSuzgecDegistir: (suzgec: SuzgecDurumu) => void
  onSiralamaDegistir: (secenek: SiralamaSecenegi) => void
}) {
  const dipSayisi = dipteKacUrun(izlemeler)
  const bugunSayisi = bugunDegisenSayisi(izlemeler, kivilcimlar)
  const dusus = enBuyukDusus(izlemeler, kivilcimlar30)

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <button
        type="button"
        onClick={() => onSuzgecDegistir({ ...SUZGEC_BOS, sinyal: 'dip' })}
        className={KUTU_SINIFI}
      >
        <div className="text-xs text-slate-500 dark:text-slate-400">Dip bölgesinde</div>
        <div className="mt-0.5 font-mono text-lg font-semibold">
          {dipSayisi > 0 ? `${dipSayisi} ürün` : 'şu an yok'}
        </div>
      </button>

      <button
        type="button"
        onClick={() => onSiralamaDegistir('son_degisim')}
        className={KUTU_SINIFI}
      >
        <div className="text-xs text-slate-500 dark:text-slate-400">Bugün değişen</div>
        <div className="mt-0.5 font-mono text-lg font-semibold">
          {bugunSayisi > 0 ? `${bugunSayisi} fiyat` : 'henüz yok'}
        </div>
      </button>

      {/* Diğer iki kutucuğun aksine burada VERİ YOKKEN gidilecek bir ürün
          de yok — "tıklanabilir" olmak için sahte bir hedef uydurmak
          yerine (BACKLOG'un "veri yokken anlamlı bir şey söylüyor" ölçütü)
          bu durumda düğüm yerine düz metin gösteriyoruz. */}
      {dusus ? (
        <Link to={`/izleme/${dusus.izlemeId}`} className={KUTU_SINIFI}>
          <div className="text-xs text-slate-500 dark:text-slate-400">
            Son 30 günde en büyük düşüş
          </div>
          <div className="mt-0.5 truncate text-sm font-medium">{dusus.ad}</div>
          <div className="font-mono text-lg font-semibold text-green-600 dark:text-green-400">
            −{tl(dusus.tutar)}
          </div>
        </Link>
      ) : (
        <div className={`${KUTU_SINIFI} cursor-default hover:border-slate-200 hover:shadow-none dark:hover:border-slate-800`}>
          <div className="text-xs text-slate-500 dark:text-slate-400">
            Son 30 günde en büyük düşüş
          </div>
          <div className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
            son 30 günde düşüş yok
          </div>
        </div>
      )}
    </div>
  )
}

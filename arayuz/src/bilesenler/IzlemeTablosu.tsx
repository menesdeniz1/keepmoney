import { Link } from 'react-router-dom'

import type { Izleme } from '../api/tipler'
import { goreliZaman, hedefeKalan, kisaTl, tl, yuzde } from '../yardimcilar/bicim'
import type { SiralamaSecenegi } from '../yardimcilar/siralama'
import Kivilcim from './Kivilcim'
import SinyalRozeti from './SinyalRozeti'

/** `IzlemeKarti.tsx`'teki AYNI renk kuralı: düşüş her zaman iyi haber. */
function farkRengi(y: number): string {
  return y < 0
    ? 'text-green-600 dark:text-green-400'
    : 'text-slate-500 dark:text-slate-400'
}

/**
 * BACKLOG C3 — sütun başlığına tıklayınca o sütuna göre sıralanır, "C1 ile
 * AYNI durum": ayrı bir tablo-sıralaması icat edilmedi, üstteki "Sırala:"
 * açılır kutusuyla (ListeKontrol.tsx) AYNI `SiralamaSecenegi` state'i
 * paylaşılıyor. Fiyat sütunu tıklandıkça yön DEĞİŞTİRİR (zaten hem artan
 * hem azalan seçeneği C1'de tanımlıydı); diğerlerinin C1'de tanımlı TEK
 * doğal yönü var.
 */
const KOLONLAR: {
  anahtar: string
  baslik: string
  siralama: SiralamaSecenegi
  hizala?: 'sag'
}[] = [
  { anahtar: 'sinyal', baslik: 'Sinyal', siralama: 'firsat' },
  { anahtar: 'ad', baslik: 'Ürün', siralama: 'ad' },
  { anahtar: 'kivilcim', baslik: 'Eğilim', siralama: 'son_degisim' },
  { anahtar: 'fiyat', baslik: 'Fiyat', siralama: 'fiyat_artan', hizala: 'sag' },
  { anahtar: 'medyan_fark', baslik: 'Medyana fark', siralama: 'medyan_fark', hizala: 'sag' },
  { anahtar: 'hedef', baslik: 'Hedef', siralama: 'hedef_yakinlik', hizala: 'sag' },
  { anahtar: 'son_kontrol', baslik: 'Son kontrol', siralama: 'son_kontrol', hizala: 'sag' },
]

export default function IzlemeTablosu({
  izlemeler,
  kivilcimlar,
  siralama,
  onSiralaDegistir,
}: {
  izlemeler: Izleme[]
  kivilcimlar: Record<string, number[]> | undefined
  siralama: SiralamaSecenegi
  onSiralaDegistir: (secenek: SiralamaSecenegi) => void
}) {
  function basligaTiklandi(kolonSiralama: SiralamaSecenegi) {
    if (kolonSiralama === 'fiyat_artan') {
      onSiralaDegistir(siralama === 'fiyat_artan' ? 'fiyat_azalan' : 'fiyat_artan')
      return
    }
    onSiralaDegistir(kolonSiralama)
  }

  function ariaSort(kolonSiralama: SiralamaSecenegi): 'ascending' | 'descending' | 'none' {
    if (kolonSiralama === 'fiyat_artan') {
      if (siralama === 'fiyat_artan') return 'ascending'
      if (siralama === 'fiyat_azalan') return 'descending'
      return 'none'
    }
    return siralama === kolonSiralama ? 'ascending' : 'none'
  }

  return (
    // BACKLOG C3 kabul ölçütü: "yatay kaydırma kendi kabında, sayfa gövdesi
    // kaymıyor" — `overflow-x-auto` BU kutuda; sayfanın kendisi hiçbir
    // zaman tablo genişliğine göre büyümez (bkz. Duzen.tsx'in D2'de
    // eklediği `min-w-0`, aynı ilke).
    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs text-slate-500
                         dark:border-slate-800 dark:text-slate-400">
            {KOLONLAR.map((k) => (
              <th
                key={k.anahtar}
                aria-sort={ariaSort(k.siralama)}
                className={`px-3 py-2 font-medium ${k.hizala === 'sag' ? 'text-right' : ''}`}
              >
                <button
                  type="button"
                  onClick={() => basligaTiklandi(k.siralama)}
                  className="hover:text-slate-900 dark:hover:text-slate-200"
                >
                  {k.baslik}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {izlemeler.map((izleme) => {
            const { urun } = izleme
            const durum = hedefeKalan(urun.guncel_fiyat, izleme.hedef_fiyat)
            const medyanFarki =
              urun.medyan90 != null && urun.guncel_fiyat != null
                ? ((urun.guncel_fiyat - urun.medyan90) / urun.medyan90) * 100
                : null
            const kivilcimVerisi = kivilcimlar?.[String(izleme.id)]
            return (
              <tr key={izleme.id} className="hover:bg-slate-50 dark:hover:bg-slate-900">
                <td className="px-3 py-2">
                  <SinyalRozeti
                    sinyal={urun.sinyal}
                    yuzdelik={urun.yuzdelik}
                    gecmisGun={urun.gecmis_gun}
                  />
                </td>
                <td className="max-w-[220px] truncate px-3 py-2">
                  <Link to={`/izleme/${izleme.id}`} className="font-medium hover:underline">
                    {urun.ad}
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <Kivilcim veri={kivilcimVerisi} sinyal={urun.sinyal} />
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">
                  {tl(urun.guncel_fiyat)}
                </td>
                <td
                  className={`px-3 py-2 text-right tabular-nums ${
                    medyanFarki != null ? farkRengi(medyanFarki) : ''
                  }`}
                >
                  {medyanFarki != null ? yuzde(medyanFarki) : '—'}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {durum ? (durum.hedefte ? '🎯 hedefte' : kisaTl(durum.fark)) : '—'}
                </td>
                <td className="px-3 py-2 text-right text-xs text-slate-500 dark:text-slate-400">
                  {goreliZaman(urun.son_kontrol)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

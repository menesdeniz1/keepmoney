import { ExternalLink, Search } from 'lucide-react'

import { useKaynakOnerileri } from '../api/kancalar'
import type { Kaynak } from '../api/tipler'
import { goreliZaman, tl } from '../yardimcilar/bicim'
import { DURUM_METNI, enUcuzKaynak } from '../yardimcilar/kaynakDurumu'

const DURUM_STIL: Record<Kaynak['durum'], string> = {
  OK: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  ENGELLI: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  OLU: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  HATA: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  BEKLEMEDE: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  STOKTA_YOK: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
}

/**
 * BACKLOG F3 — "Detayda kaynaklar sadece host adı olarak listeleniyor. Üç
 * mağazada izlenen ürünün kararı burada verilir." Kolonlar: mağaza · güncel
 * fiyat · son okuma · durum · en ucuz işareti · git.
 *
 * `izlemeId` yalnızca ENGELLİ satırdaki "akakçe kaynağı ara" düğmesi için
 * gerekiyor: `useKaynakOnerileri` aynı `['kaynak-onerileri', izlemeId]`
 * sorgu anahtarını `KaynakOnerileri.tsx`in kendi örneğiyle PAYLAŞIR (React
 * Query anahtar bazlı önbellekliyor) — burada `refetch()` çağırmak, aşağıdaki
 * "Başka mağazalarda ara" sonucunu da tetikler, ikinci bir arama akışı
 * kurmaya gerek kalmaz.
 */
export default function KaynakTablosu({
  kaynaklar, izlemeId,
}: {
  kaynaklar: Kaynak[]
  izlemeId: number
}) {
  const oneriler = useKaynakOnerileri(izlemeId)
  const enUcuzId = enUcuzKaynak(kaynaklar)

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-left text-sm">
        <thead>
          <tr className="text-xs text-slate-500 dark:text-slate-400">
            <th className="pb-2 pr-2 font-medium">Mağaza</th>
            <th className="pb-2 pr-2 font-medium">Fiyat</th>
            <th className="pb-2 pr-2 font-medium">Son okuma</th>
            <th className="pb-2 pr-2 font-medium">Durum</th>
            <th className="pb-2 pr-2 font-medium" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {kaynaklar.map((k) => (
            <tr key={k.id}>
              <td className="max-w-[160px] truncate py-2 pr-2">
                {k.satici ?? k.host}
                {k.ortaklik && (
                  <span
                    title="Bu bağlantıdan alışveriş yaparsan küçük bir komisyon alırız. Fiyatın değişmez ve hangi mağazanın en ucuz seçildiğini etkilemez."
                    className="ml-1 rounded bg-slate-100 px-1.5 text-[10px]
                               font-medium text-slate-600 dark:bg-slate-800
                               dark:text-slate-400"
                  >
                    ortaklık
                  </span>
                )}
              </td>
              <td className="py-2 pr-2 font-mono">
                {tl(k.son_fiyat)}
                {k.id === enUcuzId && (
                  <span className="ml-1.5 rounded bg-green-100 px-1.5 py-0.5 text-[10px]
                                   font-medium text-green-800 dark:bg-green-950
                                   dark:text-green-300">
                    en ucuz
                  </span>
                )}
              </td>
              <td className="py-2 pr-2 text-xs text-slate-500 dark:text-slate-400">
                {goreliZaman(k.son_kontrol)}
              </td>
              <td className="py-2 pr-2">
                <span
                  className={`inline-flex items-center rounded px-1.5 py-0.5
                             text-xs font-medium ${DURUM_STIL[k.durum]}`}
                >
                  {DURUM_METNI[k.durum]}
                </span>
                {k.durum === 'ENGELLI' && (
                  <button
                    onClick={() => void oneriler.refetch()}
                    disabled={oneriler.isFetching}
                    className="ml-1.5 inline-flex items-center gap-1 text-xs
                               text-slate-500 hover:underline disabled:opacity-50
                               dark:text-slate-400"
                  >
                    <Search size={11} />
                    {oneriler.isFetching ? 'aranıyor…' : 'akakçe kaynağı ara'}
                  </button>
                )}
              </td>
              <td className="py-2 text-right">
                <a
                  href={k.cikis_url || k.url}
                  target="_blank"
                  rel="noopener noreferrer nofollow sponsored"
                  aria-label={`${k.satici ?? k.host} sayfasına git`}
                  className="inline-flex items-center text-slate-400 hover:text-slate-700
                             dark:hover:text-slate-200"
                >
                  <ExternalLink size={14} />
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

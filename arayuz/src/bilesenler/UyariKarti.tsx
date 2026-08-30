import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BellOff, ExternalLink, Trash2 } from 'lucide-react'

import { useIzlemeGuncelle, useIzlemeSil, useUyariOkundu } from '../api/kancalar'
import type { Uyari, UyariTuru } from '../api/tipler'
import { goreliZaman } from '../yardimcilar/bicim'
import Onay from './Onay'

const TUR_ETIKETI: Record<UyariTuru, string> = {
  HEDEF: '🎯 Hedef',
  YUZDE: '📉 Yüzde düşüş',
  DIP: '📉 Dip',
  SAHTE_INDIRIM: '🎭 Sahte indirim',
  SET_HEDEF: '📦 Set bütçesi',
  KAYNAK_BOZUK: '⚠️ Kaynak',
}

const SUSTUR_GUN = 7

/**
 * BACKLOG G3 — "Uyarı geldi, kullanıcı ne yapacak? Şu an tek yol ürüne
 * gidip elle ayar değiştirmek." Her satıra üç kısayol eklendi: doğrudan
 * mağazaya git, 7 gün sustur, takipten çıkar (yıkıcı olduğu için onaylı).
 *
 * Kendi mutasyonlarını kendi yönetiyor (satır başına, `Uyarilar.tsx`
 * seviyesinde DEĞİL): her satırın `watch_id`si farklı ve React Hook'ları
 * bir döngü içinde koşullu çağrılamaz — bu yüzden ayrı bileşen.
 */
export default function UyariKarti({ u }: { u: Uyari }) {
  const [silOnay, setSilOnay] = useState(false)
  const okundu = useUyariOkundu()
  // `watch_id` `null` olduğunda (izleme zaten silinmiş) düğmeler zaten
  // gizli — kanca yine de KOŞULSUZ çağrılmalı, `-1` yalnızca tip için
  // zararsız bir yer tutucu, `.mutate()` hiç tetiklenmez.
  const guncelle = useIzlemeGuncelle(u.watch_id ?? -1)
  const sil = useIzlemeSil()

  return (
    <div
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
      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
        {u.watch_id != null && (
          <Link to={`/izleme/${u.watch_id}`} className="text-slate-500 hover:underline">
            Ürüne git
          </Link>
        )}
        {u.magaza_url && (
          <a
            href={u.magaza_url}
            target="_blank"
            rel="noopener noreferrer nofollow sponsored"
            className="inline-flex items-center gap-1 text-slate-500 hover:underline"
          >
            Mağazaya git <ExternalLink size={11} />
          </a>
        )}
        {u.watch_id != null && (
          <button
            type="button"
            onClick={() => guncelle.mutate({ sustur_gun: SUSTUR_GUN })}
            disabled={guncelle.isPending || guncelle.isSuccess}
            className="inline-flex items-center gap-1 text-slate-500 hover:underline
                       disabled:cursor-not-allowed disabled:opacity-60"
          >
            <BellOff size={11} />
            {guncelle.isSuccess ? 'Susturuldu' : `${SUSTUR_GUN} gün sustur`}
          </button>
        )}
        {!u.okundu && (
          <button onClick={() => okundu.mutate(u.id)}
                  className="text-slate-500 hover:underline">
            Okundu
          </button>
        )}
        {u.watch_id != null && (
          <button
            type="button"
            onClick={() => setSilOnay(true)}
            className="inline-flex items-center gap-1 text-red-600 hover:underline"
          >
            <Trash2 size={11} /> Takipten çıkar
          </button>
        )}
      </div>

      <Onay
        acik={silOnay}
        baslik="Takipten çıkarılsın mı?"
        aciklama="Bu ürün listenden kaldırılacak. Fiyat geçmişi sistemde kalır; yeniden eklersen geçmişi yine görürsün."
        onayMetni="Takipten çıkar"
        bekliyor={sil.isPending}
        onIptal={() => setSilOnay(false)}
        onOnay={() => {
          if (u.watch_id == null) return
          sil.mutate(u.watch_id, {
            onSuccess: () => setSilOnay(false),
            onError: () => setSilOnay(false),
          })
        }}
      />
    </div>
  )
}

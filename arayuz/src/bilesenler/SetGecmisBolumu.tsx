/**
 * `SetGecmisGrafigi`nin veri-çekme kabuğu. AYRI dosya: grafiğin kendisi
 * saf props alıp çiziyor (testte sahte veri vermek yeterli), sorgu — ve
 * yükleniyor/boş durumları — burada. Yalnızca açıldığında monte edilir
 * (bkz. `Setler.tsx`) — kapalı set kartları için gereksiz istek atılmaz.
 */
import { useSetGecmis } from '../api/kancalar'
import SetGecmisGrafigi from './SetGecmisGrafigi'

export default function SetGecmisBolumu({
  setId, hedefButce,
}: {
  setId: number
  hedefButce: number | null
}) {
  const { data: gecmis, isLoading } = useSetGecmis(setId)

  if (isLoading) {
    return <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Yükleniyor…</p>
  }
  if (!gecmis || gecmis.length === 0) {
    return (
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Henüz geçmiş yok — üyelerin fiyatı birikince burada görünür.
      </p>
    )
  }

  return (
    <div className="mt-3">
      <SetGecmisGrafigi gecmis={gecmis} hedefButce={hedefButce} yukseklik={200} />
    </div>
  )
}

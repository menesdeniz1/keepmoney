import { useState } from 'react'
import { Plus } from 'lucide-react'

import { useIzlemeEkle, useIzlemeler } from '../api/kancalar'
import IzlemeKarti from '../bilesenler/IzlemeKarti'
import { tl } from '../yardimcilar/bicim'

export default function Panel() {
  const { data: izlemeler, isLoading } = useIzlemeler()
  const ekle = useIzlemeEkle()
  const [url, setUrl] = useState('')
  const [hedef, setHedef] = useState('')

  function gonder(e: React.FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    ekle.mutate(
      {
        url: url.trim(),
        hedef_fiyat: hedef ? Number(hedef) : null,
      },
      {
        onSuccess: () => {
          setUrl('')
          setHedef('')
        },
      },
    )
  }

  const hedefteOlanlar =
    izlemeler?.filter(
      (i) =>
        i.hedef_fiyat != null &&
        i.urun.guncel_fiyat != null &&
        i.urun.guncel_fiyat <= i.hedef_fiyat,
    ) ?? []

  const toplam =
    izlemeler?.reduce((t, i) => t + (i.urun.guncel_fiyat ?? 0), 0) ?? 0

  // BACKLOG A7: kartların her biri kendi "geçmiş biriktiriliyor" rozetini
  // gösteriyor (SinyalRozeti) ama 20 karttan 15'i sinyalsizse bunu tek tek
  // fark etmek zor. Toplu satır, "sistem bozuk mu" sorusunu daha kartlara
  // bakmadan cevaplıyor — gerçek çalıştırmada (DEVIR §4.1) tam bu oldu:
  // worker günlerce açık kalmadan HİÇBİR üründe sinyal çıkmadı.
  const sinyalsizler = izlemeler?.filter((i) => i.urun.sinyal === null) ?? []
  // Sabit bir eşik ("N gün içinde") YAZILMIYOR — SinyalRozeti.tsx'teki
  // gerekçenin aynısı: backend eşiği hiçbir API alanında dışa açılmıyor.
  // Bunun yerine EN İLERİDEKİ ürünün gerçek gün sayısı gösteriliyor —
  // ilerlemenin somut, ölçülmüş kanıtı.
  const enIlerideki = Math.max(
    0, ...sinyalsizler.map((i) => i.urun.gecmis_gun ?? 0))

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-xl font-semibold">Takip listem</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Herhangi bir mağazanın ürün linkini yapıştır — fiyat hafızası
          birikmeye başlasın.
        </p>
      </section>

      <form
        onSubmit={gonder}
        className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4
                   sm:flex-row dark:border-slate-800 dark:bg-slate-900"
      >
        <input
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.magaza.com/urun/..."
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm
                     dark:border-slate-700 dark:bg-slate-950"
        />
        <input
          type="number"
          min="1"
          value={hedef}
          onChange={(e) => setHedef(e.target.value)}
          placeholder="Hedef ₺ (isteğe bağlı)"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                     sm:w-48 dark:border-slate-700 dark:bg-slate-950"
        />
        <button
          type="submit"
          disabled={ekle.isPending}
          className="inline-flex items-center justify-center gap-1.5 rounded-md
                     bg-slate-900 px-4 py-2 text-sm font-medium text-white
                     disabled:opacity-50 dark:bg-white dark:text-slate-900"
        >
          <Plus size={16} />
          {ekle.isPending ? 'Ekleniyor…' : 'Takibe al'}
        </button>
      </form>

      {ekle.isError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700
                      dark:bg-red-950/50 dark:text-red-300">
          {ekle.error.message}
        </p>
      )}

      {izlemeler && izlemeler.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Kutu etiket="İzlenen ürün" deger={String(izlemeler.length)} />
          <Kutu etiket="Hedefte" deger={String(hedefteOlanlar.length)} vurgu />
          <Kutu etiket="Liste toplamı" deger={tl(toplam)} />
        </div>
      )}

      {sinyalsizler.length > 0 && (
        <p className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500
                      dark:bg-slate-900 dark:text-slate-400">
          {sinyalsizler.length} ürün için geçmiş biriktiriliyor
          {enIlerideki > 0 && <> (en ileride {enIlerideki} gün)</>} — worker
          çalıştıkça sinyaller kendiliğinden görünür.
        </p>
      )}

      {isLoading && <p className="text-sm text-slate-500">Yükleniyor…</p>}

      {izlemeler?.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 p-8
                        text-center text-sm text-slate-500 dark:border-slate-700">
          Henüz ürün eklemedin. Yukarıya bir link yapıştırarak başla.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {izlemeler?.map((i) => (
          <IzlemeKarti key={i.id} izleme={i} />
        ))}
      </div>
    </div>
  )
}

function Kutu({
  etiket,
  deger,
  vurgu,
}: {
  etiket: string
  deger: string
  vurgu?: boolean
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3
                    dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs text-slate-500 dark:text-slate-400">{etiket}</div>
      <div
        className={`mt-0.5 font-mono text-lg font-semibold ${
          vurgu ? 'text-green-600 dark:text-green-400' : ''
        }`}
      >
        {deger}
      </div>
    </div>
  )
}

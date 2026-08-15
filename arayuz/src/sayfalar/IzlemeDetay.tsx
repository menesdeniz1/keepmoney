import { Suspense, lazy, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Trash2 } from 'lucide-react'

import { useIzleme, useIzlemeGuncelle, useIzlemeSil } from '../api/kancalar'
// Recharts ~400 KB. Panel ve diğer sayfalar bunu indirmesin diye
// yalnızca bu sayfa açıldığında yüklenir (kod bölme).
const FiyatGrafigi = lazy(() => import('../bilesenler/FiyatGrafigi'))
import YorumKarti from '../bilesenler/YorumKarti'
import { goreliZaman, tl } from '../yardimcilar/bicim'

export default function IzlemeDetay() {
  const { id } = useParams()
  const izlemeId = Number(id)
  const { data: izleme, isLoading } = useIzleme(izlemeId)
  const guncelle = useIzlemeGuncelle(izlemeId)
  const sil = useIzlemeSil()
  const navigate = useNavigate()
  const [yeniHedef, setYeniHedef] = useState('')

  if (isLoading) return <p className="text-sm text-slate-500">Yükleniyor…</p>
  if (!izleme) return <p className="text-sm text-slate-500">İzleme bulunamadı.</p>

  const { urun } = izleme

  return (
    <div className="space-y-5">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:underline"
      >
        <ArrowLeft size={15} /> Panele dön
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">{urun.ad}</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {urun.guncel_satici ?? 'bilinmiyor'} ·{' '}
            {goreliZaman(urun.son_kontrol)}
            {urun.puan != null && (
              <> · ⭐ {urun.puan.toFixed(1)} ({urun.yorum_sayisi ?? 0} yorum)</>
            )}
          </p>
        </div>
        <div className="text-right">
          <div className="font-mono text-2xl font-bold">{tl(urun.guncel_fiyat)}</div>
          {izleme.hedef_fiyat != null && (
            <div className="text-xs text-slate-500">
              hedefin: {tl(izleme.hedef_fiyat)}
            </div>
          )}
        </div>
      </header>

      <YorumKarti baglam={urun.baglam} />

      <section className="rounded-lg border border-slate-200 bg-white p-4
                          dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-sm font-medium text-slate-600 dark:text-slate-400">
          Fiyat geçmişi
        </h2>
        <Suspense
          fallback={
            <div className="h-[280px] animate-pulse rounded-lg bg-slate-100
                            dark:bg-slate-800" />
          }
        >
          <FiyatGrafigi
            gecmis={urun.gecmis}
            hedefFiyat={izleme.hedef_fiyat}
            baglam={urun.baglam}
          />
        </Suspense>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4
                        dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-3 text-sm font-medium">Hedef fiyat</h2>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (!yeniHedef) return
              guncelle.mutate({ hedef_fiyat: Number(yeniHedef) })
              setYeniHedef('')
            }}
          >
            <input
              type="number"
              min="1"
              value={yeniHedef}
              onChange={(e) => setYeniHedef(e.target.value)}
              placeholder={izleme.hedef_fiyat ? String(izleme.hedef_fiyat) : 'örn. 45000'}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm
                         dark:border-slate-700 dark:bg-slate-950"
            />
            <button className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white
                               dark:bg-white dark:text-slate-900">
              Kaydet
            </button>
          </form>
          <p className="mt-2 text-xs text-slate-500">
            Hedefi değiştirmek susturmayı kaldırır — yeni hedeften bildirim
            gelmeye başlar.
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4
                        dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-3 text-sm font-medium">Bildirimler</h2>
          <div className="flex flex-wrap gap-2">
            {[7, 30].map((gun) => (
              <button
                key={gun}
                onClick={() => guncelle.mutate({ sustur_gun: gun })}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm
                           dark:border-slate-700"
              >
                {gun} gün sustur
              </button>
            ))}
            <button
              onClick={() => guncelle.mutate({ sustur_gun: 0 })}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm
                         dark:border-slate-700"
            >
              Susturmayı kaldır
            </button>
            <button
              onClick={() => guncelle.mutate({ aktif: !izleme.aktif })}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm
                         dark:border-slate-700"
            >
              {izleme.aktif ? 'Duraklat' : 'Devam ettir'}
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4
                          dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-sm font-medium">
          Kaynaklar ({urun.kaynaklar.length})
        </h2>
        <ul className="space-y-2 text-sm">
          {urun.kaynaklar.map((k) => (
            <li key={k.id} className="flex items-center justify-between gap-3">
              <a
                href={k.cikis_url || k.url}
                target="_blank"
                rel="noopener noreferrer nofollow sponsored"
                className="inline-flex min-w-0 items-center gap-1 truncate hover:underline"
              >
                <span className="truncate">{k.satici ?? k.host}</span>
                <ExternalLink size={13} className="shrink-0" />
                {k.ortaklik && (
                  <span
                    title="Bu bağlantıdan alışveriş yaparsan küçük bir komisyon alırız. Fiyatın değişmez ve hangi mağazanın en ucuz seçildiğini etkilemez."
                    className="shrink-0 rounded bg-slate-100 px-1.5 text-[10px]
                               font-medium text-slate-600 dark:bg-slate-800
                               dark:text-slate-400"
                  >
                    ortaklık
                  </span>
                )}
              </a>
              <span className="shrink-0 font-mono">{tl(k.son_fiyat)}</span>
            </li>
          ))}
        </ul>
        {urun.kaynaklar.some((k) => k.ortaklik) && (
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            "ortaklık" işaretli bağlantılardan alışveriş yaparsan küçük bir
            komisyon alırız. <strong>Ödediğin fiyat değişmez</strong> ve bu,
            hangi mağazanın en ucuz seçildiğini etkilemez — sıralama yalnızca
            fiyata göredir.
          </p>
        )}
      </section>

      <button
        onClick={() => {
          sil.mutate(izlemeId, { onSuccess: () => navigate('/') })
        }}
        className="inline-flex items-center gap-1.5 text-sm text-red-600 hover:underline"
      >
        <Trash2 size={15} /> Takipten çıkar
      </button>
    </div>
  )
}

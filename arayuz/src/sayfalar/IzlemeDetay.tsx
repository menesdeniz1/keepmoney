import { Suspense, lazy, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Trash2 } from 'lucide-react'

import { useIzleme, useIzlemeGuncelle, useIzlemeSil, useSetler } from '../api/kancalar'
import KaynakOnerileri from '../bilesenler/KaynakOnerileri'
import Onay from '../bilesenler/Onay'
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
  const { data: setler } = useSetler()
  const [yeniHedef, setYeniHedef] = useState('')
  const [silOnay, setSilOnay] = useState(false)

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
            <label htmlFor="hedef-fiyat" className="sr-only">
              Hedef fiyat
            </label>
            <input
              id="hedef-fiyat"
              type="number"
              min="1"
              value={yeniHedef}
              onChange={(e) => setYeniHedef(e.target.value)}
              placeholder={izleme.hedef_fiyat ? String(izleme.hedef_fiyat) : 'örn. 45000'}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm
                         dark:border-slate-700 dark:bg-slate-950"
            />
            {/* Bekleme sırasında kilitli: çift tıklama iki PATCH göndermesin. */}
            <button
              disabled={guncelle.isPending}
              className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white
                         disabled:opacity-50 dark:bg-white dark:text-slate-900"
            >
              {guncelle.isPending ? '…' : 'Kaydet'}
            </button>
          </form>
          <p className="mt-2 text-xs text-slate-500">
            Hedefi değiştirmek susturmayı kaldırır — yeni hedeften bildirim
            gelmeye başlar.
          </p>
          {izleme.hedef_fiyat != null && (
            <button
              onClick={() => guncelle.mutate({ hedef_fiyat: null })}
              disabled={guncelle.isPending}
              className="mt-2 text-xs text-slate-500 hover:underline disabled:opacity-50"
            >
              Hedefi kaldır
            </button>
          )}
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

      {/* SET ATAMA. Bu kontrol YOKTU: set kurulabiliyor ama içine ürün
          konulamıyordu — yani ürünün en ayırt edici özelliği (toplam bütçe
          takibi) arayüzden hiç erişilemiyordu. */}
      <section className="rounded-lg border border-slate-200 bg-white p-4
                          dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-2 text-sm font-medium">Set</h2>
        {setler && setler.length > 0 ? (
          <>
            <label htmlFor="set-secimi" className="sr-only">
              Bu ürünün ait olduğu set
            </label>
            <select
              id="set-secimi"
              value={izleme.set_id ?? ''}
              disabled={guncelle.isPending}
              onChange={(e) =>
                guncelle.mutate({
                  set_id: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                         disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950"
            >
              <option value="">Sete dahil değil</option>
              {setler.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.ad}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-slate-500">
              Sete eklenen ürünler toplam bütçe hedefine dahil olur.
            </p>
          </>
        ) : (
          <p className="text-sm text-slate-500">
            Henüz set yok.{' '}
            <Link to="/setler" className="underline">
              Set kur
            </Link>{' '}
            — sonra bu ürünü ekleyebilirsin.
          </p>
        )}
      </section>

      {guncelle.isError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700
                      dark:bg-red-950/50 dark:text-red-300">
          {guncelle.error.message}
        </p>
      )}

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

        {/*
          Pazar derinliği. "Kaç mağaza satıyor ve ikincisi kaça" bilgisi,
          kullanıcının fiyata güvenip güvenmeyeceğini belirleyen tek bağlam
          olabiliyor — özellikle yeni eklenmiş, fiyat geçmişi henüz oluşmamış
          üründe. Koruma katmanı aynı sinyali kullanıyor (karar.pazar_aykiri);
          burada gösterilmesi kullanıcının kararı DENETLEYEBİLMESİ için.
        */}
        {urun.kaynaklar
          .filter((k) => k.satici_sayisi != null)
          .map((k) => (
            <p
              key={`pazar-${k.id}`}
              className="mt-3 text-xs text-slate-500 dark:text-slate-400"
            >
              🏪 {k.satici_sayisi} satıcı
              {k.ikinci_fiyat != null && <> · 2. en ucuz: {tl(k.ikinci_fiyat)}</>}
              {k.ikinci_fiyat != null &&
                k.son_fiyat != null &&
                k.ikinci_fiyat > k.son_fiyat * 1.5 && (
                  <span className="ml-1 font-medium text-amber-600 dark:text-amber-500">
                    ⚠️ tek satıcı belirgin ucuz — mağazayı teyit et
                  </span>
                )}
              {k.satici_sayisi === 1 && (
                <span className="ml-1">· kıyaslanacak ikinci fiyat yok</span>
              )}
            </p>
          ))}

        <KaynakOnerileri izlemeId={izleme.id} />

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
        onClick={() => setSilOnay(true)}
        className="inline-flex items-center gap-1.5 text-sm text-red-600 hover:underline"
      >
        <Trash2 size={15} /> Takipten çıkar
      </button>

      <Onay
        acik={silOnay}
        baslik="Takipten çıkarılsın mı?"
        aciklama={`"${urun.ad}" listenden kaldırılacak. Ürünün fiyat geçmişi
                   sistemde kalır; yeniden eklersen geçmişi yine görürsün.`}
        onayMetni="Takipten çıkar"
        bekliyor={sil.isPending}
        onIptal={() => setSilOnay(false)}
        onOnay={() =>
          sil.mutate(izlemeId, {
            onSuccess: () => navigate('/'),
            onError: () => setSilOnay(false),
          })
        }
      />

      {sil.isError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700
                      dark:bg-red-950/50 dark:text-red-300">
          {sil.error.message}
        </p>
      )}
    </div>
  )
}

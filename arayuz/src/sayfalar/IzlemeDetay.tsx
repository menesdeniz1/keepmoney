import { Suspense, lazy, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Trash2 } from 'lucide-react'

import { csvAdresleri } from '../api/istemci'
import { useIzleme, useIzlemeGuncelle, useIzlemeSil, useSetler } from '../api/kancalar'
import CsvIndir from '../bilesenler/CsvIndir'
import KaynakOnerileri from '../bilesenler/KaynakOnerileri'
import KaynakTablosu from '../bilesenler/KaynakTablosu'
import Onay from '../bilesenler/Onay'
// Recharts ~400 KB. Panel ve diğer sayfalar bunu indirmesin diye
// yalnızca bu sayfa açıldığında yüklenir (kod bölme).
const FiyatGrafigi = lazy(() => import('../bilesenler/FiyatGrafigi'))
import UyariKurulumu from '../bilesenler/UyariKurulumu'
import YorumKarti from '../bilesenler/YorumKarti'
import { goreliZaman, tl } from '../yardimcilar/bicim'
import { yenidenKurmaDurumu, yenidenKurmaMetni } from '../yardimcilar/yenidenKurma'

export default function IzlemeDetay() {
  const { id } = useParams()
  const izlemeId = Number(id)
  const { data: izleme, isLoading } = useIzleme(izlemeId)
  const guncelle = useIzlemeGuncelle(izlemeId)
  const sil = useIzlemeSil()
  const navigate = useNavigate()
  const { data: setler } = useSetler()
  const [silOnay, setSilOnay] = useState(false)

  if (isLoading) return <p className="text-sm text-slate-500">Yükleniyor…</p>
  if (!izleme) return <p className="text-sm text-slate-500">İzleme bulunamadı.</p>

  const { urun } = izleme
  const rearmMetni = yenidenKurmaMetni(yenidenKurmaDurumu(izleme))

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

      <YorumKarti baglam={urun.baglam} gecmisGun={urun.gecmis_gun} />

      <section className="rounded-lg border border-slate-200 bg-white p-4
                          dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-medium text-slate-600 dark:text-slate-400">
            Fiyat geçmişi
          </h2>
          {/* BACKLOG H1 — grafiğin YANINDA duruyor çünkü indirilen şey tam
              olarak grafiğin verisi (daha da fazlası: gün özeti değil ham
              okumalar). Sayfa dibindeki bir bağlantı bu ilişkiyi
              anlatmazdı. */}
          <CsvIndir
            adres={csvAdresleri.gecmis(izleme.id)}
            baslik="Bu ürünün tüm fiyat okumalarını CSV olarak indir (Türkçe Excel biçimi)"
          >
            CSV indir
          </CsvIndir>
        </div>
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
            seriler={urun.seriler}
            kaynaklar={urun.kaynaklar}
          />
        </Suspense>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <UyariKurulumu izleme={izleme} urun={urun} />

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
            {/* BACKLOG E4: yalnızca GERÇEKTEN bir bekleme durumu varken
                anlamlı — hiç bildirim gitmemişse "yeniden kur" fiilen
                hiçbir şeyi sıfırlamaz. */}
            {izleme.son_bildirim_ts != null && (
              <button
                onClick={() => guncelle.mutate({ yeniden_kur: true })}
                disabled={guncelle.isPending}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm
                           disabled:opacity-50 dark:border-slate-700"
              >
                Şimdi yeniden kur
              </button>
            )}
          </div>
          {rearmMetni && (
            <p className="mt-2 text-xs text-slate-500">{rearmMetni}</p>
          )}
          {/* BACKLOG G2 — "ürüne göre daraltma": Bildirimler sayfasına
              yalnızca bu ürünün uyarılarıyla süzülmüş gidiyor. */}
          <Link
            to={`/uyarilar?watch_id=${izleme.id}`}
            className="mt-3 inline-block text-xs text-slate-500 hover:underline"
          >
            Bu ürünün bildirimlerini gör
          </Link>
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
            {/* Açılır liste DEĞİL, onay kutuları: bir ürün BİRDEN ÇOK sette
                olabilir. Tek seçimli `select` bunu ifade edemezdi ve zaten
                modeli de o kısıtlıyordu (`Watch.set_id`). */}
            <fieldset disabled={guncelle.isPending} className="space-y-1">
              <legend className="sr-only">Bu ürünün ait olduğu setler</legend>
              {setler.map((s) => {
                const uye = izleme.set_idler.includes(s.id)
                return (
                  <label key={s.id}
                         className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={uye}
                      onChange={() =>
                        guncelle.mutate({
                          set_idler: uye
                            ? izleme.set_idler.filter((x) => x !== s.id)
                            : [...izleme.set_idler, s.id],
                        })
                      }
                      className="h-4 w-4 rounded border-slate-300 dark:border-slate-700"
                    />
                    <span>{s.ad}</span>
                    {s.hedef_butce != null && (
                      <span className="text-xs text-slate-500">
                        · bütçe {tl(s.hedef_butce)}
                      </span>
                    )}
                  </label>
                )
              })}
            </fieldset>
            <p className="mt-2 text-xs text-slate-500">
              Sete eklenen ürünler toplam bütçe hedefine dahil olur. Aynı ürün
              birden çok sette olabilir.
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
        <KaynakTablosu kaynaklar={urun.kaynaklar} izlemeId={izleme.id} />

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

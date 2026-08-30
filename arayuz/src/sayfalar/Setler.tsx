import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, Pencil, Plus, Trash2, X } from 'lucide-react'

import {
  useSetGuncelle, useSetOlustur, useSetSil, useSetUyeCikar, useSetler,
} from '../api/kancalar'
import Onay from '../bilesenler/Onay'
import SetUyeSecici from '../bilesenler/SetUyeSecici'
import SinyalRozeti from '../bilesenler/SinyalRozeti'
import { kisaTl, tl } from '../yardimcilar/bicim'
import { butceDurumu, enPahaliUye } from '../yardimcilar/setButcesi'

export default function Setler() {
  const { data: setler, isLoading } = useSetler()
  const olustur = useSetOlustur()
  const guncelle = useSetGuncelle()
  const sil = useSetSil()
  const [ad, setAd] = useState('')
  const [butce, setButce] = useState('')
  const [silinecek, setSilinecek] = useState<{ id: number; ad: string } | null>(null)
  const [duzenlenen, setDuzenlenen] = useState<number | null>(null)
  const [yeniButce, setYeniButce] = useState('')
  // Hangi setin içi açık ve hangisine ürün ekleniyor.
  const [acikSet, setAcikSet] = useState<number | null>(null)
  const [eklenenSet, setEklenenSet] = useState<number | null>(null)
  const uyeCikar = useSetUyeCikar()

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-xl font-semibold">Setler</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Ürünleri bütçeli koleksiyonlarda topla. Parçalar tek tek hedefte
          olmasa bile <strong>toplam</strong> bütçenin altına inince haber verilir.
        </p>
      </section>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!ad.trim()) return
          olustur.mutate(
            { ad: ad.trim(), butce: butce ? Number(butce) : null },
            { onSuccess: () => { setAd(''); setButce('') } },
          )
        }}
        className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4
                   sm:flex-row dark:border-slate-800 dark:bg-slate-900"
      >
        <label htmlFor="set-adi" className="sr-only">Set adı</label>
        <input
          id="set-adi"
          value={ad} onChange={(e) => setAd(e.target.value)}
          placeholder="Set adı (örn. PC Toplama)" required maxLength={60}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm
                     dark:border-slate-700 dark:bg-slate-950"
        />
        <label htmlFor="set-butce" className="sr-only">Hedef bütçe</label>
        <input
          id="set-butce"
          type="number" min="1" value={butce}
          onChange={(e) => setButce(e.target.value)} placeholder="Bütçe ₺"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                     sm:w-40 dark:border-slate-700 dark:bg-slate-950"
        />
        <button
          disabled={olustur.isPending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium
                     text-white disabled:opacity-50 dark:bg-white dark:text-slate-900"
        >
          {olustur.isPending ? 'Kuruluyor…' : 'Set kur'}
        </button>
      </form>

      {(olustur.isError || sil.isError || guncelle.isError) && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700
                      dark:bg-red-950/50 dark:text-red-300">
          {(olustur.error ?? sil.error ?? guncelle.error)?.message}
        </p>
      )}

      {isLoading && <p className="text-sm text-slate-500">Yükleniyor…</p>}

      <div className="space-y-3">
        {setler?.map((s) => {
          const oran = s.hedef_butce ? Math.min(100, (s.toplam / s.hedef_butce) * 100) : 0
          const durum = butceDurumu(s.toplam, s.hedef_butce, s.uye_sayisi, s.eksik_uye)
          const enPahali = enPahaliUye(s.uyeler)
          const acik = acikSet === s.id
          const eklemeAcik = eklenenSet === s.id
          return (
            <div key={s.id}
                 className="rounded-lg border border-slate-200 bg-white p-4
                            dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-medium">{s.ad}</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {s.uye_sayisi} ürün
                    {s.eksik_uye > 0 && ` · ${s.eksik_uye} tanesi henüz okunamadı`}
                  </p>
                  {s.uye_sayisi === 0 && (
                    <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                      Boş. Aşağıdaki <strong>Ürün ekle</strong> ile takip
                      listenden seç, ya da bir ürünün{' '}
                      <Link to="/" className="underline">detay sayfasından</Link>{' '}
                      ekle.
                    </p>
                  )}
                </div>
                <div className="text-right">
                  <div className="font-mono font-semibold">{tl(s.toplam)}</div>
                  {durum.tur === 'asiyor' && (
                    <div className="text-xs text-red-600 dark:text-red-400">
                      {kisaTl(durum.fark)} aşıyor (%{durum.yuzde})
                    </div>
                  )}
                  {durum.tur === 'altinda' && (
                    <div className="text-xs text-green-600 dark:text-green-400">
                      🎯 bütçe altında
                    </div>
                  )}
                  {(durum.tur === 'bos' || durum.tur === 'eksik') && (
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      bütçe {tl(s.hedef_butce)}
                    </div>
                  )}
                </div>
              </div>

              {durum.tur === 'asiyor' && (
                <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                  Sığması için {kisaTl(durum.fark)} daha düşmeli.
                </p>
              )}

              {s.hedef_butce != null && (
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100
                                dark:bg-slate-800">
                  <div
                    className={`h-full ${
                      durum.tur === 'altinda' ? 'bg-green-500'
                      : durum.tur === 'asiyor' ? 'bg-red-500'
                      : 'bg-slate-400'
                    }`}
                    style={{ width: `${oran}%` }}
                  />
                </div>
              )}

              {duzenlenen === s.id ? (
                <form
                  className="mt-3 flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault()
                    guncelle.mutate(
                      {
                        id: s.id,
                        girdi: { hedef_butce: yeniButce ? Number(yeniButce) : null },
                      },
                      { onSuccess: () => setDuzenlenen(null) },
                    )
                  }}
                >
                  <label htmlFor={`butce-${s.id}`} className="sr-only">
                    Yeni bütçe
                  </label>
                  <input
                    id={`butce-${s.id}`}
                    type="number" min="1" value={yeniButce} autoFocus
                    onChange={(e) => setYeniButce(e.target.value)}
                    placeholder="Bütçe ₺ (boş = kaldır)"
                    className="flex-1 rounded-md border border-slate-300 px-3 py-1.5
                               text-sm dark:border-slate-700 dark:bg-slate-950"
                  />
                  <button
                    disabled={guncelle.isPending}
                    className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white
                               disabled:opacity-50 dark:bg-white dark:text-slate-900"
                  >
                    Kaydet
                  </button>
                  <button
                    type="button" onClick={() => setDuzenlenen(null)}
                    className="rounded-md border border-slate-300 px-3 py-1.5 text-sm
                               dark:border-slate-700"
                  >
                    Vazgeç
                  </button>
                </form>
              ) : (
                <div className="mt-3 flex flex-wrap gap-4">
                  <button
                    onClick={() => setAcikSet(acik ? null : s.id)}
                    aria-expanded={acik}
                    className="inline-flex items-center gap-1 text-xs text-slate-500
                               hover:underline"
                  >
                    {acik ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    İçindekiler ({s.uye_sayisi})
                  </button>
                  <button
                    onClick={() => {
                      setAcikSet(s.id)
                      setEklenenSet(eklemeAcik ? null : s.id)
                    }}
                    className="inline-flex items-center gap-1 text-xs text-slate-500
                               hover:underline"
                  >
                    <Plus size={13} /> Ürün ekle
                  </button>
                  <button
                    onClick={() => {
                      setDuzenlenen(s.id)
                      setYeniButce(s.hedef_butce != null ? String(s.hedef_butce) : '')
                    }}
                    className="inline-flex items-center gap-1 text-xs text-slate-500
                               hover:underline"
                  >
                    <Pencil size={13} /> Bütçeyi düzenle
                  </button>
                  <button
                    onClick={() => setSilinecek({ id: s.id, ad: s.ad })}
                    className="inline-flex items-center gap-1 text-xs text-red-600
                               hover:underline"
                  >
                    <Trash2 size={13} /> Seti sil (ürünler silinmez)
                  </button>
                </div>
              )}

              {acik && s.uyeler.length > 0 && (
                <ul className="mt-3 divide-y divide-slate-100 border-t
                               border-slate-100 pt-1 dark:divide-slate-800
                               dark:border-slate-800">
                  {s.uyeler.map((u) => (
                    <li key={u.izleme_id}
                        className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
                      <Link to={`/izleme/${u.izleme_id}`}
                            className="flex-1 truncate hover:underline">
                        {u.ad}
                      </Link>
                      <SinyalRozeti
                        sinyal={u.sinyal} yuzdelik={u.yuzdelik} gecmisGun={u.gecmis_gun}
                      />
                      {u.izleme_id === enPahali && (
                        <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px]
                                         font-medium text-red-700 dark:bg-red-950/50
                                         dark:text-red-300">
                          en pahalı
                        </span>
                      )}
                      {u.kilitli && (
                        <span className="text-xs text-slate-400">kilitli</span>
                      )}
                      <span className="font-mono text-xs">
                        {u.fiyat != null
                          ? tl(u.fiyat)
                          : <span className="text-amber-600">fiyat yok</span>}
                      </span>
                      <button
                        onClick={() =>
                          uyeCikar.mutate({ setId: s.id, izlemeId: u.izleme_id })
                        }
                        title="Setten çıkar (ürün silinmez)"
                        aria-label={`${u.ad} setten çıkar`}
                        className="rounded p-1 text-slate-400 hover:text-red-600"
                      >
                        <X size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {eklemeAcik && (
                <SetUyeSecici
                  setId={s.id}
                  mevcutUyeIdler={s.uyeler.map((u) => u.izleme_id)}
                  onKapat={() => setEklenenSet(null)}
                />
              )}
            </div>
          )
        })}
        {setler?.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center
                        text-sm text-slate-500 dark:border-slate-700">
            Henüz set yok.
          </p>
        )}
      </div>

      <Onay
        acik={silinecek !== null}
        baslik="Set silinsin mi?"
        aciklama={`"${silinecek?.ad ?? ''}" seti silinecek. İçindeki ürünler
                   takipte kalır, yalnızca gruplamadan çıkar.`}
        onayMetni="Seti sil"
        bekliyor={sil.isPending}
        onIptal={() => setSilinecek(null)}
        onOnay={() =>
          silinecek &&
          sil.mutate(silinecek.id, {
            onSuccess: () => setSilinecek(null),
            onError: () => setSilinecek(null),
          })
        }
      />
    </div>
  )
}

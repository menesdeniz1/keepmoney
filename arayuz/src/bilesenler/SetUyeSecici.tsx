import { useMemo, useState } from 'react'

import { useIzlemeler, useSetUyeEkle } from '../api/kancalar'
import type { UyelikSonucu } from '../api/tipler'
import { tl } from '../yardimcilar/bicim'

/**
 * Setin İÇİNDEN çoklu ürün ekleme.
 *
 * NEDEN VAR: ürün eklemenin tek yolu her ürünün detay sayfasına tek tek
 * gidip oradan set seçmekti — 8 parçalık bir PC için 8 ayrı sayfa. Oysa
 * kullanıcı set kurarken "bu sete hangi ürünler girer" diye düşünür,
 * "bu ürün hangi sete gider" diye değil. Arayüz soruyu ters soruyordu.
 *
 * KISMİ BAŞARI: sunucu eklenenleri ve SEBEBİYLE atlananları döndürüyor.
 * Hepsini birden reddetmek, sekiz seçimden biri bayat diye sekizini birden
 * kaybettirirdi.
 */
export default function SetUyeSecici({
  setId,
  mevcutUyeIdler,
  onKapat,
}: {
  setId: number
  mevcutUyeIdler: number[]
  onKapat: () => void
}) {
  const { data: izlemeler, isLoading } = useIzlemeler()
  const ekle = useSetUyeEkle()
  const [secili, setSecili] = useState<number[]>([])
  const [arama, setArama] = useState('')
  const [sonuc, setSonuc] = useState<UyelikSonucu | null>(null)

  // Zaten üye olanlar listede GÖSTERİLMEZ: seçilemeyecek satırları göstermek
  // listeyi uzatır ve kullanıcıyı "neden tıklayamıyorum" sorusuna sokar.
  const adaylar = useMemo(() => {
    const uye = new Set(mevcutUyeIdler)
    const q = arama.trim().toLocaleLowerCase('tr')
    return (izlemeler ?? [])
      .filter((i) => !uye.has(i.id))
      .filter((i) => !q || i.urun.ad.toLocaleLowerCase('tr').includes(q))
  }, [izlemeler, mevcutUyeIdler, arama])

  function degistir(id: number) {
    setSecili((ö) => (ö.includes(id) ? ö.filter((x) => x !== id) : [...ö, id]))
  }

  if (sonuc) {
    return (
      <div className="mt-3 rounded-md border border-slate-200 p-3 text-sm
                      dark:border-slate-700">
        <p className="font-medium">{sonuc.eklendi.length} ürün eklendi.</p>
        {sonuc.atlandi.length > 0 && (
          <ul className="mt-1 text-xs text-amber-700 dark:text-amber-400">
            {sonuc.atlandi.map((a) => (
              <li key={a.id}>
                #{a.id}:{' '}
                {a.sebep === 'zaten_uye' ? 'zaten sette' : 'bulunamadı'}
              </li>
            ))}
          </ul>
        )}
        <button
          onClick={onKapat}
          className="mt-2 rounded-md border border-slate-300 px-3 py-1.5 text-xs
                     dark:border-slate-700"
        >
          Kapat
        </button>
      </div>
    )
  }

  return (
    <div className="mt-3 rounded-md border border-slate-200 p-3
                    dark:border-slate-700">
      {isLoading && <p className="text-sm text-slate-500">Yükleniyor…</p>}

      {!isLoading && adaylar.length === 0 && (
        <p className="text-sm text-slate-500">
          {arama
            ? 'Bu aramaya uyan, sette olmayan ürün yok.'
            : 'Takip listendeki tüm ürünler zaten bu sette.'}
        </p>
      )}

      {!isLoading && (izlemeler?.length ?? 0) > 0 && (
        <>
          <label htmlFor={`ara-${setId}`} className="sr-only">
            Ürün ara
          </label>
          <input
            id={`ara-${setId}`}
            value={arama}
            onChange={(e) => setArama(e.target.value)}
            placeholder="Ürün ara…"
            className="mb-2 w-full rounded-md border border-slate-300 px-3 py-1.5
                       text-sm dark:border-slate-700 dark:bg-slate-950"
          />

          <div className="max-h-64 space-y-1 overflow-y-auto">
            {adaylar.map((i) => (
              <label
                key={i.id}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1
                           text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <input
                  type="checkbox"
                  checked={secili.includes(i.id)}
                  onChange={() => degistir(i.id)}
                  className="h-4 w-4 rounded border-slate-300 dark:border-slate-700"
                />
                <span className="flex-1 truncate">{i.urun.ad}</span>
                <span className="font-mono text-xs text-slate-500">
                  {i.urun.guncel_fiyat != null ? tl(i.urun.guncel_fiyat) : '—'}
                </span>
              </label>
            ))}
          </div>

          <div className="mt-3 flex items-center gap-2">
            <button
              disabled={secili.length === 0 || ekle.isPending}
              onClick={() =>
                ekle.mutate(
                  { setId, idler: secili },
                  { onSuccess: (s) => setSonuc(s) },
                )
              }
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white
                         disabled:opacity-50 dark:bg-white dark:text-slate-900"
            >
              {ekle.isPending ? 'Ekleniyor…' : `Ekle (${secili.length})`}
            </button>
            <button
              onClick={onKapat}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm
                         dark:border-slate-700"
            >
              Vazgeç
            </button>
          </div>
        </>
      )}

      {ekle.isError && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {ekle.error.message}
        </p>
      )}
    </div>
  )
}

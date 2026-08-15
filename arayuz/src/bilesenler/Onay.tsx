import { useEffect, useRef } from 'react'

/**
 * Yıkıcı işlemler için onay kutusu.
 *
 * NEDEN VAR: "Seti sil" ve "Takipten çıkar" düğmeleri tek tıkla, onaysız
 * çalışıyordu. Yanlışlıkla tıklanan bir düğme aylarca biriktirilmiş bir
 * takibi geri alınamaz biçimde siliyordu.
 *
 * ERİŞİLEBİLİRLİK — `<dialog>` kullanılıyor, `<div role="dialog">` değil:
 * odak tuzağı, Esc ile kapanma ve arka planın etkisizleşmesi tarayıcının
 * yerel davranışıyla geliyor. Elle ARIA kurmaya çalışmak, aynı davranışın
 * eksik bir taklidini üretirdi.
 */
export default function Onay({
  acik,
  baslik,
  aciklama,
  onayMetni = 'Sil',
  bekliyor = false,
  onOnay,
  onIptal,
}: {
  acik: boolean
  baslik: string
  aciklama?: string
  onayMetni?: string
  bekliyor?: boolean
  onOnay: () => void
  onIptal: () => void
}) {
  const kutu = useRef<HTMLDialogElement>(null)
  const iptalDugmesi = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const d = kutu.current
    if (!d) return
    if (acik && !d.open) {
      d.showModal()
      // Odak YIKICI OLMAYAN düğmede başlar: Enter'a refleksle basan
      // kullanıcı yanlışlıkla silmesin.
      iptalDugmesi.current?.focus()
    } else if (!acik && d.open) {
      d.close()
    }
  }, [acik])

  return (
    <dialog
      ref={kutu}
      onCancel={(e) => {
        e.preventDefault()
        onIptal()
      }}
      onClick={(e) => {
        // Arka plana (dialog elemanının kendisine) tıklayınca kapat.
        if (e.target === kutu.current) onIptal()
      }}
      className="max-w-sm rounded-lg border border-slate-200 bg-white p-5
                 text-slate-900 backdrop:bg-slate-900/40 dark:border-slate-700
                 dark:bg-slate-900 dark:text-slate-100"
    >
      <h2 className="text-base font-semibold">{baslik}</h2>
      {aciklama && (
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          {aciklama}
        </p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <button
          ref={iptalDugmesi}
          type="button"
          onClick={onIptal}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm
                     dark:border-slate-700"
        >
          Vazgeç
        </button>
        <button
          type="button"
          onClick={onOnay}
          disabled={bekliyor}
          className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white
                     disabled:opacity-50"
        >
          {bekliyor ? 'Siliniyor…' : onayMetni}
        </button>
      </div>
    </dialog>
  )
}

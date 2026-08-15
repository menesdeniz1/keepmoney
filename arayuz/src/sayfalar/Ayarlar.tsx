import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { ApiHatasi, api } from '../api/istemci'
import { anahtar, useBen } from '../api/kancalar'

export default function Ayarlar() {
  const { data: ben } = useBen()
  const qc = useQueryClient()
  const [baglanti, setBaglanti] = useState<string | null>(null)
  const [hata, setHata] = useState<string | null>(null)

  async function baglantiUret() {
    setHata(null)
    try {
      const y = await api.telegramBaglanti()
      setBaglanti(y.baglanti)
    } catch (e) {
      setHata(e instanceof ApiHatasi ? e.message : 'Bağlantı üretilemedi')
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Ayarlar</h1>

      <section className="rounded-lg border border-slate-200 bg-white p-4
                          dark:border-slate-800 dark:bg-slate-900">
        <h2 className="font-medium">Hesap</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{ben?.eposta}</p>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4
                          dark:border-slate-800 dark:bg-slate-900">
        <h2 className="font-medium">Telegram bildirimleri</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Bağlarsan fiyat uyarıları Telegram'a da düşer ve hedefleri bottan
          değiştirebilirsin.
        </p>

        {ben?.telegram_bagli ? (
          <div className="mt-3 flex items-center gap-3">
            <span className="rounded bg-green-100 px-2 py-1 text-sm text-green-800
                             dark:bg-green-950 dark:text-green-300">✓ Bağlı</span>
            <button
              onClick={async () => {
                await api.telegramKaldir()
                await qc.invalidateQueries({ queryKey: anahtar.ben })
              }}
              className="text-sm text-red-600 hover:underline"
            >
              Bağlantıyı kaldır
            </button>
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            <button
              onClick={() => void baglantiUret()}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white
                         dark:bg-white dark:text-slate-900"
            >
              Telegram'a bağla
            </button>
            {baglanti && (
              <p className="text-sm">
                <a href={baglanti} target="_blank" rel="noopener noreferrer"
                   className="text-blue-600 underline">Bu bağlantıya tıkla</a>
                {' '}— 10 dakika geçerli. Chat ID kopyalaman gerekmiyor.
              </p>
            )}
            {hata && <p className="text-sm text-red-600">{hata}</p>}
          </div>
        )}
      </section>
    </div>
  )
}

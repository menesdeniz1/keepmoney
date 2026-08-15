import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { ApiHatasi, api } from '../api/istemci'
import { anahtar } from '../api/kancalar'

type Durum = 'calisiyor' | 'tamam' | 'hata'

/**
 * E-posta doğrulama — bağlantıya tıklandığında açılan sayfa.
 *
 * Doğrulama sayfa açılır açılmaz yapılır; kullanıcıya tıklayacak bir şey
 * bırakmanın anlamı yok, bağlantıya tıklamak zaten niyet beyanıdır.
 */
export default function EpostaDogrula() {
  const [parametreler] = useSearchParams()
  const token = parametreler.get('token') ?? ''
  const [durum, setDurum] = useState<Durum>('calisiyor')
  const [hata, setHata] = useState<string | null>(null)
  const qc = useQueryClient()
  // React 19 StrictMode geliştirmede efektleri iki kez çalıştırır; token tek
  // kullanımlık olduğu için ikinci çağrı "geçersiz" hatası verirdi.
  const calisti = useRef(false)

  useEffect(() => {
    if (calisti.current) return
    calisti.current = true

    if (!token) {
      setDurum('hata')
      setHata('Bağlantı eksik görünüyor.')
      return
    }
    api
      .epostaDogrula(token)
      .then(() => {
        setDurum('tamam')
        void qc.invalidateQueries({ queryKey: anahtar.ben })
      })
      .catch((e) => {
        setDurum('hata')
        setHata(e instanceof ApiHatasi ? e.message : 'Doğrulama başarısız')
      })
  }, [token, qc])

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm text-center">
        <h1 className="text-2xl font-semibold tracking-tight">E-posta doğrulama</h1>

        {durum === 'calisiyor' && (
          <p className="mt-6 text-sm text-slate-500">Doğrulanıyor…</p>
        )}

        {durum === 'tamam' && (
          <p className="mt-6 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800
                        dark:bg-emerald-950/50 dark:text-emerald-300">
            ✅ Adresin doğrulandı.
          </p>
        )}

        {durum === 'hata' && (
          <p className="mt-6 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700
                        dark:bg-red-950/50 dark:text-red-300">
            {hata} Ayarlar sayfasından yeni bağlantı isteyebilirsin.
          </p>
        )}

        <Link to="/" className="mt-6 inline-block text-sm text-slate-500 hover:underline">
          Panele dön
        </Link>
      </div>
    </div>
  )
}

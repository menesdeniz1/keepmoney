import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { ApiHatasi, api } from '../api/istemci'

/**
 * Parola sıfırlama — e-postadaki bağlantının açtığı sayfa.
 *
 * Token adres çubuğundan okunur. Sunucu tarafında tek kullanımlıktır ve
 * kısa ömürlüdür; başarılı sıfırlamadan sonra sunucu oturum çerezini de
 * kurduğu için kullanıcı doğrudan panele geçer — yeni parolayı bir daha
 * yazdırmak gereksiz sürtünme olurdu.
 */
export default function ParolaSifirla() {
  const [parametreler] = useSearchParams()
  const token = parametreler.get('token') ?? ''
  const [parola, setParola] = useState('')
  const [tekrar, setTekrar] = useState('')
  const [hata, setHata] = useState<string | null>(null)
  const [bekliyor, setBekliyor] = useState(false)
  const navigate = useNavigate()
  const qc = useQueryClient()

  async function gonder(e: React.FormEvent) {
    e.preventDefault()
    setHata(null)
    if (parola !== tekrar) {
      setHata('Parolalar aynı değil')
      return
    }
    setBekliyor(true)
    try {
      await api.parolaSifirla(token, parola)
      await qc.invalidateQueries()
      navigate('/', { replace: true })
    } catch (e) {
      setHata(e instanceof ApiHatasi ? e.message : 'Beklenmeyen bir hata oldu')
    } finally {
      setBekliyor(false)
    }
  }

  if (!token) {
    return (
      <Kabuk>
        <p className="text-sm text-red-700 dark:text-red-300">
          Bağlantı eksik görünüyor. E-postandaki bağlantıya yeniden tıkla.
        </p>
      </Kabuk>
    )
  }

  return (
    <Kabuk>
      <form onSubmit={gonder} className="space-y-3">
        <input
          type="password" required minLength={8} autoComplete="new-password"
          value={parola} onChange={(e) => setParola(e.target.value)}
          placeholder="Yeni parola (en az 8 karakter)"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                     dark:border-slate-700 dark:bg-slate-950"
        />
        <input
          type="password" required minLength={8} autoComplete="new-password"
          value={tekrar} onChange={(e) => setTekrar(e.target.value)}
          placeholder="Yeni parola (tekrar)"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                     dark:border-slate-700 dark:bg-slate-950"
        />
        {hata && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700
                        dark:bg-red-950/50 dark:text-red-300">{hata}</p>
        )}
        <button
          type="submit" disabled={bekliyor}
          className="w-full rounded-md bg-slate-900 py-2 text-sm font-medium text-white
                     disabled:opacity-50 dark:bg-white dark:text-slate-900"
        >
          {bekliyor ? 'Kaydediliyor…' : 'Parolayı değiştir'}
        </button>
      </form>
    </Kabuk>
  )
}

function Kabuk({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-center text-2xl font-semibold tracking-tight">
          Yeni parola
        </h1>
        <div className="mt-8">{children}</div>
      </div>
    </div>
  )
}

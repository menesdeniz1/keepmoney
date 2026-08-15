import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { ApiHatasi, api } from '../api/istemci'
import { anahtar } from '../api/kancalar'

type Kip = 'giris' | 'kayit' | 'unuttum'

export default function Giris() {
  const [kip, setKip] = useState<Kip>('giris')
  const [eposta, setEposta] = useState('')
  const [parola, setParola] = useState('')
  const [hata, setHata] = useState<string | null>(null)
  const [bilgi, setBilgi] = useState<string | null>(null)
  const [bekliyor, setBekliyor] = useState(false)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const kayitMi = kip === 'kayit'
  const unuttumMu = kip === 'unuttum'

  function kipDegistir(yeni: Kip) {
    setKip(yeni)
    setHata(null)
    setBilgi(null)
  }

  async function gonder(e: React.FormEvent) {
    e.preventDefault()
    setHata(null)
    setBilgi(null)
    setBekliyor(true)
    try {
      if (unuttumMu) {
        const y = await api.parolaSifirlamaIste(eposta)
        // Sunucu hesabın varlığını SIZDIRMAZ; mesaj da bu yüzden koşullu
        // değil — "kayıtlıysa gönderildi" der.
        setBilgi(y.durum)
        return
      }
      if (kayitMi) await api.kayit(eposta, parola)
      await api.giris(eposta, parola)
      // Token'a dokunmuyoruz — sunucu httpOnly çerezi kurdu.
      await qc.invalidateQueries({ queryKey: anahtar.ben })
      navigate('/', { replace: true })
    } catch (e) {
      setHata(e instanceof ApiHatasi ? e.message : 'Beklenmeyen bir hata oldu')
    } finally {
      setBekliyor(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-center text-2xl font-semibold tracking-tight">KeepMoney</h1>
        <p className="mt-2 text-center text-sm text-slate-500 dark:text-slate-400">
          Fiyatı değil, <strong>doğru zamanı</strong> takip et.
        </p>

        <form onSubmit={gonder} className="mt-8 space-y-3">
          <input
            type="email" required autoComplete="email" value={eposta}
            onChange={(e) => setEposta(e.target.value)} placeholder="E-posta"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                       dark:border-slate-700 dark:bg-slate-950"
          />
          {!unuttumMu && (
            <input
              type="password" required minLength={8}
              autoComplete={kayitMi ? 'new-password' : 'current-password'}
              value={parola} onChange={(e) => setParola(e.target.value)}
              placeholder="Parola (en az 8 karakter)"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm
                         dark:border-slate-700 dark:bg-slate-950"
            />
          )}
          {hata && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700
                          dark:bg-red-950/50 dark:text-red-300">{hata}</p>
          )}
          {bilgi && (
            <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800
                          dark:bg-emerald-950/50 dark:text-emerald-300">{bilgi}</p>
          )}
          <button
            type="submit" disabled={bekliyor}
            className="w-full rounded-md bg-slate-900 py-2 text-sm font-medium text-white
                       disabled:opacity-50 dark:bg-white dark:text-slate-900"
          >
            {bekliyor
              ? 'Bekleyin…'
              : unuttumMu
                ? 'Sıfırlama bağlantısı gönder'
                : kayitMi
                  ? 'Hesap oluştur'
                  : 'Giriş yap'}
          </button>
        </form>

        <div className="mt-4 space-y-2 text-center text-sm text-slate-500">
          {unuttumMu ? (
            <button onClick={() => kipDegistir('giris')} className="hover:underline">
              Girişe dön
            </button>
          ) : (
            <>
              <button
                onClick={() => kipDegistir(kayitMi ? 'giris' : 'kayit')}
                className="block w-full hover:underline"
              >
                {kayitMi ? 'Zaten hesabım var' : 'Hesabım yok, oluştur'}
              </button>
              {!kayitMi && (
                <button
                  onClick={() => kipDegistir('unuttum')}
                  className="block w-full hover:underline"
                >
                  Parolamı unuttum
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

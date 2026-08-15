import { Bell, LayoutGrid, LogOut, Package, Settings } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { api } from '../api/istemci'
import { useBen, useOkunmamisSayisi } from '../api/kancalar'

const BAGLANTILAR = [
  { yol: '/', etiket: 'Panel', ikon: LayoutGrid },
  { yol: '/setler', etiket: 'Setler', ikon: Package },
  { yol: '/uyarilar', etiket: 'Bildirimler', ikon: Bell },
  { yol: '/ayarlar', etiket: 'Ayarlar', ikon: Settings },
] as const

export default function Duzen() {
  const { data: ben } = useBen()
  const { data: sayi } = useOkunmamisSayisi()
  const navigate = useNavigate()
  const qc = useQueryClient()

  async function cikisYap() {
    await api.cikis()
    qc.clear()
    navigate('/giris', { replace: true })
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80
                         backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <span className="text-lg font-semibold tracking-tight">KeepMoney</span>

          <nav className="flex flex-1 items-center gap-1">
            {BAGLANTILAR.map(({ yol, etiket, ikon: Ikon }) => (
              <NavLink
                key={yol}
                to={yol}
                end={yol === '/'}
                className={({ isActive }) =>
                  `inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm
                   transition ${
                     isActive
                       ? 'bg-slate-100 font-medium dark:bg-slate-800'
                       : 'text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-900'
                   }`
                }
              >
                <Ikon size={16} />
                <span className="hidden sm:inline">{etiket}</span>
                {yol === '/uyarilar' && (sayi?.okunmamis ?? 0) > 0 && (
                  <span className="ml-0.5 rounded-full bg-red-600 px-1.5 text-[11px]
                                   font-semibold text-white">
                    {sayi?.okunmamis}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>

          <button
            onClick={() => void cikisYap()}
            title={ben?.eposta}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm
                       text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-900"
          >
            <LogOut size={16} />
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}

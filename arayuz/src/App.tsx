import { Navigate, Route, Routes } from 'react-router-dom'

import { useBen } from './api/kancalar'
import Duzen from './bilesenler/Duzen'
import Ayarlar from './sayfalar/Ayarlar'
import Giris from './sayfalar/Giris'
import IzlemeDetay from './sayfalar/IzlemeDetay'
import Panel from './sayfalar/Panel'
import Setler from './sayfalar/Setler'
import Uyarilar from './sayfalar/Uyarilar'

export default function App() {
  const { data: ben, isLoading, isError } = useBen()

  // Oturum kontrolü tamamlanmadan yönlendirme yapma: aksi halde sayfa
  // yenilendiğinde kullanıcı bir an giriş ekranını görür (flash).
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Yükleniyor…
      </div>
    )
  }

  if (isError || !ben) {
    return (
      <Routes>
        <Route path="/giris" element={<Giris />} />
        <Route path="*" element={<Navigate to="/giris" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route element={<Duzen />}>
        <Route index element={<Panel />} />
        <Route path="/izleme/:id" element={<IzlemeDetay />} />
        <Route path="/setler" element={<Setler />} />
        <Route path="/uyarilar" element={<Uyarilar />} />
        <Route path="/ayarlar" element={<Ayarlar />} />
      </Route>
      <Route path="/giris" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

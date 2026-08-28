import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { OTURUM_BITTI } from './api/istemci'
import { anahtar, useBen } from './api/kancalar'
import Duzen from './bilesenler/Duzen'
import Ayarlar from './sayfalar/Ayarlar'
import EpostaDogrula from './sayfalar/EpostaDogrula'
import Firsatlar from './sayfalar/Firsatlar'
import Giris from './sayfalar/Giris'
import ParolaSifirla from './sayfalar/ParolaSifirla'
import IzlemeDetay from './sayfalar/IzlemeDetay'
import Panel from './sayfalar/Panel'
import Setler from './sayfalar/Setler'
import Uyarilar from './sayfalar/Uyarilar'

export default function App() {
  const { data: ben, isLoading, isError } = useBen()
  const qc = useQueryClient()

  // Oturum uygulama AÇIKKEN de dolabilir (token 7 gün ömürlü).
  //
  // DİKKAT — burada yalnızca `qc.clear()` çağırmak SONSUZ DÖNGÜ kuruyordu:
  // önbellek temizlenince bağlı bileşenlerin sorguları hemen yeniden
  // çalışıyor, 401 alıyor, olayı yeniden tetikliyor… Ekran "giriş yapılmış"
  // düzeninde kilitlenip arka planda 401 yağdırıyordu.
  //
  // Çözüm: `ben`i AÇIKÇA null yap. Aşağıdaki dal anında giriş ekranına
  // geçer, korumalı sayfalar ve sorguları unmount olur — yeniden çekecek
  // kimse kalmaz, döngü kapanır.
  useEffect(() => {
    const isle = () => {
      qc.clear()
      qc.setQueryData(anahtar.ben, null)
    }
    window.addEventListener(OTURUM_BITTI, isle)
    return () => window.removeEventListener(OTURUM_BITTI, isle)
  }, [qc])

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
        {/* Bu iki yol OTURUM İSTEMEZ: kullanıcı zaten giriş yapamadığı için
            buraya geliyor. Giriş duvarının arkasına koymak, parola sıfırlama
            bağlantısını kullanılamaz hâle getirirdi. */}
        <Route path="/parola-sifirla" element={<ParolaSifirla />} />
        <Route path="/eposta-dogrula" element={<EpostaDogrula />} />
        <Route path="*" element={<Navigate to="/giris" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route element={<Duzen />}>
        <Route index element={<Panel />} />
        <Route path="/firsatlar" element={<Firsatlar />} />
        <Route path="/izleme/:id" element={<IzlemeDetay />} />
        <Route path="/setler" element={<Setler />} />
        <Route path="/uyarilar" element={<Uyarilar />} />
        <Route path="/ayarlar" element={<Ayarlar />} />
      </Route>
      <Route path="/eposta-dogrula" element={<EpostaDogrula />} />
      <Route path="/parola-sifirla" element={<ParolaSifirla />} />
      <Route path="/giris" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

import { Bell, LayoutGrid, LogOut, Package, Settings, Tag } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { api } from '../api/istemci'
import { useBen, useOkunmamisSayisi } from '../api/kancalar'

// BACKLOG D2: Fırsatlar, Panel'den SONRA İKİNCİ sırada — Deals sayfası
// "her gün açılacak sayfa" olarak tasarlandı, gezinmede öne yakın durmalı.
const BAGLANTILAR = [
  { yol: '/', etiket: 'Panel', ikon: LayoutGrid },
  { yol: '/firsatlar', etiket: 'Fırsatlar', ikon: Tag },
  { yol: '/setler', etiket: 'Setler', ikon: Package },
  { yol: '/uyarilar', etiket: 'Bildirimler', ikon: Bell },
  { yol: '/ayarlar', etiket: 'Ayarlar', ikon: Settings },
] as const

export default function Duzen() {
  const { data: ben } = useBen()
  const { data: sayi } = useOkunmamisSayisi()
  const qc = useQueryClient()

  async function cikisYap() {
    // Sunucu çağrısı BEST-EFFORT: ağ koptuysa ya da sunucu hata verdiyse
    // bile yerel oturum kapanmalı. Eskiden hata yakalanmıyordu — çağrı
    // düşerse `qc.clear()` ve yönlendirme hiç çalışmıyor, kullanıcı çıkış
    // yapamıyordu (üstelik hiçbir geri bildirim de almadan).
    try {
      await api.cikis()
    } catch {
      // yut: çerezi sunucu siliyor, yerel durum aşağıda zaten sıfırlanıyor
    }
    qc.clear()

    // TAM SAYFA YENİLEME — istemci tarafı yönlendirme DEĞİL.
    //
    // İki sebep:
    //  1) DOĞRULUK. `navigate('/giris')` ile React Router'ın "giriş
    //     yapılmışken /giris → /" yönlendirmesi yarışıyordu: kullanıcı
    //     panele geri atılıyor, arka planda 401 yağıyor ve çıkış fiilen
    //     gerçekleşmiyordu.
    //  2) GÜVENLİK. Yeniden yükleme JS belleğindeki her şeyi (bileşen
    //     durumunda kalmış kişisel veri dahil) siler. Çıkışta bunu garanti
    //     etmek, önbelleği tek tek temizlemeye çalışmaktan sağlamdır.
    window.location.assign('/giris')
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80
                         backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <span className="text-lg font-semibold tracking-tight">KeepMoney</span>

          {/* `min-w-0` — GERÇEK TARAYICIDA (375px) ÖLÇÜLDÜ: beşinci sekme
              (BACKLOG D2, Fırsatlar) eklenince nav'ın İÇERİK genişliği
              mevcut alanı aştı ve flex item'ların varsayılan `min-width:
              auto`'su (klasik flexbox tuzağı — bkz. A8'in CSS Grid'teki
              aynı ailedeki tuzağı) nav'ın küçülmesini ENGELLEDİ; taşan
              genişlik, sıradaki flex kardeşi (çıkış düğmesi) viewport
              dışına itti — header satırı 389px, viewport 375px. `nav`'ın
              kendi `scrollWidth`'i bunu YAKALAMAZ (kendi içinde taşma
              yok, sorun onu SIĞDIRAN üst satırda), bu yüzden header
              satırının/gövdenin toplam genişliği ölçülmeli. */}
          <nav className="flex min-w-0 flex-1 items-center gap-1">
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
                  <span
                    className="ml-0.5 rounded-full bg-red-600 px-1.5 text-[11px]
                               font-semibold text-white"
                    aria-label={`${sayi?.okunmamis} okunmamış bildirim`}
                  >
                    {sayi?.okunmamis}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>

          {/* İKON-ONLY DÜĞMEDE ERİŞİLEBİLİR AD ŞART. Burada yalnızca bir
              SVG vardı ve `title` kullanıcının e-postasıydı — ekran okuyucu
              "çıkış" yerine e-posta adresini okuyordu, yani düğmenin ne
              yaptığı hiç duyurulmuyordu. `aria-label` amacı söyler; e-posta
              görsel ipucu olarak `title`da kalır. */}
          <button
            onClick={() => void cikisYap()}
            aria-label="Çıkış yap"
            title={ben?.eposta ? `Çıkış yap (${ben.eposta})` : 'Çıkış yap'}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm
                       text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-900"
          >
            <LogOut size={16} aria-hidden="true" />
            <span className="sr-only">Çıkış yap</span>
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>

      {/* Hukuki metinlere HER SAYFADAN erişilebilmeli — yalnızca kayıt
          ekranındaki onay satırında bulunmaları, hesap açtıktan sonra
          metni bir daha bulmayı imkânsız kılardı. */}
      <footer className="mx-auto max-w-5xl px-4 pb-8 text-xs text-slate-400">
        <Link to="/gizlilik" className="hover:underline">
          Gizlilik
        </Link>
        <span aria-hidden="true"> · </span>
        <Link to="/kosullar" className="hover:underline">
          Kullanım koşulları
        </Link>
      </footer>
    </div>
  )
}

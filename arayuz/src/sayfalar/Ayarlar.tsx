import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { ApiHatasi, api } from '../api/istemci'
import { anahtar, useBen } from '../api/kancalar'

export default function Ayarlar() {
  const { data: ben } = useBen()
  const qc = useQueryClient()
  const [baglanti, setBaglanti] = useState<string | null>(null)
  const [hata, setHata] = useState<string | null>(null)
  const [dogrulamaBilgi, setDogrulamaBilgi] = useState<string | null>(null)
  const [silParola, setSilParola] = useState('')
  const [silOnay, setSilOnay] = useState(false)
  const [silHata, setSilHata] = useState<string | null>(null)

  async function dogrulamaGonder() {
    setDogrulamaBilgi(null)
    try {
      const y = await api.dogrulamaYenidenGonder()
      setDogrulamaBilgi(y.durum)
    } catch (e) {
      setDogrulamaBilgi(
        e instanceof ApiHatasi ? e.message : 'Bağlantı gönderilemedi',
      )
    }
  }

  async function hesabiSil() {
    setSilHata(null)
    try {
      await api.hesabiSil(silParola)
      qc.clear()
      // TAM SAYFA YENİLEME — çıkıştaki gerekçenin aynısı (bkz. Duzen.tsx):
      // istemci yönlendirmesi, "giriş yapılmışken /giris → /" kuralıyla
      // yarışıyor ve kullanıcı silinmiş bir hesapla panele geri atılıyordu.
      // Ayrıca yeniden yükleme, JS belleğinde kalan kişisel veriyi de siler.
      window.location.assign('/giris')
    } catch (e) {
      setSilHata(e instanceof ApiHatasi ? e.message : 'Hesap silinemedi')
    }
  }

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

        {ben?.eposta_dogrulandi ? (
          <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-400">
            ✓ E-posta adresin doğrulandı
          </p>
        ) : (
          <div className="mt-2 space-y-2">
            <p className="text-sm text-amber-700 dark:text-amber-400">
              ⚠️ E-posta adresin doğrulanmadı. Doğrulanmamış adrese parola
              sıfırlama bağlantısı gönderemeyiz — hesabını kaybetme riski var.
            </p>
            <button
              onClick={() => void dogrulamaGonder()}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm
                         dark:border-slate-700"
            >
              Doğrulama bağlantısını yeniden gönder
            </button>
            {dogrulamaBilgi && (
              <p className="text-sm text-slate-500">{dogrulamaBilgi}</p>
            )}
          </div>
        )}
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
              <div className="space-y-2 text-sm">
                <p>
                  <a href={baglanti} target="_blank" rel="noopener noreferrer"
                     className="text-blue-600 underline">Bu bağlantıya tıkla</a>
                  {' '}— 10 dakika geçerli. Chat ID kopyalaman gerekmiyor.
                </p>
                {/* YEDEK YOL — gerçek kullanımda gerekti.
                    Telegram `?start=` yükünü YALNIZCA "Başlat" düğmesine
                    basıldığında gönderiyor; botu daha önce başlatmış bir
                    kullanıcıda o düğme çıkmıyor ve bağlantı sohbeti açıp
                    hiçbir şey göndermiyor. Kullanıcı "buton çalışmıyor"
                    diyor ama aslında mesaj hiç ulaşmamış oluyor.
                    Aynı mesajı elle göndermek her durumda çalışıyor. */}
                <details>
                  <summary className="cursor-pointer text-slate-500 dark:text-slate-400">
                    Bağlantı bir şey yapmıyorsa (botu daha önce başlattıysan)
                  </summary>
                  <p className="mt-2 text-slate-600 dark:text-slate-300">
                    Aşağıdaki komutu kopyalayıp bot sohbetine yapıştır:
                  </p>
                  <code className="mt-1 block break-all rounded bg-slate-100 p-2
                                   font-mono text-xs dark:bg-slate-800">
                    /start {baglanti.split('start=')[1] ?? ''}
                  </code>
                </details>
              </div>
            )}
            {hata && <p className="text-sm text-red-600">{hata}</p>}
          </div>
        )}
      </section>

      {/* Yıkıcı işlem en altta ve görsel olarak ayrı: yanlışlıkla tıklanmasın.
          Parola YENİDEN sorulur — oturumu çalınmış birinin hesabı silmesini
          zorlaştırır. KVKK/GDPR: kullanıcının verisini sildirme hakkı. */}
      <section className="rounded-lg border border-red-200 bg-white p-4
                          dark:border-red-900/60 dark:bg-slate-900">
        <h2 className="font-medium text-red-700 dark:text-red-400">Hesabı sil</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Hesabın, izlemelerin, setlerin ve bildirimlerin kalıcı olarak silinir.
          Bu işlem geri alınamaz. (Ürünlerin fiyat geçmişi kişisel veri
          olmadığı için sistemde kalır.)
        </p>

        {!silOnay ? (
          <button
            onClick={() => setSilOnay(true)}
            className="mt-3 rounded-md border border-red-300 px-3 py-1.5 text-sm
                       text-red-700 dark:border-red-900 dark:text-red-400"
          >
            Hesabımı silmek istiyorum
          </button>
        ) : (
          <div className="mt-3 space-y-2">
            <input
              type="password" value={silParola} autoComplete="current-password"
              onChange={(e) => setSilParola(e.target.value)}
              placeholder="Onaylamak için parolanı yaz"
              className="w-full max-w-xs rounded-md border border-slate-300 px-3 py-2
                         text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            {silHata && <p className="text-sm text-red-600">{silHata}</p>}
            <div className="flex gap-2">
              <button
                onClick={() => void hesabiSil()}
                disabled={!silParola}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium
                           text-white disabled:opacity-50"
              >
                Kalıcı olarak sil
              </button>
              <button
                onClick={() => { setSilOnay(false); setSilParola(''); setSilHata(null) }}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm
                           dark:border-slate-700"
              >
                Vazgeç
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

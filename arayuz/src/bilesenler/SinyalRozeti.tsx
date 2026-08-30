import type { Sinyal } from '../api/tipler'

/**
 * "Bu iyi bir fiyat mı?" sinyalini panel kartında, detayda, Fırsatlar
 * sayfasında ve set üye listesinde (F1) AYNI YERDEN çizer (BACKLOG A6).
 * Renk paleti `YorumKarti.tsx`
 * ile birebir aynı (dip=yeşil, ucuz=SARI — amber değil, mevcut uygulamanın
 * kendi ayrımı budur, ikisini karıştırmak tutarsızlık yaratırdı).
 *
 * METİN HER ZAMAN VAR: yalnızca renkle anlatmak renk körlüğünde bilgiyi
 * tamamen kaybettirir.
 *
 * `sinyal === null` durumu A7'nin asıl konusu; burada zaten `gecmisGun`
 * prop'u tanımlı olduğundan basit bir gün sayacı gösteriliyor. SABİT BİR
 * PAYDA ("N/7 gün") YOK: backend eşiği `analiz.MIN_GUN` (şu an 5) hiçbir
 * API alanında dışa açılmıyor, frontend'in bunu bilmesinin doğru yolu yok
 * — sabit bir sayı yazmak eşik değişince (ya da BACKLOG'daki gibi yanlış
 * hatırlanınca) sessizce yanlış bilgi vermiş olurdu.
 */

const METIN: Record<Sinyal, string> = {
  dip: '90 günün dibi',
  ucuz: 'ucuz dönem',
  pahali: 'pahalı dönem',
}

const STIL: Record<Sinyal, string> = {
  dip: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  ucuz: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-300',
  pahali: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
}

export default function SinyalRozeti({
  sinyal,
  yuzdelik,
  gecmisGun,
}: {
  sinyal: Sinyal | null
  yuzdelik: number | null
  gecmisGun: number | null
}) {
  if (sinyal === null) {
    return (
      <span
        className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5
                   text-xs font-medium text-slate-500 dark:bg-slate-800
                   dark:text-slate-400"
      >
        geçmiş biriktiriliyor
        {gecmisGun !== null && <span className="tabular-nums">· {gecmisGun} gün</span>}
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs
                  font-medium ${STIL[sinyal]}`}
    >
      {METIN[sinyal]}
      {yuzdelik !== null && <span className="tabular-nums opacity-80">· %{yuzdelik}</span>}
    </span>
  )
}

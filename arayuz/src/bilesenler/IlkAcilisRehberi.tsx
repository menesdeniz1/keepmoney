import { ORNEK_LINK } from '../yardimcilar/rehber'

/**
 * BACKLOG H2 — boş panelde üç adımlık ilk açılış rehberi.
 *
 * NEDEN VAR (A7'nin devamı, gerçek çalıştırmadan): worker üç gün koştu,
 * bir üründe %7,2 düşüş oldu ve hiç uyarı çıkmadı — çünkü sistem yeterli
 * geçmiş olmadan "rekor" demeyi REDDEDİYOR (doğru davranış). Kullanıcı
 * bunu bilmediği için bir hafta sessizlik görüp "kural mı, arıza mı"
 * ayırt edemiyordu. Rehberin ikinci adımı tam olarak bu bekleyişi ÖNCEDEN
 * söylüyor; sessizlik sürprize dönüşmesin.
 *
 * `<ol>` kullanılıyor, `<div>` yığını değil: adımlar SIRALI ve ekran
 * okuyucu "3 öğeden 2." diyerek bunu iletiyor. Numaralar CSS sayacı değil
 * gerçek liste — numarayı görselden okuyamayan kullanıcı da sırayı alır.
 */
export default function IlkAcilisRehberi({
  onOrnekLink,
}: {
  onOrnekLink: (url: string) => void
}) {
  return (
    <section
      aria-labelledby="rehber-basligi"
      className="rounded-lg border border-slate-200 bg-white p-5
                 dark:border-slate-800 dark:bg-slate-900"
    >
      <h2 id="rehber-basligi" className="text-sm font-semibold">
        Üç adımda başla
      </h2>

      <ol className="mt-4 space-y-4">
        <Adim no={1} baslik="Bir ürün linki yapıştır">
          Hangi mağaza olduğu fark etmez — linki yukarıdaki kutuya yapıştır,
          fiyatı düzenli olarak okumaya başlarız.
          <div className="mt-2">
            <button
              type="button"
              onClick={() => onOrnekLink(ORNEK_LINK)}
              className="rounded-md border border-slate-300 px-2.5 py-1 text-xs
                         text-slate-600 hover:bg-slate-50 dark:border-slate-700
                         dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Elimde link yok, örnekle dene
            </button>
          </div>
        </Adim>

        <Adim no={2} baslik="Fiyat hafızası birikirken bekle">
          İlk günlerde kartta <strong>"geçmiş biriktiriliyor"</strong> yazar.
          Bu bir arıza değil: birkaç günlük veriyle "bu iyi bir fiyat" demek
          yanlış olurdu, o yüzden yeterli geçmiş toplanana kadar sinyal
          verilmez.
        </Adim>

        <Adim no={3} baslik="Uyarı kur, haberi bize bırak">
          Ürün sayfasından hedef fiyat, yüzde düşüş ya da "tüm zamanların
          dibi" uyarısı kurabilirsin. Koşul gerçekleşince haber veririz —
          fiyatı sen takip etmezsin.
        </Adim>
      </ol>
    </section>
  )
}

function Adim({
  no,
  baslik,
  children,
}: {
  no: number
  baslik: string
  children: React.ReactNode
}) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden="true"
        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center
                   rounded-full bg-slate-900 text-xs font-semibold text-white
                   dark:bg-white dark:text-slate-900"
      >
        {no}
      </span>
      <div className="min-w-0 text-sm text-slate-600 dark:text-slate-400">
        <span className="font-medium text-slate-900 dark:text-slate-100">
          {baslik}
        </span>
        <div className="mt-0.5">{children}</div>
      </div>
    </li>
  )
}

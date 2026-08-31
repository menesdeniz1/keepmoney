import { Download } from 'lucide-react'

/**
 * CSV indirme bağlantısı (BACKLOG H1).
 *
 * DÜZ BİR `<a>`, `fetch` + `Blob` DEĞİL — üç ayrı sebeple:
 *
 *  1. OTURUM. Token httpOnly çerezde duruyor (istemci.ts); aynı kaynağa
 *     giden bir indirmede çerez zaten gider. Blob yolunda `fetch`
 *     `credentials: 'include'` ile tekrar kurulurdu — kazanç yok.
 *  2. DOSYA ADI. Sunucu adı `Content-Disposition` ile veriyor
 *     (`keepmoney-<ürün>-gecmis-<tarih>.csv`). Blob yolunda o başlığı
 *     JS'in ayrıştırıp adı KENDİSİNİN kurması gerekirdi: aynı bilgi iki
 *     yerde, ikisi ayrı düştüğü gün sessizce yanlış ad.
 *  3. CSP. Uygulamanın politikası `default-src 'self'` (api/koruma.py) ve
 *     `blob:` hiçbir yönergede izinli değil.
 *
 * `download` niteliği DEĞERSİZ bırakıldı: değer verilseydi sunucunun
 * verdiği adı EZERDİ. Boş bırakılınca tarayıcı `Content-Disposition`daki
 * adı kullanır.
 */
export default function CsvIndir({
  adres,
  children,
  baslik,
}: {
  adres: string
  children: React.ReactNode
  baslik?: string
}) {
  return (
    <a
      href={adres}
      download
      title={baslik}
      className="inline-flex items-center gap-1.5 rounded-md border
                 border-slate-300 px-3 py-1.5 text-sm text-slate-600
                 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300
                 dark:hover:bg-slate-800"
    >
      <Download size={15} aria-hidden="true" />
      {children}
    </a>
  )
}

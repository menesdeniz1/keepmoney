import { Plus, Search } from 'lucide-react'

import { ApiHatasi } from '../api/istemci'
import { useKaynakEkle, useKaynakOnerileri } from '../api/kancalar'

/**
 * "Bu ürün başka nerede satılıyor?" — çoklu kaynak kurgusunun giriş kapısı.
 *
 * ÜÇ SEBEPLE DEĞERLİ:
 *  1. Sistem her turda tüm kaynakları okuyup EN UCUZUNU bildirir.
 *  2. Bir mağaza bot duvarına takılsa bile ürün okunmaya devam eder —
 *     ölçümde Hepsiburada ve n11 gerçek tarayıcıyla bile 403 dönüyordu,
 *     aynı ürünün fiyatı toplayıcıda sorunsuz okunuyor.
 *  3. Toplayıcı sayfası "kaç satıcı var, ikincisi kaça" bilgisini de getirir;
 *     bu, fiyat geçmişi henüz oluşmamış üründe tek uyarı işaretidir.
 *
 * ARAMA KENDİLİĞİNDEN ÇALIŞMAZ. Dış siteye çıkıyor ve gerekirse gerçek
 * tarayıcı açılıyor (~1-8 sn). Sayfa her açılışında tetiklenmesi hem
 * kullanıcıyı bekletir hem toplayıcıya gereksiz yük bindirir.
 *
 * SEÇİMİ KULLANICI YAPAR. "RTX 5070 Ti Prime" ile "Prime OC" ayrı ürünler;
 * otomatik eşleştirme yanlış ürünün fiyatını bu ürünün geçmişine yazardı —
 * grafiğe işleyen, geri alınamayan, sessiz bir hata.
 */
export default function KaynakOnerileri({ izlemeId }: { izlemeId: number }) {
  const oneriler = useKaynakOnerileri(izlemeId)
  const ekle = useKaynakEkle(izlemeId)

  return (
    <div className="mt-4 border-t border-slate-200 pt-3 dark:border-slate-800">
      <button
        onClick={() => void oneriler.refetch()}
        disabled={oneriler.isFetching}
        className="inline-flex items-center gap-1.5 text-sm text-slate-600
                   hover:underline disabled:opacity-50 dark:text-slate-400"
      >
        <Search size={14} />
        {oneriler.isFetching ? 'Aranıyor…' : 'Başka mağazalarda ara'}
      </button>

      {oneriler.isError && (
        <p role="alert" className="mt-2 text-xs text-slate-500">
          {/*
            Sunucunun söylediği sebep varsa ONU göster. Tek bir "arama
            yapılamadı" metni, "ürün adı henüz okunmadı" gibi geçici ve
            KULLANICININ ÇÖZEBİLECEĞİ durumları kalıcı arıza gibi
            gösteriyordu — kullanıcı özelliğin bozuk olduğunu sanır.
          */}
          {oneriler.error instanceof ApiHatasi && oneriler.error.durum === 409
            ? oneriler.error.message
            : 'Arama şu an yapılamadı. Mağaza linkini elle de ekleyebilirsin.'}
        </p>
      )}

      {oneriler.data && oneriler.data.length === 0 && (
        <p className="mt-2 text-xs text-slate-500">
          Bu ürün için eşleşme bulunamadı.
        </p>
      )}

      {oneriler.data && oneriler.data.length > 0 && (
        <>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            Doğru ürünü sen seç — adları benzeyen farklı modeller olabilir ve
            yanlış seçim fiyat geçmişini bozar.
          </p>
          <ul className="mt-2 space-y-1.5">
            {oneriler.data.map((o) => (
              <li key={o.url} className="flex items-center justify-between gap-3">
                <a
                  href={o.url}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
                  className="min-w-0 truncate text-sm hover:underline"
                >
                  {o.ad}
                </a>
                <button
                  onClick={() => ekle.mutate(o.url)}
                  disabled={ekle.isPending}
                  aria-label={`${o.ad} kaynağını ekle`}
                  className="inline-flex shrink-0 items-center gap-1 rounded-md
                             border border-slate-300 px-2 py-1 text-xs
                             disabled:opacity-50 dark:border-slate-700"
                >
                  <Plus size={12} /> Ekle
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {ekle.isError && (
        <p role="alert" className="mt-2 text-xs text-red-600 dark:text-red-400">
          {ekle.error.message}
        </p>
      )}
    </div>
  )
}

import { Link } from 'react-router-dom'

import { Bolum, HukukiSayfa } from './Gizlilik'

/**
 * Kullanım koşulları — OTURUM İSTEMEZ (bkz. `Gizlilik.tsx`).
 *
 * Buradaki sınırlar UYDURULMADI, koddan alındı: kota
 * `ayarlar.kullanici_basina_izleme_limiti`, sinyal eşiği `analiz.MIN_GUN`,
 * "fiyat garantisi yok" ifadesi de `karar.py`nin koruma katmanının gerçek
 * davranışıdır (şüpheli okuma reddedilir, yine de mağaza fiyatı esastır).
 *
 * HUKUKİ YETERLİLİK AYRI KONUDUR — metin sistemin ne yaptığını doğru
 * anlatır; sözleşme hukuku açısından yeterliliği ayrıca değerlendirilmeli.
 */
export default function Kosullar() {
  return (
    <HukukiSayfa baslik="Kullanım Koşulları">
      <Bolum baslik="Servis ne yapar">
        <p>
          KeepMoney, senin verdiğin ürün linklerindeki fiyatları düzenli
          olarak okur, geçmişini biriktirir ve koyduğun koşul gerçekleştiğinde
          sana haber verir. Ürün satmaz, satışa aracılık etmez ve ödeme
          almaz.
        </p>
      </Bolum>

      <Bolum baslik="Fiyat bilgisi garanti değildir">
        <p>
          Fiyatlar mağaza sayfalarından otomatik okunur. Mağaza sayfasını
          değiştirebilir, yanlış fiyat yayınlayabilir ya da fiyat sen
          bakarken değişebilir. Sistem şüpheli okumaları reddeder ve
          okuyamadığı kaynağı sana bildirir, ama{' '}
          <strong>bağlayıcı olan mağazanın kendi sayfasındaki fiyattır</strong>
          . Satın almadan önce mağaza sayfasını kontrol et.
        </p>
      </Bolum>

      <Bolum baslik="Bildirimler gecikebilir">
        <p>
          Tarama periyodiktir; fiyat değişimiyle bildirim arasında zaman
          geçebilir. Ayrıca sinyal üretilebilmesi için ürünün birkaç günlük
          fiyat geçmişinin birikmesi gerekir — yeni eklenen üründe "geçmiş
          biriktiriliyor" yazması normaldir. Kaçırılan bir fırsattan
          sorumluluk kabul edilmez.
        </p>
      </Bolum>

      <Bolum baslik="Hesabın ve kullanım sınırları">
        <ul className="list-disc space-y-1 pl-5">
          <li>Hesap başına izlenebilecek ürün sayısı sınırlıdır.</li>
          <li>
            Parolanın güvenliği senin sorumluluğundadır; paylaşılan hesap
            kullanma.
          </li>
          <li>
            Servisi otomatik araçlarla aşırı yüklemek, başkasının verisine
            erişmeye çalışmak veya mağazaları bizim üzerimizden taciz etmek
            yasaktır.
          </li>
          <li>
            Hesabını istediğin an{' '}
            <Link to="/gizlilik" className="underline">
              silebilirsin
            </Link>
            .
          </li>
        </ul>
      </Bolum>

      <Bolum baslik="Mağaza içerikleri">
        <p>
          Ürün adları, görselleri ve fiyatları ilgili mağazalara aittir.
          KeepMoney bu içerikleri yalnızca senin izlemek üzere eklediğin
          sayfalardan, fiyat takibi amacıyla okur ve mağazaların{' '}
          <code>robots.txt</code> beyanlarına uyar.
        </p>
      </Bolum>

      <Bolum baslik="Servisin sürekliliği">
        <p>
          Servis "olduğu gibi" sunulur. Bakım, mağaza değişiklikleri veya
          teknik arızalar nedeniyle kesinti olabilir. Fiyat geçmişin düzenli
          olarak yedeklenir, ancak veri kaybına karşı mutlak garanti
          verilmez.
        </p>
      </Bolum>
    </HukukiSayfa>
  )
}

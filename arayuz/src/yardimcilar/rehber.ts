/**
 * BACKLOG H2 — Panel ilk açılış rehberi. Saf mantık; `Panel.tsx` kullanır.
 *
 * Depolama kalıbı `gorunum.ts`/`siralama.ts`/`grafikAraligi.ts` ile aynı
 * (localStorage + try/catch). SUNUCUYA YAZILMIYOR ve bu bilinçli: rehberi
 * görüp görmediği bir TERCİH değil, o tarayıcıdaki ilk deneyimin durumu.
 * Kalıcı hâle getirmek `users` tablosuna göç demekti — H2 "arayüz · 2
 * saat" olarak tanımlanmış bir iş ve şema değişikliği içermiyor. Bedeli
 * dürüstçe şu: kullanıcı ikinci bir tarayıcıdan HİÇ ÜRÜNÜ YOKKEN girerse
 * rehberi yeniden görür — ki o durumda rehber zaten DOĞRU olur.
 */

export const REHBER_ANAHTARI = 'km:rehber-bitti'

/**
 * Örnek link — tıklayınca URL kutusuna dolar.
 *
 * TEK YERDE: değiştirmek gerektiğinde aranacak başka nokta olmasın.
 * Seçim ölçütü "popüler ürün" DEĞİL, "kuralı tanımlı mağaza": host'un
 * `keepmoney/siteler/` altında bir yaml'ı olmalı ki fiyat gerçekten
 * okunabilsin. Bunu `tests/test_siteler.py` zorluyor — burayı kuralı
 * olmayan bir mağazaya çevirirsen test kırılır.
 *
 * BİLİNEN KIRILGANLIK: ürün mağazadan kaldırılırsa vatanbilgisayar
 * YUMUŞAK 404 döndürüyor — kaldırılmış ürüne HTTP 200 ve "404 - File or
 * directory not found" başlıklı sayfa (ÖLÇÜLDÜ, bkz. docs/DEVIR.md §5.6).
 * Yani link öldüğünde sistem bunu hemen anlamaz; yeni kullanıcının ilk
 * ürünü sessizce fiyatsız kalır. Rehber bu yüzden örneği "deneyecek bir
 * şeyin yoksa" diye sunuyor, tek yol olarak değil — ve bu satır bayatlarsa
 * DEĞİŞTİRİLECEK yer burasıdır.
 */
export const ORNEK_LINK =
  'https://www.vatanbilgisayar.com/hyperx-cloud-iii-s-kulaklik.html'

export function rehberBaslangici(): boolean {
  try {
    return localStorage.getItem(REHBER_ANAHTARI) === '1'
  } catch {
    // Gizli sekme / depolama kapalı — rehber gösterilir. Yanlış tarafa
    // düşmek gerekiyorsa "gereksiz yere gösterildi" tarafı, "yeni
    // kullanıcı hiç görmedi" tarafından iyidir.
    return false
  }
}

export function rehberiBitir(): void {
  try {
    localStorage.setItem(REHBER_ANAHTARI, '1')
  } catch {
    // Depolama kapalı — rehber bu tarayıcıda tekrar görünebilir. Kabul
    // edilebilir: liste doluyken zaten gösterilmiyor.
  }
}

/**
 * BACKLOG H2 kabul ölçütü: "ilk ürün eklenince rehber kaybolur, GERİ
 * GELMEZ".
 *
 * İki ayrı koşul, ikisi de gerekli:
 *  • `bitti` — kullanıcının BİR KEZ ürünü olmuş. Sonradan hepsini silse
 *    bile rehber geri gelmemeli; yalnızca `izlemeSayisi === 0` bakan bir
 *    kontrol tam burada yanılırdı.
 *  • `izlemeSayisi === undefined` — liste HENÜZ YÜKLENMEDİ. Bu durumda
 *    rehber ÇİZİLMEZ: aksi hâlde ürünü olan kullanıcı her sayfa
 *    açılışında rehberin bir an parlayıp kaybolduğunu görürdü.
 */
export function rehberGorunurMu(
  bitti: boolean,
  izlemeSayisi: number | undefined,
): boolean {
  if (bitti) return false
  if (izlemeSayisi === undefined) return false
  return izlemeSayisi === 0
}

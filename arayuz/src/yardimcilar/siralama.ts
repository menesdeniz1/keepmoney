/**
 * BACKLOG C1 — panel liste sıralaması. Saf mantık, `ListeKontrol.tsx` ve
 * `Panel.tsx` bunu kullanır. Ayrı dosyada olması `grafikAraligi.ts` ile
 * aynı gerekçe: recharts YOK burada ama yine de saf mantık / UI ayrımı
 * testi kolaylaştırıyor ve `react-refresh/only-export-components`
 * uyarısından kaçınıyor.
 */
import type { Izleme } from '../api/tipler'
import { kivilcimDegisimiHesapla } from './kivilcimDegisim'

export type SiralamaSecenegi =
  | 'firsat'
  | 'fiyat_artan'
  | 'fiyat_azalan'
  | 'hedef_yakinlik'
  | 'son_degisim'
  | 'ad'
  | 'eklenme'

export const SIRALAMA_SECENEKLERI: { deger: SiralamaSecenegi; etiket: string }[] = [
  { deger: 'firsat', etiket: 'En iyi fırsat' },
  { deger: 'fiyat_artan', etiket: 'Fiyat: düşükten yükseğe' },
  { deger: 'fiyat_azalan', etiket: 'Fiyat: yüksekten düşüğe' },
  { deger: 'hedef_yakinlik', etiket: 'Hedefe yakınlık' },
  { deger: 'son_degisim', etiket: 'Son değişim' },
  { deger: 'ad', etiket: 'Ad (A-Z)' },
  { deger: 'eklenme', etiket: 'Son eklenen' },
]

export const SIRALAMA_ANAHTARI = 'km:panel-siralama'
// "En iyi fırsat" varsayılan — panel açıldığında en yukarıda alınacak
// şey (en ucuz dönemdeki ürün) dursun, sabit "eklenme sırası" değil.
export const SIRALAMA_VARSAYILAN: SiralamaSecenegi = 'firsat'

export function siralamaGecerliMi(deger: string | null): deger is SiralamaSecenegi {
  return SIRALAMA_SECENEKLERI.some((s) => s.deger === deger)
}

export function baslangicSiralamasi(): SiralamaSecenegi {
  try {
    const kayitli = localStorage.getItem(SIRALAMA_ANAHTARI)
    return siralamaGecerliMi(kayitli) ? kayitli : SIRALAMA_VARSAYILAN
  } catch {
    // Gizli sekme / depolama kapalı — sessizce varsayılana düş.
    return SIRALAMA_VARSAYILAN
  }
}

/**
 * `deger` fonksiyonu her izleme için bir sayı ya da `null` üretir. `null`
 * HER ZAMAN sona gider — kabul ölçütü "null'lar sonda", sinyalsiz/
 * hedefsiz/kıvılcımsız ürünler listenin başını işgal etmesin diye.
 * Girdi dizisi DEĞİŞTİRİLMEZ (`sort` kopya üzerinde çalışır) — React
 * state'i doğrudan mutasyona uğratmak render'ı bozardı.
 */
function sayiylaSirala(
  izlemeler: Izleme[],
  deger: (i: Izleme) => number | null,
  yon: 'artan' | 'azalan',
): Izleme[] {
  return [...izlemeler].sort((a, b) => {
    const va = deger(a)
    const vb = deger(b)
    if (va === null && vb === null) return 0
    if (va === null) return 1
    if (vb === null) return -1
    return yon === 'artan' ? va - vb : vb - va
  })
}

export function izlemeleriSirala(
  izlemeler: Izleme[],
  secenek: SiralamaSecenegi,
  kivilcimlar: Record<string, number[]> | undefined,
): Izleme[] {
  switch (secenek) {
    case 'firsat':
      // Yüzdelik yüksek = "günlerin çoğundan ucuz" (bkz. analiz.py) —
      // en büyükten en küçüğe.
      return sayiylaSirala(izlemeler, (i) => i.urun.yuzdelik, 'azalan')

    case 'fiyat_artan':
      return sayiylaSirala(izlemeler, (i) => i.urun.guncel_fiyat, 'artan')

    case 'fiyat_azalan':
      return sayiylaSirala(izlemeler, (i) => i.urun.guncel_fiyat, 'azalan')

    case 'hedef_yakinlik':
      // fark = guncel - hedef; negatifse zaten hedefte. En küçük fark
      // (hedefte olanlar dahil) en üste — hedefi olmayanlar null, sona.
      return sayiylaSirala(
        izlemeler,
        (i) =>
          i.hedef_fiyat != null && i.urun.guncel_fiyat != null
            ? i.urun.guncel_fiyat - i.hedef_fiyat
            : null,
        'artan',
      )

    case 'son_degisim':
      // En büyük DÜŞÜŞ (en negatif % değişim) en üstte — kullanıcı için
      // en ilginç olan bu. Kıvılcım verisi henüz gelmediyse (A8'in
      // "ayrı ve gecikmeli" tasarımı) tüm değerler null'dur ve sıralama
      // sessizce orijinal sırada kalır — bu bir hata değil, veri henüz
      // yok demektir.
      return sayiylaSirala(
        izlemeler,
        (i) => kivilcimDegisimiHesapla(kivilcimlar?.[String(i.id)]),
        'artan',
      )

    case 'eklenme':
      // `Izleme` API yanıtı `created_at` taşımıyor; `id` otomatik artan
      // olduğu için "en son eklenen" için güvenilir bir vekil — büyük id
      // = sonra eklendi.
      return sayiylaSirala(izlemeler, (i) => i.id, 'azalan')

    case 'ad':
      // TÜRKÇE SIRALAMA: `localeCompare('tr')` şart — düz JS `<`/`>`
      // "İ"/"ı" gibi Türkçe'ye özgü büyük/küçük harf kurallarını yanlış
      // sıralar (örn. "İstanbul" ile "Izmir" ASCII sırasına göre yanlış
      // yer değiştirir).
      return [...izlemeler].sort((a, b) =>
        a.urun.ad.localeCompare(b.urun.ad, 'tr'),
      )

    default: {
      const kontrolEdilmemis: never = secenek
      throw new Error(`Bilinmeyen sıralama seçeneği: ${String(kontrolEdilmemis)}`)
    }
  }
}

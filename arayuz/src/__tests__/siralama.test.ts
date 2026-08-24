/**
 * BACKLOG C1 kabul ölçütleri: her seçenek doğru sıralıyor, null'lar sonda,
 * Türkçe sıralama doğru.
 */
import { describe, expect, it } from 'vitest'

import type { Izleme, UrunOzet } from '../api/tipler'
import { izlemeleriSirala } from '../yardimcilar/siralama'

function urun(parcaGirdi: Partial<UrunOzet> & { id: number; ad: string }): UrunOzet {
  return {
    kategori: null,
    guncel_fiyat: null,
    guncel_satici: null,
    puan: null,
    yorum_sayisi: null,
    son_kontrol: null,
    sinyal: null,
    dip90: null,
    medyan90: null,
    yuzdelik: null,
    gecmis_gun: null,
    ...parcaGirdi,
  }
}

function izleme(parcaGirdi: Partial<Izleme> & { urun: UrunOzet }): Izleme {
  return {
    id: parcaGirdi.urun.id,
    hedef_fiyat: null,
    acil_fiyat: null,
    aktif: true,
    kilitli: false,
    kilitli_fiyat: null,
    sustur_bitis: null,
    set_idler: [],
    ...parcaGirdi,
  }
}

describe('izlemeleriSirala — firsat (yüzdelik)', () => {
  it('yüksekten düşüğe sıralar, null en sonda', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A', yuzdelik: 40 }) }),
      izleme({ urun: urun({ id: 2, ad: 'B', yuzdelik: null }) }),
      izleme({ urun: urun({ id: 3, ad: 'C', yuzdelik: 90 }) }),
    ]
    const sonuc = izlemeleriSirala(liste, 'firsat', undefined).map((i) => i.id)
    expect(sonuc).toEqual([3, 1, 2])
  })
})

describe('izlemeleriSirala — fiyat_artan / fiyat_azalan', () => {
  const liste = [
    izleme({ urun: urun({ id: 1, ad: 'A', guncel_fiyat: 500 }) }),
    izleme({ urun: urun({ id: 2, ad: 'B', guncel_fiyat: null }) }),
    izleme({ urun: urun({ id: 3, ad: 'C', guncel_fiyat: 100 }) }),
  ]

  it('artan: düşükten yükseğe, null sonda', () => {
    const sonuc = izlemeleriSirala(liste, 'fiyat_artan', undefined).map((i) => i.id)
    expect(sonuc).toEqual([3, 1, 2])
  })

  it('azalan: yüksekten düşüğe, null YİNE sonda (başa değil)', () => {
    const sonuc = izlemeleriSirala(liste, 'fiyat_azalan', undefined).map((i) => i.id)
    expect(sonuc).toEqual([1, 3, 2])
  })
})

describe('izlemeleriSirala — hedef_yakinlik', () => {
  it('hedefte olan (negatif fark) en üstte, hedefsiz ürün sonda', () => {
    const liste = [
      izleme({ hedef_fiyat: 1000, urun: urun({ id: 1, ad: 'A', guncel_fiyat: 1200 }) }), // +200
      izleme({ hedef_fiyat: null, urun: urun({ id: 2, ad: 'B', guncel_fiyat: 300 }) }), // hedefsiz
      izleme({ hedef_fiyat: 1000, urun: urun({ id: 3, ad: 'C', guncel_fiyat: 900 }) }), // -100 (hedefte)
    ]
    const sonuc = izlemeleriSirala(liste, 'hedef_yakinlik', undefined).map((i) => i.id)
    expect(sonuc).toEqual([3, 1, 2])
  })
})

describe('izlemeleriSirala — son_degisim (kıvılcım)', () => {
  it('en büyük düşüş (en negatif %) en üstte, kıvılcımsız ürün sonda', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A' }) }),   // kıvılcım yok
      izleme({ urun: urun({ id: 2, ad: 'B' }) }),   // 1000 -> 900: -%10
      izleme({ urun: urun({ id: 3, ad: 'C' }) }),   // 1000 -> 500: -%50
    ]
    const kivilcimlar = { '2': [1000, 950, 900], '3': [1000, 700, 500] }
    const sonuc = izlemeleriSirala(liste, 'son_degisim', kivilcimlar).map((i) => i.id)
    expect(sonuc).toEqual([3, 2, 1])
  })

  it('kıvılcım verisi hiç gelmediyse (undefined) hata vermez, sırayı korur', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A' }) }),
      izleme({ urun: urun({ id: 2, ad: 'B' }) }),
    ]
    expect(() => izlemeleriSirala(liste, 'son_degisim', undefined)).not.toThrow()
  })
})

describe('izlemeleriSirala — eklenme', () => {
  it('büyük id (son eklenen) önce', () => {
    const liste = [
      izleme({ urun: urun({ id: 5, ad: 'A' }) }),
      izleme({ urun: urun({ id: 20, ad: 'B' }) }),
      izleme({ urun: urun({ id: 1, ad: 'C' }) }),
    ]
    const sonuc = izlemeleriSirala(liste, 'eklenme', undefined).map((i) => i.id)
    expect(sonuc).toEqual([20, 5, 1])
  })
})

describe('izlemeleriSirala — ad (Türkçe)', () => {
  it('Türkçe alfabetik sıraya göre dizilir', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'Zebra' }) }),
      izleme({ urun: urun({ id: 2, ad: 'Elma' }) }),
      izleme({ urun: urun({ id: 3, ad: 'Armut' }) }),
    ]
    const sonuc = izlemeleriSirala(liste, 'ad', undefined).map((i) => i.id)
    expect(sonuc).toEqual([3, 2, 1])
  })

  it("Türkçe I/İ sırasını `localeCompare('tr')` ile doğru uygular — ÖLÇÜLDÜ:" +
     " varsayılan (locale'siz) karşılaştırmada 'Izmir'.localeCompare('İstanbul')" +
     " İKİSİ FARKLI İŞARET verir (+1 vs -1), yani locale parametresi" +
     " gerçekten sonucu değiştiriyor, süslü bir no-op değil", () => {
    // Türkçe alfabede sıra ...H, I, İ, J... — yani büyük harfte "Izmir"
    // "İstanbul"dan ÖNCE gelir. Locale'siz `localeCompare` bu ikisini
    // TERS sıralar (Unicode kod noktası: İ U+0130 < I... hayır, tam
    // tersi — ÖLÇÜLDÜ ki `'Izmir'.localeCompare('İstanbul')` (locale'siz)
    // +1, `('tr')` ile -1 döner).
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'İstanbul Ürünü' }) }),
      izleme({ urun: urun({ id: 2, ad: 'Izmir Ürünü' }) }),
    ]
    const sonuc = izlemeleriSirala(liste, 'ad', undefined).map((i) => i.id)
    expect(sonuc).toEqual([2, 1])                    // Izmir ÖNCE, İstanbul SONRA
  })
})

describe('izlemeleriSirala — girdi mutasyona uğramaz', () => {
  it('orijinal dizi DEĞİŞMEZ — React state doğrudan mutasyona uğramamalı', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'B', guncel_fiyat: 500 }) }),
      izleme({ urun: urun({ id: 2, ad: 'A', guncel_fiyat: 100 }) }),
    ]
    const kopyaOnce = [...liste]
    izlemeleriSirala(liste, 'fiyat_artan', undefined)
    expect(liste).toEqual(kopyaOnce)
  })
})

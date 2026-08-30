/**
 * BACKLOG C2 kabul ölçütleri: iki süzgeç birlikte VE mantığıyla çalışıyor,
 * çip listesi/kaldırma doğru, "hepsini temizle" öncesi boşluk tespiti doğru.
 */
import { describe, expect, it } from 'vitest'

import type { Izleme, UrunOzet } from '../api/tipler'
import {
  aktifCipler,
  izlemeleriSuz,
  suzgecBosMu,
  SUZGEC_BOS,
  type SuzgecDurumu,
} from '../yardimcilar/suzme'

function urun(parcaGirdi: Partial<UrunOzet> & { id: number; ad: string }): UrunOzet {
  return {
    kategori: null,
    guncel_fiyat: 100,
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
    dusus_yuzdesi: null,
    yeniden_kur_gun: null,
    son_bildirim_ts: null,
    ...parcaGirdi,
  }
}

// `sustur_bitis` backend'den 'Z' EKİ OLMADAN geliyor — `suzme.ts` bunu
// UTC varsayıp kendi 'Z' ekliyor (IzlemeKarti.tsx'teki aynı mantık).
function isoZsiz(tarih: Date): string {
  return tarih.toISOString().slice(0, -1)
}

describe('izlemeleriSuz — arama', () => {
  const liste = [
    izleme({ urun: urun({ id: 1, ad: 'Kablosuz Kulaklık' }) }),
    izleme({ urun: urun({ id: 2, ad: 'Mekanik Klavye' }) }),
  ]

  it('ada göre Türkçe küçültmeyle süzer', () => {
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, arama: 'kulaklık' })
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })

  it('boş arama hiçbir şeyi elemez', () => {
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, arama: '   ' })
    expect(sonuc).toHaveLength(2)
  })
})

describe('izlemeleriSuz — sinyal', () => {
  const liste = [
    izleme({ urun: urun({ id: 1, ad: 'A', sinyal: 'dip' }) }),
    izleme({ urun: urun({ id: 2, ad: 'B', sinyal: 'ucuz' }) }),
    izleme({ urun: urun({ id: 3, ad: 'C', sinyal: 'pahali' }) }),
    izleme({ urun: urun({ id: 4, ad: 'D', sinyal: null }) }),
  ]

  it("'dip': yalnızca dip sinyali", () => {
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, sinyal: 'dip' })
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })

  it("'dip_ucuz': dip VEYA ucuz, pahalı/sinyalsiz hariç", () => {
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, sinyal: 'dip_ucuz' })
    expect(sonuc.map((i) => i.id)).toEqual([1, 2])
  })

  it("'hepsi': hiçbir şey elenmez", () => {
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, sinyal: 'hepsi' })
    expect(sonuc).toHaveLength(4)
  })
})

describe('izlemeleriSuz — set', () => {
  it('yalnızca verilen set idsine üye olanları bırakır', () => {
    const liste = [
      izleme({ set_idler: [7], urun: urun({ id: 1, ad: 'A' }) }),
      izleme({ set_idler: [9], urun: urun({ id: 2, ad: 'B' }) }),
      izleme({ set_idler: [7, 9], urun: urun({ id: 3, ad: 'C' }) }),
    ]
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, setId: 7 })
    expect(sonuc.map((i) => i.id)).toEqual([1, 3])
  })
})

describe('izlemeleriSuz — mağaza', () => {
  it('yalnızca verilen mağazayı bırakır', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A', guncel_satici: 'Trendyol' }) }),
      izleme({ urun: urun({ id: 2, ad: 'B', guncel_satici: 'Hepsiburada' }) }),
    ]
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, magaza: 'Trendyol' })
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })
})

describe('izlemeleriSuz — durum', () => {
  it("'hedefli': yalnızca hedef_fiyat != null", () => {
    const liste = [
      izleme({ hedef_fiyat: 1000, urun: urun({ id: 1, ad: 'A' }) }),
      izleme({ hedef_fiyat: null, urun: urun({ id: 2, ad: 'B' }) }),
    ]
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, durumlar: ['hedefli'] })
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })

  it("'susturulmus': sustur_bitis GELECEKTE olmalı — GEÇMİŞ tarih eşleşmez", () => {
    const gelecek = isoZsiz(new Date(Date.now() + 86_400_000))
    const gecmis = isoZsiz(new Date(Date.now() - 86_400_000))
    const liste = [
      izleme({ sustur_bitis: gelecek, urun: urun({ id: 1, ad: 'A' }) }),
      izleme({ sustur_bitis: gecmis, urun: urun({ id: 2, ad: 'B' }) }),
      izleme({ sustur_bitis: null, urun: urun({ id: 3, ad: 'C' }) }),
    ]
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, durumlar: ['susturulmus'] })
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })

  it("'duraklatilmis': yalnızca aktif=false", () => {
    const liste = [
      izleme({ aktif: false, urun: urun({ id: 1, ad: 'A' }) }),
      izleme({ aktif: true, urun: urun({ id: 2, ad: 'B' }) }),
    ]
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, durumlar: ['duraklatilmis'] })
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })

  it("'okunamayan': yalnızca guncel_fiyat null", () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A', guncel_fiyat: null }) }),
      izleme({ urun: urun({ id: 2, ad: 'B', guncel_fiyat: 500 }) }),
    ]
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, durumlar: ['okunamayan'] })
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })

  it('BİRDEN ÇOK durum etiketi VEYA mantığıyla birleşir (kart aynı anda birden çok rozet gösterebiliyor)', () => {
    const liste = [
      izleme({ aktif: false, hedef_fiyat: null, urun: urun({ id: 1, ad: 'A' }) }), // yalnızca duraklatılmış
      izleme({ aktif: true, hedef_fiyat: 1000, urun: urun({ id: 2, ad: 'B' }) }), // yalnızca hedefli
      izleme({ aktif: true, hedef_fiyat: null, urun: urun({ id: 3, ad: 'C' }) }), // hiçbiri
    ]
    const sonuc = izlemeleriSuz(liste, {
      ...SUZGEC_BOS,
      durumlar: ['duraklatilmis', 'hedefli'],
    })
    expect(sonuc.map((i) => i.id)).toEqual([1, 2])
  })
})

describe('izlemeleriSuz — kategoriler arası VE mantığı', () => {
  it('sinyal + arama birlikte uygulanır, ikisine de uyanı bırakır', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'Kablosuz Kulaklık', sinyal: 'dip' }) }),
      izleme({ urun: urun({ id: 2, ad: 'Kablosuz Klavye', sinyal: 'pahali' }) }),
      izleme({ urun: urun({ id: 3, ad: 'Mekanik Klavye', sinyal: 'dip' }) }),
    ]
    const sonuc = izlemeleriSuz(liste, { ...SUZGEC_BOS, sinyal: 'dip', arama: 'kablosuz' })
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })

  it('set + durum birlikte uygulanır', () => {
    const liste = [
      izleme({ set_idler: [5], aktif: false, urun: urun({ id: 1, ad: 'A' }) }),
      izleme({ set_idler: [5], aktif: true, urun: urun({ id: 2, ad: 'B' }) }),
      izleme({ set_idler: [6], aktif: false, urun: urun({ id: 3, ad: 'C' }) }),
    ]
    const suzgec: SuzgecDurumu = { ...SUZGEC_BOS, setId: 5, durumlar: ['duraklatilmis'] }
    const sonuc = izlemeleriSuz(liste, suzgec)
    expect(sonuc.map((i) => i.id)).toEqual([1])
  })
})

describe('suzgecBosMu', () => {
  it('varsayılan süzgeç boştur', () => {
    expect(suzgecBosMu(SUZGEC_BOS)).toBe(true)
  })

  it('herhangi bir alan doluysa boş değildir', () => {
    expect(suzgecBosMu({ ...SUZGEC_BOS, arama: 'x' })).toBe(false)
    expect(suzgecBosMu({ ...SUZGEC_BOS, sinyal: 'dip' })).toBe(false)
    expect(suzgecBosMu({ ...SUZGEC_BOS, setId: 1 })).toBe(false)
    expect(suzgecBosMu({ ...SUZGEC_BOS, magaza: 'Trendyol' })).toBe(false)
    expect(suzgecBosMu({ ...SUZGEC_BOS, durumlar: ['hedefli'] })).toBe(false)
  })
})

describe('aktifCipler', () => {
  it('her dolu alan için bir çip üretir, set adını çözümleyerek', () => {
    const suzgec: SuzgecDurumu = {
      arama: 'kulaklık',
      sinyal: 'dip',
      setId: 5,
      magaza: 'Trendyol',
      durumlar: ['hedefli', 'duraklatilmis'],
    }
    const cipler = aktifCipler(suzgec, (id) => (id === 5 ? 'PC Toplama' : undefined))
    expect(cipler.map((c) => c.etiket)).toEqual([
      '"kulaklık"',
      'Yalnızca dip',
      'PC Toplama',
      'Trendyol',
      'Hedefi olanlar',
      'Duraklatılmışlar',
    ])
  })

  it('boş süzgeç için hiç çip üretmez', () => {
    expect(aktifCipler(SUZGEC_BOS, () => undefined)).toEqual([])
  })

  it('bir çibi kaldırmak SADECE o alanı sıfırlar, diğerlerini korur', () => {
    const suzgec: SuzgecDurumu = { ...SUZGEC_BOS, sinyal: 'dip', magaza: 'Trendyol' }
    const cipler = aktifCipler(suzgec, () => undefined)
    const sinyalCipi = cipler.find((c) => c.anahtar === 'sinyal')
    expect(sinyalCipi).toBeDefined()
    const sonraki = sinyalCipi!.kaldir(suzgec)
    expect(sonraki).toEqual({ ...SUZGEC_BOS, magaza: 'Trendyol' })
  })

  it('durum çiplerinden birini kaldırmak yalnızca o etiketi listeden çıkarır', () => {
    const suzgec: SuzgecDurumu = { ...SUZGEC_BOS, durumlar: ['hedefli', 'duraklatilmis'] }
    const cipler = aktifCipler(suzgec, () => undefined)
    const hedefliCipi = cipler.find((c) => c.anahtar === 'durum-hedefli')!
    const sonraki = hedefliCipi.kaldir(suzgec)
    expect(sonraki.durumlar).toEqual(['duraklatilmis'])
  })
})

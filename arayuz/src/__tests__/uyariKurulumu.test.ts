/**
 * BACKLOG E3 kabul ölçütleri: önizleme doğru hesaplanıyor, geçmiş
 * yeterlilik kontrolü doğru, özet cümlesi seçili kuralları doğru anlatıyor.
 */
import { describe, expect, it } from 'vitest'

import {
  ozetCumlesi,
  taslakBaslangici,
  taslaktanPatchGovdesi,
  yuzdeKullanilabilirMi,
  yuzdeOnizlemesi,
  YUZDE_ESIGI_GUN,
  type UyariTaslagi,
} from '../yardimcilar/uyariKurulumu'

describe('yuzdeOnizlemesi', () => {
  it('medyan * (1 - yüzde/100) hesaplar', () => {
    expect(yuzdeOnizlemesi(1000, 15)).toBeCloseTo(850)
  })

  it('BACKLOG örneği: medyan 2857 civarı, %15 → yaklaşık 2428', () => {
    expect(yuzdeOnizlemesi(2857, 15)).toBeCloseTo(2428.45, 1)
  })

  it('medyan yoksa null döner', () => {
    expect(yuzdeOnizlemesi(null, 15)).toBeNull()
  })

  it('yüzde yoksa/sıfırsa/negatifse null döner', () => {
    expect(yuzdeOnizlemesi(1000, null)).toBeNull()
    expect(yuzdeOnizlemesi(1000, 0)).toBeNull()
    expect(yuzdeOnizlemesi(1000, -5)).toBeNull()
  })

  it('NaN girdi null döner — hata fırlatmaz', () => {
    expect(yuzdeOnizlemesi(1000, NaN)).toBeNull()
  })
})

describe('yuzdeKullanilabilirMi', () => {
  it(`gecmis_gun >= ${YUZDE_ESIGI_GUN} ise kullanılabilir`, () => {
    expect(yuzdeKullanilabilirMi(YUZDE_ESIGI_GUN)).toBe(true)
    expect(yuzdeKullanilabilirMi(YUZDE_ESIGI_GUN + 10)).toBe(true)
  })

  it(`gecmis_gun < ${YUZDE_ESIGI_GUN} ise KULLANILAMAZ`, () => {
    expect(yuzdeKullanilabilirMi(YUZDE_ESIGI_GUN - 1)).toBe(false)
    expect(yuzdeKullanilabilirMi(0)).toBe(false)
  })

  it('gecmis_gun null ise kullanılamaz', () => {
    expect(yuzdeKullanilabilirMi(null)).toBe(false)
  })
})

describe('taslakBaslangici', () => {
  it('mevcut izlemenin gerçek değerlerinden başlar', () => {
    const taslak = taslakBaslangici({
      hedef_fiyat: 5000,
      dusus_yuzdesi: 15,
      yeniden_kur_gun: 30,
    })
    expect(taslak).toEqual({ hedefFiyat: 5000, yuzde: 15, yenidenKurGun: 30 })
  })

  it('yeniden_kur_gun null ise varsayılana (7) düşer', () => {
    const taslak = taslakBaslangici({
      hedef_fiyat: null,
      dusus_yuzdesi: null,
      yeniden_kur_gun: null,
    })
    expect(taslak.yenidenKurGun).toBe(7)
  })
})

describe('ozetCumlesi', () => {
  it('yalnızca hedef fiyat kuruluysa yalnızca onu anlatır', () => {
    const taslak: UyariTaslagi = { hedefFiyat: 5500, yuzde: null, yenidenKurGun: 7 }
    expect(ozetCumlesi(taslak, null)).toBe(
      '₺5.500,00 altına inince haber verilir; uyarıdan sonra 7 gün susar.',
    )
  })

  it('yalnızca yüzde kuruluysa önizleme fiyatını da cümleye katar', () => {
    const taslak: UyariTaslagi = { hedefFiyat: null, yuzde: 15, yenidenKurGun: 3 }
    const cumle = ozetCumlesi(taslak, 1000)
    expect(cumle).toBe(
      '90 günlük medyanın %15 altına düşünce (yaklaşık ₺850,00 ve altı) ' +
        'haber verilir; uyarıdan sonra 3 gün susar.',
    )
  })

  it("BACKLOG'un kendi örneği: HEM hedef HEM yüzde kuruluysa 'ya da' ile birleşir", () => {
    const taslak: UyariTaslagi = { hedefFiyat: 5500, yuzde: 15, yenidenKurGun: 7 }
    const cumle = ozetCumlesi(taslak, 2857)
    expect(cumle).toContain('₺5.500,00 altına inince ya da')
    expect(cumle).toContain('90 günlük medyanın %15 altına düşünce')
    expect(cumle.indexOf('₺5.500,00')).toBeLessThan(cumle.indexOf('90 günlük'))
  })

  it("hiçbiri kurulu değilse yalnızca dip cümlesi — rearm EKLENMEZ (DIP cooldown kullanmıyor)", () => {
    const taslak: UyariTaslagi = { hedefFiyat: null, yuzde: null, yenidenKurGun: 7 }
    expect(ozetCumlesi(taslak, null)).toBe(
      'Ürün 90 günün ya da tüm zamanların dibini kırınca haber verilir.',
    )
  })

  it("yeniden_kur_gun=0 ('hiç') seçiliyse 'bir daha haber verilmez' der", () => {
    const taslak: UyariTaslagi = { hedefFiyat: 5000, yuzde: null, yenidenKurGun: 0 }
    expect(ozetCumlesi(taslak, null)).toBe(
      '₺5.000,00 altına inince haber verilir; bir daha haber verilmez.',
    )
  })

  it('yüzde kuruluyken medyan henüz yoksa (önizleme hesaplanamaz) parantezli tahmini atlar', () => {
    const taslak: UyariTaslagi = { hedefFiyat: null, yuzde: 15, yenidenKurGun: 7 }
    const cumle = ozetCumlesi(taslak, null)
    expect(cumle).not.toContain('yaklaşık')
    expect(cumle).toContain('90 günlük medyanın %15 altına düşünce haber verilir')
  })
})

describe('taslaktanPatchGovdesi', () => {
  it('taslağı PATCH alanlarına birebir çevirir — boş alanlar açık null olarak gider (TEMİZLE)', () => {
    const taslak: UyariTaslagi = { hedefFiyat: null, yuzde: 15, yenidenKurGun: 30 }
    expect(taslaktanPatchGovdesi(taslak)).toEqual({
      hedef_fiyat: null,
      dusus_yuzdesi: 15,
      yeniden_kur_gun: 30,
    })
  })
})

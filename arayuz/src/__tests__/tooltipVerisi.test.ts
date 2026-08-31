import { describe, expect, it } from 'vitest'

import { magazaAdi, tooltipVerisiOlustur } from '../yardimcilar/tooltipVerisi'

describe('magazaAdi', () => {
  it('satıcı adı varsa onu döner', () => {
    expect(magazaAdi({ satici: 'Ucuz Mağaza', host: 'ucuz.com' })).toBe('Ucuz Mağaza')
  })

  it('satıcı adı yoksa host\'a düşer', () => {
    expect(magazaAdi({ satici: null, host: 'ucuz.com' })).toBe('ucuz.com')
  })
})

describe('tooltipVerisiOlustur', () => {
  it('medyana göre farkı doğru hesaplar (ucuz gün, negatif fark)', () => {
    const v = tooltipVerisiOlustur(
      { gun: '2026-01-01', fiyat: 900, stokta: true },
      { medyan90: 1000 },
    )
    expect(v.medyanFarki).toBeCloseTo(-10)
  })

  it('medyana göre farkı doğru hesaplar (pahalı gün, pozitif fark)', () => {
    const v = tooltipVerisiOlustur(
      { gun: '2026-01-01', fiyat: 1100, stokta: true },
      { medyan90: 1000 },
    )
    expect(v.medyanFarki).toBeCloseTo(10)
  })

  it('medyan bilinmiyorsa fark null döner', () => {
    const v = tooltipVerisiOlustur({ gun: '2026-01-01', fiyat: 900, stokta: true }, {})
    expect(v.medyanFarki).toBeNull()
  })

  it('fiyat null iken (stok yok) fark da null döner', () => {
    const v = tooltipVerisiOlustur(
      { gun: '2026-01-01', fiyat: null, stokta: false },
      { medyan90: 1000 },
    )
    expect(v.medyanFarki).toBeNull()
  })

  it('medyan 0 ise bölme hatası yerine null döner', () => {
    const v = tooltipVerisiOlustur(
      { gun: '2026-01-01', fiyat: 900, stokta: true },
      { medyan90: 0 },
    )
    expect(v.medyanFarki).toBeNull()
  })

  it('kabul ölçütü: tüm zamanlar dibi olan gün işaretlenir', () => {
    const v = tooltipVerisiOlustur(
      { gun: '2026-01-05', fiyat: 800, stokta: true },
      { tumZamanlarDibiTarih: '2026-01-05' },
    )
    expect(v.tumZamanlarDibiMi).toBe(true)
  })

  it('başka bir gün tüm zamanlar dibi olarak işaretlenmez', () => {
    const v = tooltipVerisiOlustur(
      { gun: '2026-01-06', fiyat: 800, stokta: true },
      { tumZamanlarDibiTarih: '2026-01-05' },
    )
    expect(v.tumZamanlarDibiMi).toBe(false)
  })

  it('tüm zamanlar dibi tarihi verilmemişse false döner', () => {
    const v = tooltipVerisiOlustur({ gun: '2026-01-05', fiyat: 800, stokta: true }, {})
    expect(v.tumZamanlarDibiMi).toBe(false)
  })

  it('mağaza belirtilmemişse null döner (çok kaynaklı birleşik görünüm)', () => {
    const v = tooltipVerisiOlustur({ gun: '2026-01-01', fiyat: 900, stokta: true }, {})
    expect(v.magaza).toBeNull()
  })

  it('mağaza belirtilmişse aynen taşınır', () => {
    const v = tooltipVerisiOlustur(
      { gun: '2026-01-01', fiyat: 900, stokta: true },
      { magaza: 'Ucuz Mağaza' },
    )
    expect(v.magaza).toBe('Ucuz Mağaza')
  })

  it('stok durumu ve gün aynen taşınır', () => {
    const v = tooltipVerisiOlustur({ gun: '2026-01-01', fiyat: null, stokta: false }, {})
    expect(v.gun).toBe('2026-01-01')
    expect(v.fiyat).toBeNull()
    expect(v.stokta).toBe(false)
  })
})

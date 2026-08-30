import { describe, expect, it } from 'vitest'

import { butceDurumu, enPahaliUye } from '../yardimcilar/setButcesi'

describe('butceDurumu', () => {
  it('bütçe yoksa butcesiz döner', () => {
    expect(butceDurumu(1000, null, 2, 0)).toEqual({ tur: 'butcesiz' })
  })

  it('boş sette bos döner — 0 asla aşmaz ama bu bir başarı değil', () => {
    expect(butceDurumu(0, 90000, 0, 0)).toEqual({ tur: 'bos' })
  })

  it('fiyatı eksik üye varsa eksik döner', () => {
    expect(butceDurumu(50000, 90000, 3, 1)).toEqual({ tur: 'eksik' })
  })

  it('BACKLOG F1 örneği: 104.826 / 90.000 → %16 aşıyor', () => {
    expect(butceDurumu(104826, 90000, 3, 0)).toEqual({
      tur: 'asiyor', fark: 14826, yuzde: 16,
    })
  })

  it('tam bütçe eşitse aşmıyor sayılır', () => {
    expect(butceDurumu(90000, 90000, 2, 0)).toEqual({ tur: 'altinda' })
  })

  it('bütçenin altındaysa altinda döner', () => {
    expect(butceDurumu(50000, 90000, 2, 0)).toEqual({ tur: 'altinda' })
  })
})

describe('enPahaliUye', () => {
  it('en yüksek fiyatlı üyenin id\'sini döner', () => {
    const uyeler = [
      { izleme_id: 1, fiyat: 10000 },
      { izleme_id: 2, fiyat: 25000 },
      { izleme_id: 3, fiyat: 15000 },
    ]
    expect(enPahaliUye(uyeler)).toBe(2)
  })

  it('fiyatı bilinmeyen üyeleri sayıma katmaz', () => {
    const uyeler = [
      { izleme_id: 1, fiyat: null },
      { izleme_id: 2, fiyat: 25000 },
    ]
    expect(enPahaliUye(uyeler)).toBeNull()
  })

  it('tek üyeli ya da boş sette işaretlenecek bir şey yok', () => {
    expect(enPahaliUye([{ izleme_id: 1, fiyat: 10000 }])).toBeNull()
    expect(enPahaliUye([])).toBeNull()
  })
})

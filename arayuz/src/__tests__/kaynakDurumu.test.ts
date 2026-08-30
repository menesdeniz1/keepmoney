import { describe, expect, it } from 'vitest'

import { DURUM_METNI, enUcuzKaynak } from '../yardimcilar/kaynakDurumu'

describe('DURUM_METNI', () => {
  it('her durum kodu için bir sebep cümlesi var', () => {
    const kodlar: Array<keyof typeof DURUM_METNI> = [
      'OK', 'ENGELLI', 'OLU', 'HATA', 'BEKLEMEDE', 'STOKTA_YOK',
    ]
    for (const kod of kodlar) {
      expect(DURUM_METNI[kod]).toBeTruthy()
    }
  })
})

describe('enUcuzKaynak', () => {
  it('en düşük fiyatlı OK kaynağı seçer', () => {
    const kaynaklar = [
      { id: 1, durum: 'OK' as const, son_fiyat: 1200 },
      { id: 2, durum: 'OK' as const, son_fiyat: 999 },
      { id: 3, durum: 'OK' as const, son_fiyat: 1500 },
    ]
    expect(enUcuzKaynak(kaynaklar)).toBe(2)
  })

  it('ENGELLİ ya da STOKTA_YOK kaynağın eski fiyatını asla en ucuz saymaz', () => {
    const kaynaklar = [
      { id: 1, durum: 'ENGELLI' as const, son_fiyat: 500 },
      { id: 2, durum: 'STOKTA_YOK' as const, son_fiyat: 600 },
      { id: 3, durum: 'OK' as const, son_fiyat: 1200 },
    ]
    expect(enUcuzKaynak(kaynaklar)).toBe(3)
  })

  it('okunabilen fiyat yoksa null döner', () => {
    const kaynaklar = [
      { id: 1, durum: 'ENGELLI' as const, son_fiyat: 500 },
      { id: 2, durum: 'OK' as const, son_fiyat: null },
    ]
    expect(enUcuzKaynak(kaynaklar)).toBeNull()
    expect(enUcuzKaynak([])).toBeNull()
  })
})

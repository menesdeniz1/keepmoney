import { describe, expect, it } from 'vitest'

import { hedefeKalan, kisaTl, tl, yuzde } from '../yardimcilar/bicim'

describe('TL biçimleme', () => {
  it('tr-TR biçiminde para gösterir', () => {
    expect(tl(26450.5)).toContain('26.450,50')
    expect(tl(null)).toBe('—')
  })

  it('kısa biçim ondalık göstermez', () => {
    expect(kisaTl(26450.5)).not.toContain(',50')
  })
})

describe('yuzde', () => {
  it('yön işaretiyle gösterir', () => {
    expect(yuzde(-4.23)).toBe('↓%4,2')
    expect(yuzde(2.1)).toBe('↑%2,1')
  })
})

describe('hedefeKalan', () => {
  it('hedefin altındaysa hedefte der', () => {
    expect(hedefeKalan(45000, 50000)).toEqual({ hedefte: true, fark: -5000 })
  })

  it('hedefin üstündeyse kalan farkı verir', () => {
    expect(hedefeKalan(55000, 50000)).toEqual({ hedefte: false, fark: 5000 })
  })

  it('veri eksikse null döner', () => {
    expect(hedefeKalan(null, 50000)).toBeNull()
    expect(hedefeKalan(50000, null)).toBeNull()
  })
})

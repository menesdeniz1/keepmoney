import { afterEach, describe, expect, it } from 'vitest'

import {
  efektifGorunum,
  gorunumBaslangici,
  gorunumGecerliMi,
  GORUNUM_ANAHTARI,
  GORUNUM_VARSAYILAN,
} from '../yardimcilar/gorunum'

afterEach(() => {
  localStorage.clear()
})

describe('gorunumGecerliMi', () => {
  it('kart ve tablo geçerlidir', () => {
    expect(gorunumGecerliMi('kart')).toBe(true)
    expect(gorunumGecerliMi('tablo')).toBe(true)
  })

  it('bilinmeyen değer ve null geçersizdir', () => {
    expect(gorunumGecerliMi('liste')).toBe(false)
    expect(gorunumGecerliMi(null)).toBe(false)
  })
})

describe('gorunumBaslangici', () => {
  it('kayıtlı değer yoksa varsayılanı (kart) döner', () => {
    expect(gorunumBaslangici()).toBe(GORUNUM_VARSAYILAN)
  })

  it('kayıtlı geçerli değeri döner', () => {
    localStorage.setItem(GORUNUM_ANAHTARI, 'tablo')
    expect(gorunumBaslangici()).toBe('tablo')
  })

  it('kayıtlı geçersiz değerde varsayılana düşer', () => {
    localStorage.setItem(GORUNUM_ANAHTARI, 'bozuk-deger')
    expect(gorunumBaslangici()).toBe(GORUNUM_VARSAYILAN)
  })
})

describe('efektifGorunum', () => {
  it('BACKLOG C3 kabul ölçütü: dar ekranda tercih tablo olsa bile kart döner', () => {
    expect(efektifGorunum('tablo', false)).toBe('kart')
  })

  it('geniş ekranda tercih neyse o döner', () => {
    expect(efektifGorunum('tablo', true)).toBe('tablo')
    expect(efektifGorunum('kart', true)).toBe('kart')
  })

  it('dar ekranda tercih zaten kart olsa da kart kalır', () => {
    expect(efektifGorunum('kart', false)).toBe('kart')
  })
})

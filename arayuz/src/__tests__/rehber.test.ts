import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ORNEK_LINK,
  REHBER_ANAHTARI,
  rehberBaslangici,
  rehberGorunurMu,
  rehberiBitir,
} from '../yardimcilar/rehber'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('rehberGorunurMu', () => {
  it('hiç ürünü olmayan yeni kullanıcıya gösterilir', () => {
    expect(rehberGorunurMu(false, 0)).toBe(true)
  })

  it('ürün varken gösterilmez', () => {
    expect(rehberGorunurMu(false, 1)).toBe(false)
    expect(rehberGorunurMu(false, 35)).toBe(false)
  })

  it('BACKLOG H2 kabul ölçütü: bir kez bittiyse GERİ GELMEZ', () => {
    // Kullanıcı ürün ekledi, sonra hepsini sildi: liste yine boş ama
    // rehber dönmemeli. Yalnızca `izlemeSayisi === 0` bakan bir kontrol
    // tam burada yanılırdı.
    expect(rehberGorunurMu(true, 0)).toBe(false)
  })

  it('liste henüz yüklenmediyse çizilmez (yanıp sönmesin)', () => {
    // `undefined` = TanStack Query ilk yükleme. `0` sayılsaydı ürünü olan
    // kullanıcı her sayfa açılışında rehberin bir an parladığını görürdü.
    expect(rehberGorunurMu(false, undefined)).toBe(false)
    expect(rehberGorunurMu(true, undefined)).toBe(false)
  })
})

describe('rehberBaslangici / rehberiBitir', () => {
  it('hiç yazılmamışken rehber bitmemiş sayılır', () => {
    expect(rehberBaslangici()).toBe(false)
  })

  it('bitirildikten sonra kalıcı olarak bitmiş okunur', () => {
    rehberiBitir()
    expect(localStorage.getItem(REHBER_ANAHTARI)).toBe('1')
    expect(rehberBaslangici()).toBe(true)
  })

  it('beklenmedik bir değer bitmiş sayılmaz', () => {
    localStorage.setItem(REHBER_ANAHTARI, 'evet')
    expect(rehberBaslangici()).toBe(false)
  })

  it('depolama okunamıyorsa rehber GÖSTERİLİR', () => {
    // Gizli sekme / depolama kapalı. Yanlış tarafa düşmek gerekiyorsa
    // "gereksiz yere gösterildi", "yeni kullanıcı hiç görmedi"den iyidir.
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('depolama kapalı')
    })
    expect(rehberBaslangici()).toBe(false)
  })

  it('depolama yazılamıyorsa çökmez', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('kota doldu')
    })
    expect(() => rehberiBitir()).not.toThrow()
  })
})

describe('ORNEK_LINK', () => {
  it('gerçek bir https ürün adresi', () => {
    // Kutuya dolan değer `type="url"` girdisinde geçerli olmalı; aksi
    // hâlde form gönderilemez ve örnek işe yaramaz.
    expect(() => new URL(ORNEK_LINK)).not.toThrow()
    expect(new URL(ORNEK_LINK).protocol).toBe('https:')
  })
})

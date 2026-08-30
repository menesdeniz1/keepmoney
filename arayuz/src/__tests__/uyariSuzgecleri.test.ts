import { describe, expect, it } from 'vitest'

import { suzgeciCoz } from '../yardimcilar/uyariSuzgecleri'

describe('suzgeciCoz', () => {
  it('tumu hiçbir tür süzmez, okunmamışa bakmaz', () => {
    expect(suzgeciCoz('tumu')).toEqual({ tur: null, sadeceOkunmamis: false })
  })

  it('hedef yalnızca HEDEF türünü ister', () => {
    expect(suzgeciCoz('hedef')).toEqual({ tur: ['HEDEF'], sadeceOkunmamis: false })
  })

  it('düşüş YUZDE ve DIP ikisini BİRLİKTE ister', () => {
    expect(suzgeciCoz('dusus')).toEqual({ tur: ['YUZDE', 'DIP'], sadeceOkunmamis: false })
  })

  it('set yalnızca SET_HEDEF türünü ister', () => {
    expect(suzgeciCoz('set')).toEqual({ tur: ['SET_HEDEF'], sadeceOkunmamis: false })
  })

  it('bozuk_kaynak yalnızca KAYNAK_BOZUK türünü ister', () => {
    expect(suzgeciCoz('bozuk_kaynak')).toEqual({ tur: ['KAYNAK_BOZUK'], sadeceOkunmamis: false })
  })

  it('okunmamış tür göndermez, yalnızca okunma durumuna bakar', () => {
    expect(suzgeciCoz('okunmamis')).toEqual({ tur: null, sadeceOkunmamis: true })
  })
})

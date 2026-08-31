import { describe, expect, it } from 'vitest'

import { stokBosluklariniBul } from '../yardimcilar/stokBosluklari'

function nokta(gun: string, stokta: boolean) {
  return { gun, stokta }
}

describe('stokBosluklariniBul', () => {
  it('hiç boşluk yoksa boş liste döner', () => {
    const veri = [nokta('2026-08-01', true), nokta('2026-08-02', true)]
    expect(stokBosluklariniBul(veri)).toEqual([])
  })

  it('tek günlük boşluğu tek aralık olarak döner', () => {
    const veri = [
      nokta('2026-08-01', true),
      nokta('2026-08-02', false),
      nokta('2026-08-03', true),
    ]
    expect(stokBosluklariniBul(veri)).toEqual([
      { baslangic: '2026-08-02', bitis: '2026-08-02' },
    ])
  })

  it('art arda gelen boşluk günlerini TEK aralığa birleştirir', () => {
    const veri = [
      nokta('2026-08-01', true),
      nokta('2026-08-02', false),
      nokta('2026-08-03', false),
      nokta('2026-08-04', false),
      nokta('2026-08-05', true),
    ]
    expect(stokBosluklariniBul(veri)).toEqual([
      { baslangic: '2026-08-02', bitis: '2026-08-04' },
    ])
  })

  it('birden fazla ayrı boşluk aralığını ayrı ayrı döner', () => {
    const veri = [
      nokta('2026-08-01', false),
      nokta('2026-08-02', true),
      nokta('2026-08-03', true),
      nokta('2026-08-04', false),
      nokta('2026-08-05', false),
    ]
    expect(stokBosluklariniBul(veri)).toEqual([
      { baslangic: '2026-08-01', bitis: '2026-08-01' },
      { baslangic: '2026-08-04', bitis: '2026-08-05' },
    ])
  })

  it('grafik SONA ererken açık kalan bir boşluğu da kapatır', () => {
    const veri = [nokta('2026-08-01', true), nokta('2026-08-02', false)]
    expect(stokBosluklariniBul(veri)).toEqual([
      { baslangic: '2026-08-02', bitis: '2026-08-02' },
    ])
  })

  it('grafik BAŞTAN itibaren boşluksa da doğru yakalar', () => {
    const veri = [nokta('2026-08-01', false), nokta('2026-08-02', true)]
    expect(stokBosluklariniBul(veri)).toEqual([
      { baslangic: '2026-08-01', bitis: '2026-08-01' },
    ])
  })

  it('boş veri listesinde patlamadan boş liste döner', () => {
    expect(stokBosluklariniBul([])).toEqual([])
  })
})

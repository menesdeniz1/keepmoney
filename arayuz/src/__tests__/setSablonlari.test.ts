import { describe, expect, it } from 'vitest'

import { eksikParcalar, sablonEtiketi } from '../yardimcilar/setSablonlari'

describe('eksikParcalar', () => {
  it('şablonsuz (null) sette hiçbir parça listelenmez', () => {
    expect(eksikParcalar(null, [{ kategori: 'Ekran Kartları' }])).toEqual([])
  })

  it('bilinmeyen bir şablon adında da boş liste döner — eski davranış korunur', () => {
    expect(eksikParcalar('tatil-listesi', [])).toEqual([])
  })

  it('hiç üye yoksa PC Toplama şablonunun tüm 7 parçası eksik', () => {
    expect(eksikParcalar('pc_toplama', [])).toHaveLength(7)
  })

  it('kategorisi eşleşen üye o parçayı listeden düşürür', () => {
    const eksik = eksikParcalar('pc_toplama', [{ kategori: 'Ekran Kartları' }])
    expect(eksik.some((p) => p.ad.includes('GPU'))).toBe(false)
    expect(eksik).toHaveLength(6)
  })

  it('eşleşme büyük/küçük harf duyarsız', () => {
    const eksik = eksikParcalar('pc_toplama', [{ kategori: 'İŞLEMCİ' }])
    expect(eksik.some((p) => p.ad.includes('CPU'))).toBe(false)
  })

  it('kategorisi bilinmeyen (null) üye hiçbir parçayı düşürmez', () => {
    expect(eksikParcalar('pc_toplama', [{ kategori: null }])).toHaveLength(7)
  })

  it('birden çok üye birden çok parçayı karşılayabilir', () => {
    const eksik = eksikParcalar('pc_toplama', [
      { kategori: 'İşlemciler' },
      { kategori: 'Ekran Kartları' },
      { kategori: 'SSD Diskler' },
    ])
    expect(eksik).toHaveLength(4)
  })

  it('ev kurulumu şablonu kendi parçalarını kullanır', () => {
    const eksik = eksikParcalar('ev_kurulumu', [{ kategori: 'Router' }])
    expect(eksik).toHaveLength(3)
    expect(eksik.some((p) => p.ad.includes('Router'))).toBe(false)
  })
})

describe('sablonEtiketi', () => {
  it('bilinen şablon için görünen adı döner', () => {
    expect(sablonEtiketi('pc_toplama')).toBe('PC Toplama')
  })

  it('null ya da bilinmeyen için null döner', () => {
    expect(sablonEtiketi(null)).toBeNull()
    expect(sablonEtiketi('tatil-listesi')).toBeNull()
  })
})

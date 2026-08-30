import { describe, expect, it } from 'vitest'

import { uyariGrubu, uyarilariGrupla } from '../yardimcilar/uyariGruplama'

// Sabit "şimdi": 15 Haziran 2026, 12:00 UTC (Türkiye'de 15:00, gün sınırını
// aşan bir kenar durum yaratmasın diye günün ortası seçildi).
const SIMDI = new Date('2026-06-15T12:00:00Z')

describe('uyariGrubu', () => {
  it('bugünkü bir zaman damgası "bugun" döner', () => {
    expect(uyariGrubu('2026-06-15T08:00:00Z', SIMDI)).toBe('bugun')
  })

  it('dünkü bir zaman damgası "dun" döner', () => {
    expect(uyariGrubu('2026-06-14T08:00:00Z', SIMDI)).toBe('dun')
  })

  it('2-6 gün önce "bu_hafta" döner', () => {
    expect(uyariGrubu('2026-06-13T08:00:00Z', SIMDI)).toBe('bu_hafta')
    expect(uyariGrubu('2026-06-09T08:00:00Z', SIMDI)).toBe('bu_hafta')
  })

  it('7+ gün önce "daha_eski" döner', () => {
    expect(uyariGrubu('2026-06-08T08:00:00Z', SIMDI)).toBe('daha_eski')
    expect(uyariGrubu('2025-01-01T08:00:00Z', SIMDI)).toBe('daha_eski')
  })

  it('gece yarısına yakın saatlerde Türkiye takvim gününü kullanır', () => {
    // 2026-06-15 02:00 UTC = Türkiye'de 05:00 — hâlâ 15 Haziran, "bugun".
    expect(uyariGrubu('2026-06-15T02:00:00Z', SIMDI)).toBe('bugun')
    // 2026-06-14 22:00 UTC = Türkiye'de 15 Haziran 01:00 — "bugun", "dun" DEĞİL.
    expect(uyariGrubu('2026-06-14T22:00:00Z', SIMDI)).toBe('bugun')
  })
})

describe('uyarilariGrupla', () => {
  function uyari(id: number, gunOnce: number): { id: number; created_at: string } {
    const d = new Date(SIMDI)
    d.setUTCDate(d.getUTCDate() - gunOnce)
    return { id, created_at: d.toISOString() }
  }

  it('ardışık aynı-grup öğeleri tek bölümde toplar', () => {
    const uyarilar = [uyari(1, 0), uyari(2, 0), uyari(3, 1), uyari(4, 10)]
    const bolumler = uyarilariGrupla(uyarilar, SIMDI)
    expect(bolumler.map((b) => b.grup)).toEqual(['bugun', 'dun', 'daha_eski'])
    expect(bolumler[0]!.ogeler.map((u) => u.id)).toEqual([1, 2])
    expect(bolumler[1]!.ogeler.map((u) => u.id)).toEqual([3])
    expect(bolumler[2]!.ogeler.map((u) => u.id)).toEqual([4])
  })

  it('SIRALAMA KORUNUR — hiçbir öğe yer değiştirmez, yalnızca bölümlenir', () => {
    const uyarilar = [uyari(5, 0), uyari(1, 3), uyari(9, 3), uyari(2, 20)]
    const bolumler = uyarilariGrupla(uyarilar, SIMDI)
    const duzIdler = bolumler.flatMap((b) => b.ogeler.map((u) => u.id))
    expect(duzIdler).toEqual([5, 1, 9, 2])
  })

  it('boş listede boş bölüm dizisi döner', () => {
    expect(uyarilariGrupla([], SIMDI)).toEqual([])
  })

  it('sayfalama simülasyonu: ikinci "sayfa" eklenince önceki bölümler bozulmaz', () => {
    const ilkSayfa = [uyari(1, 0), uyari(2, 1)]
    const ikinciSayfaEklenmis = [...ilkSayfa, uyari(3, 1), uyari(4, 15)]
    const once = uyarilariGrupla(ilkSayfa, SIMDI)
    const sonra = uyarilariGrupla(ikinciSayfaEklenmis, SIMDI)
    // "bugun" bölümü İKİSİNDE de aynı — yeni sayfa onu bozmadı.
    expect(sonra[0]).toEqual(once[0])
    // "dun" bölümü genişledi (3 eklendi), yeni bir "daha_eski" bölümü açıldı.
    expect(sonra[1]!.ogeler.map((u) => u.id)).toEqual([2, 3])
    expect(sonra[2]!.grup).toBe('daha_eski')
  })
})

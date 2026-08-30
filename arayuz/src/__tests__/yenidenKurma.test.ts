/**
 * BACKLOG E4 kabul ölçütü: kalan süre doğru gösteriliyor.
 */
import { describe, expect, it } from 'vitest'

import { yenidenKurmaDurumu, yenidenKurmaMetni } from '../yardimcilar/yenidenKurma'

const SIMDI = new Date('2026-08-29T12:00:00Z')

describe('yenidenKurmaDurumu', () => {
  it('hiç bildirim gitmediyse (son_bildirim_ts null) durum yok', () => {
    const durum = yenidenKurmaDurumu(
      { sustur_bitis: null, son_bildirim_ts: null, yeniden_kur_gun: 7 },
      SIMDI,
    )
    expect(durum).toBeNull()
  })

  it('susturma AKTİFSE — rearm bekliyor olsa bile — susturma önceliklidir', () => {
    const durum = yenidenKurmaDurumu(
      {
        sustur_bitis: '2026-09-05T12:00:00',
        son_bildirim_ts: '2026-08-29T10:00:00',
        yeniden_kur_gun: 7,
      },
      SIMDI,
    )
    expect(durum).toEqual({ tur: 'susturuldu', tarih: '2026-09-05T12:00:00' })
  })

  it('susturma SÜRESİ DOLMUŞSA görmezden gelinir, rearm hesabına geçilir', () => {
    const durum = yenidenKurmaDurumu(
      {
        sustur_bitis: '2026-08-20T12:00:00', // geçmişte kaldı
        son_bildirim_ts: '2026-08-29T10:00:00',
        yeniden_kur_gun: 7,
      },
      SIMDI,
    )
    expect(durum?.tur).toBe('bekliyor')
  })

  it('yeniden_kur_gun=0 ("hiç") — bildirim gittiyse bir daha uyarmaz', () => {
    const durum = yenidenKurmaDurumu(
      { sustur_bitis: null, son_bildirim_ts: '2026-08-29T10:00:00', yeniden_kur_gun: 0 },
      SIMDI,
    )
    expect(durum).toEqual({ tur: 'hic_uyarmaz' })
  })

  it('cooldown içindeyse kalan gün YUKARI YUVARLANIR (2.1 gün → 3 gün)', () => {
    // son_bildirim 4.9 gün önce, eşik 7 gün → kalan 2.1 gün.
    const sonBildirim = new Date(SIMDI.getTime() - 4.9 * 86_400_000).toISOString()
    const durum = yenidenKurmaDurumu(
      { sustur_bitis: null, son_bildirim_ts: sonBildirim, yeniden_kur_gun: 7 },
      SIMDI,
    )
    expect(durum).toEqual({ tur: 'bekliyor', kalanGun: 3 })
  })

  it('yeniden_kur_gun null ise varsayılan (7 gün) eşik kullanılır', () => {
    const sonBildirim = new Date(SIMDI.getTime() - 6 * 86_400_000).toISOString()
    const durum = yenidenKurmaDurumu(
      { sustur_bitis: null, son_bildirim_ts: sonBildirim, yeniden_kur_gun: null },
      SIMDI,
    )
    expect(durum).toEqual({ tur: 'bekliyor', kalanGun: 1 })
  })

  it('süre zaten dolmuşsa (worker bir sonraki taramada uyaracak) durum yok', () => {
    const sonBildirim = new Date(SIMDI.getTime() - 10 * 86_400_000).toISOString()
    const durum = yenidenKurmaDurumu(
      { sustur_bitis: null, son_bildirim_ts: sonBildirim, yeniden_kur_gun: 7 },
      SIMDI,
    )
    expect(durum).toBeNull()
  })
})

describe('yenidenKurmaMetni', () => {
  it('null durum için null döner (gösterilecek bir şey yok)', () => {
    expect(yenidenKurmaMetni(null)).toBeNull()
  })

  it("BACKLOG'un kendi örneği: 'susturuldu — {tarih}e kadar'", () => {
    const metin = yenidenKurmaMetni({ tur: 'susturuldu', tarih: '2026-09-12T12:00:00' })
    expect(metin).toContain('susturuldu —')
    expect(metin).toContain("kadar")
  })

  it("BACKLOG'un kendi örneği: 'N gün sonra yeniden uyarır'", () => {
    expect(yenidenKurmaMetni({ tur: 'bekliyor', kalanGun: 3 })).toBe(
      '3 gün sonra yeniden uyarır',
    )
  })

  it("'hiç' seçiliyken açık bir cümle verir", () => {
    expect(yenidenKurmaMetni({ tur: 'hic_uyarmaz' })).toContain('bir daha uyarmayacak')
  })
})

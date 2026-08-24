/**
 * BACKLOG B1 kabul ölçütleri — saf mantık fonksiyonları.
 *
 * `grafikAraligi.ts` bilerek `FiyatGrafigi.tsx`'ten AYRI: `FiyatGrafigi`
 * recharts (`ResponsiveContainer`) kullanıyor ve bu, jsdom'da gerçek
 * layout hesabı olmadan güvenilir test edilemez (genişlik/yükseklik 0
 * döner). Filtreleme ve "devre dışı" mantığı recharts'a hiç dokunmadan,
 * saf fonksiyon olarak test edilebiliyor — asıl davranış burada, görsel
 * render E2E'de.
 */
import { describe, expect, it } from 'vitest'

import type { FiyatNoktasi } from '../api/tipler'
import {
  grafikAraligaGoreSuz as araligaGoreSuz,
  grafikAraligiYetersiz as araligiYetersiz,
  grafikSinirTarihi as sinirTarihi,
} from '../yardimcilar/grafikAraligi'

function nokta(gunOnce: number, fiyat: number): FiyatNoktasi {
  const d = new Date()
  d.setDate(d.getDate() - gunOnce)
  return { gun: d.toISOString().slice(0, 10), fiyat }
}

describe('sinirTarihi', () => {
  it('bugünden N gün önceki ISO tarihi döner', () => {
    const beklenen = nokta(30, 0).gun
    expect(sinirTarihi(30)).toBe(beklenen)
  })
})

describe('araligaGoreSuz', () => {
  it('gun=null iken (Tümü) hiçbir şey filtrelemez', () => {
    const gecmis = [nokta(400, 100), nokta(10, 90)]
    expect(araligaGoreSuz(gecmis, null)).toEqual(gecmis)
  })

  it('yalnızca sınır tarihinden YENİ (>=) noktaları bırakır', () => {
    const gecmis = [nokta(100, 1000), nokta(50, 950), nokta(5, 900)]
    const sonuc = araligaGoreSuz(gecmis, 30)
    expect(sonuc).toEqual([nokta(5, 900)])
  })

  it('sınırın TAM ÜSTÜNDEKİ günü dahil eder (>=, sınırda dışlama yok)', () => {
    const tamSinirda = nokta(30, 500)
    expect(araligaGoreSuz([tamSinirda], 30)).toEqual([tamSinirda])
  })
})

describe('araligiYetersiz', () => {
  it('"Tümü" (gun=null) HİÇBİR ZAMAN yetersiz değildir', () => {
    expect(araligiYetersiz([], null)).toBe(false)
    expect(araligiYetersiz([nokta(1, 100)], null)).toBe(false)
  })

  it('geçmiş boşsa her sayısal aralık yetersizdir', () => {
    expect(araligiYetersiz([], 7)).toBe(true)
  })

  it('en eski nokta aralığın başlangıcından daha YENİYSE yetersizdir', () => {
    // yalnızca 5 günlük veri var; "30g" bu veriyle "Tümü"den farksız olurdu.
    const gecmis = [nokta(5, 100), nokta(1, 90)]
    expect(araligiYetersiz(gecmis, 30)).toBe(true)
  })

  it('en eski nokta aralığın başlangıcından daha ESKİYSE yeterlidir', () => {
    const gecmis = [nokta(45, 100), nokta(1, 90)]
    expect(araligiYetersiz(gecmis, 30)).toBe(false)
  })
})

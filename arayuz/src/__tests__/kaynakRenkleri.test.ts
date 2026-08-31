import { describe, expect, it } from 'vitest'

import type { KaynakSerisi } from '../api/tipler'
import {
  anahtar, birlesikVeri, enUcuzKaynakId, gorunurFiyatAraligi, kaynakStili,
} from '../yardimcilar/kaynakRenkleri'

describe('kaynakStili', () => {
  it('aynı host için her zaman aynı rengi döner (kararlı hash)', () => {
    expect(kaynakStili('amazon.com.tr', 2)).toEqual(kaynakStili('amazon.com.tr', 2))
  })

  it('2 ya da daha az kaynakta desen YOK', () => {
    expect(kaynakStili('amazon.com.tr', 1).desen).toBeUndefined()
    expect(kaynakStili('amazon.com.tr', 2).desen).toBeUndefined()
  })

  it('2den fazla kaynakta desen VAR', () => {
    expect(kaynakStili('amazon.com.tr', 3).desen).toBeTruthy()
  })

  it('farklı hostlar genelde farklı renk alır (çakışma olabilir ama hepsi aynı olmamalı)', () => {
    const hostlar = ['a.com', 'b.com', 'c.com', 'd.com', 'e.com', 'f.com']
    const renkler = new Set(hostlar.map((h) => kaynakStili(h, 2).renk))
    expect(renkler.size).toBeGreaterThan(1)
  })
})

describe('anahtar', () => {
  it('kaynak id\'sini önekli bir sütun adına çevirir', () => {
    expect(anahtar(12)).toBe('k12')
  })
})

describe('birlesikVeri', () => {
  const seriler: KaynakSerisi[] = [
    { kaynak_id: 1, host: 'a.com', noktalar: [
      { gun: '2026-01-01', fiyat: 1000, stokta: true },
      { gun: '2026-01-02', fiyat: 950, stokta: true },
    ] },
    { kaynak_id: 2, host: 'b.com', noktalar: [
      { gun: '2026-01-02', fiyat: 1200, stokta: true },
    ] },
  ]

  it('tüm günlerin birleşimini, sıralı olarak döner', () => {
    const veri = birlesikVeri(seriler)
    expect(veri.map((r) => r.gun)).toEqual(['2026-01-01', '2026-01-02'])
  })

  it('her satırda yalnızca o gün verisi olan kaynakların sütunu dolu', () => {
    const veri = birlesikVeri(seriler)
    expect(veri[0]).toEqual({ gun: '2026-01-01', k1: 1000 })
    expect(veri[1]).toEqual({ gun: '2026-01-02', k1: 950, k2: 1200 })
  })

  it('boş seri listesinde boş tablo döner', () => {
    expect(birlesikVeri([])).toEqual([])
  })

  it('BACKLOG B4: stok-yok noktası (fiyat null) sütuna null olarak yazılır', () => {
    const stokYokluSeriler: KaynakSerisi[] = [
      { kaynak_id: 1, host: 'a.com', noktalar: [
        { gun: '2026-01-01', fiyat: null, stokta: false },
      ] },
    ]
    expect(birlesikVeri(stokYokluSeriler)).toEqual([
      { gun: '2026-01-01', k1: null },
    ])
  })
})

describe('gorunurFiyatAraligi', () => {
  const seriler: KaynakSerisi[] = [
    { kaynak_id: 1, host: 'ucuz.com', noktalar: [
      { gun: '2026-01-01', fiyat: 800, stokta: true },
      { gun: '2026-01-02', fiyat: 850, stokta: true },
    ] },
    { kaynak_id: 2, host: 'pahali.com', noktalar: [
      { gun: '2026-01-01', fiyat: 2000, stokta: true },
      { gun: '2026-01-02', fiyat: 2100, stokta: true },
    ] },
  ]

  it('tüm kaynaklar görünürken ikisinin de aralığını kapsar', () => {
    expect(gorunurFiyatAraligi(seriler, new Set())).toEqual({ enDusuk: 800, enYuksek: 2100 })
  })

  it('BACKLOG B3 kabul ölçütü: pahalı kaynak gizlenince aralık daralır', () => {
    expect(gorunurFiyatAraligi(seriler, new Set([2]))).toEqual({ enDusuk: 800, enYuksek: 850 })
  })

  it('ucuz kaynak gizlenince aralık yükselir', () => {
    expect(gorunurFiyatAraligi(seriler, new Set([1]))).toEqual({ enDusuk: 2000, enYuksek: 2100 })
  })

  it('hepsi gizlenince null döner', () => {
    expect(gorunurFiyatAraligi(seriler, new Set([1, 2]))).toBeNull()
  })

  it('BACKLOG B4: stok-yok noktalarının null fiyatı aralık hesabını bozmaz', () => {
    const stokYokluSeriler: KaynakSerisi[] = [
      { kaynak_id: 1, host: 'a.com', noktalar: [
        { gun: '2026-01-01', fiyat: 800, stokta: true },
        { gun: '2026-01-02', fiyat: null, stokta: false },
      ] },
    ]
    // Mutasyon süzgeci olmasa `Math.min(800, null)` `null`ı 0'a çevirip
    // `enDusuk: 0` verirdi.
    expect(gorunurFiyatAraligi(stokYokluSeriler, new Set()))
      .toEqual({ enDusuk: 800, enYuksek: 800 })
  })
})

describe('enUcuzKaynakId', () => {
  it('son günün en düşük fiyatlı kaynağını seçer', () => {
    const seriler: KaynakSerisi[] = [
      { kaynak_id: 1, host: 'a.com', noktalar: [{ gun: '2026-01-01', fiyat: 1000, stokta: true }] },
      { kaynak_id: 2, host: 'b.com', noktalar: [{ gun: '2026-01-01', fiyat: 900, stokta: true }] },
    ]
    expect(enUcuzKaynakId(seriler)).toBe(2)
  })

  it('sonraki günlerdeki değişimi dikkate alır — SON nokta belirleyici', () => {
    const seriler: KaynakSerisi[] = [
      { kaynak_id: 1, host: 'a.com', noktalar: [
        { gun: '2026-01-01', fiyat: 500, stokta: true },
        { gun: '2026-01-02', fiyat: 1500, stokta: true },
      ] },
      { kaynak_id: 2, host: 'b.com', noktalar: [{ gun: '2026-01-01', fiyat: 900, stokta: true }] },
    ]
    expect(enUcuzKaynakId(seriler)).toBe(2)
  })

  it('noktası olmayan kaynağı yok sayar', () => {
    const seriler: KaynakSerisi[] = [
      { kaynak_id: 1, host: 'a.com', noktalar: [] },
      { kaynak_id: 2, host: 'b.com', noktalar: [{ gun: '2026-01-01', fiyat: 900, stokta: true }] },
    ]
    expect(enUcuzKaynakId(seriler)).toBe(2)
  })

  it('boş dizide null döner', () => {
    expect(enUcuzKaynakId([])).toBeNull()
  })

  it('BACKLOG B4: son nokta stok-yok boşluğuysa bir önceki BİLİNEN fiyata bakar', () => {
    const seriler: KaynakSerisi[] = [
      // kaynak 1'in son BİLİNEN fiyatı (500) kaynak 2'den (900) ucuz —
      // doğru cevap kaynak 1 olmalı, ama son NOKTASI stok-yok boşluğu.
      { kaynak_id: 1, host: 'a.com', noktalar: [
        { gun: '2026-01-01', fiyat: 500, stokta: true },
        { gun: '2026-01-02', fiyat: null, stokta: false },
      ] },
      { kaynak_id: 2, host: 'b.com', noktalar: [{ gun: '2026-01-01', fiyat: 900, stokta: true }] },
    ]
    // Kaynak 1 "son noktayı olduğu gibi al" mantığıyla ya YANLIŞLIKLA
    // dışlanır (boşluğu `null` gördüğü için) ya da `null < 900` JS'te
    // `0 < 900` olduğu için YANLIŞ biçimde "en ucuz" seçilir — ikisi de
    // yanlış cevap verirdi. Doğrusu: bilinen SON fiyata (500) bakıp
    // kaynak 1'i seçmek.
    expect(enUcuzKaynakId(seriler)).toBe(1)
  })

  it('BACKLOG B4: TÜM noktaları stok-yok olan kaynağı yok sayar', () => {
    const seriler: KaynakSerisi[] = [
      { kaynak_id: 1, host: 'a.com', noktalar: [
        { gun: '2026-01-01', fiyat: null, stokta: false },
      ] },
      { kaynak_id: 2, host: 'b.com', noktalar: [{ gun: '2026-01-01', fiyat: 900, stokta: true }] },
    ]
    expect(enUcuzKaynakId(seriler)).toBe(2)
  })
})

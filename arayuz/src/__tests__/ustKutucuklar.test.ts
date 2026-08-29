/**
 * BACKLOG C4 kabul ölçütleri: kutucuklar doğru sayıyor/buluyor, veri
 * yokken (0/null) anlamlı bir "boş" durumu ayırt edilebiliyor.
 */
import { describe, expect, it } from 'vitest'

import type { Izleme, UrunOzet } from '../api/tipler'
import { bugunDegisenSayisi, dipteKacUrun, enBuyukDusus } from '../yardimcilar/ustKutucuklar'

function urun(parcaGirdi: Partial<UrunOzet> & { id: number; ad: string }): UrunOzet {
  return {
    kategori: null,
    guncel_fiyat: null,
    guncel_satici: null,
    puan: null,
    yorum_sayisi: null,
    son_kontrol: null,
    sinyal: null,
    dip90: null,
    medyan90: null,
    yuzdelik: null,
    gecmis_gun: null,
    ...parcaGirdi,
  }
}

function izleme(parcaGirdi: Partial<Izleme> & { urun: UrunOzet }): Izleme {
  return {
    id: parcaGirdi.urun.id,
    hedef_fiyat: null,
    acil_fiyat: null,
    aktif: true,
    kilitli: false,
    kilitli_fiyat: null,
    sustur_bitis: null,
    set_idler: [],
    dusus_yuzdesi: null,
    yeniden_kur_gun: null,
    ...parcaGirdi,
  }
}

describe('dipteKacUrun', () => {
  it('yalnızca sinyal=dip olanları sayar', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A', sinyal: 'dip' }) }),
      izleme({ urun: urun({ id: 2, ad: 'B', sinyal: 'ucuz' }) }),
      izleme({ urun: urun({ id: 3, ad: 'C', sinyal: 'dip' }) }),
      izleme({ urun: urun({ id: 4, ad: 'D', sinyal: null }) }),
    ]
    expect(dipteKacUrun(liste)).toBe(2)
  })

  it('boş listede 0 döner', () => {
    expect(dipteKacUrun([])).toBe(0)
  })
})

describe('bugunDegisenSayisi', () => {
  const bugun = new Date('2026-08-28T12:00:00Z')
  const dun = new Date('2026-08-27T12:00:00Z')

  it('bugün okunmuş VE fiyatı değişmiş ürünü sayar', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A', son_kontrol: bugun.toISOString().slice(0, -1) }) }),
    ]
    const kivilcimlar = { '1': [1000, 900] }
    expect(bugunDegisenSayisi(liste, kivilcimlar, bugun)).toBe(1)
  })

  it('bugün okunmuş ama fiyatı AYNI kalmış ürünü SAYMAZ', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A', son_kontrol: bugun.toISOString().slice(0, -1) }) }),
    ]
    const kivilcimlar = { '1': [1000, 1000] }
    expect(bugunDegisenSayisi(liste, kivilcimlar, bugun)).toBe(0)
  })

  it('DÜN okunmuş ürünü — fiyatı değişmiş olsa bile — SAYMAZ ("bugün" iddiası)', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A', son_kontrol: dun.toISOString().slice(0, -1) }) }),
    ]
    const kivilcimlar = { '1': [1000, 900] }
    expect(bugunDegisenSayisi(liste, kivilcimlar, bugun)).toBe(0)
  })

  it('son_kontrol veya kıvılcım verisi yoksa saymaz, hata vermez', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'A', son_kontrol: null }) }),
      izleme({ urun: urun({ id: 2, ad: 'B', son_kontrol: bugun.toISOString().slice(0, -1) }) }),
    ]
    expect(bugunDegisenSayisi(liste, undefined, bugun)).toBe(0)
    expect(bugunDegisenSayisi(liste, {}, bugun)).toBe(0)
  })
})

describe('enBuyukDusus', () => {
  it('en büyük İLK-SON farkına sahip ürünü bulur', () => {
    const liste = [
      izleme({ urun: urun({ id: 1, ad: 'Az düşen' }) }),
      izleme({ urun: urun({ id: 2, ad: 'Çok düşen' }) }),
      izleme({ urun: urun({ id: 3, ad: 'Yükselen' }) }),
    ]
    const kivilcimlar30 = {
      '1': [1000, 950], // -50
      '2': [2000, 1500], // -500 (en büyük)
      '3': [500, 600], // yükseliyor, aday DEĞİL
    }
    const sonuc = enBuyukDusus(liste, kivilcimlar30)
    expect(sonuc).toEqual({ izlemeId: 2, ad: 'Çok düşen', tutar: 500 })
  })

  it('hiçbir üründe düşüş yoksa null döner', () => {
    const liste = [izleme({ urun: urun({ id: 1, ad: 'A' }) })]
    const kivilcimlar30 = { '1': [1000, 1200] }
    expect(enBuyukDusus(liste, kivilcimlar30)).toBeNull()
  })

  it('veri yoksa (undefined ya da tek nokta) null döner, hata vermez', () => {
    const liste = [izleme({ urun: urun({ id: 1, ad: 'A' }) })]
    expect(enBuyukDusus(liste, undefined)).toBeNull()
    expect(enBuyukDusus(liste, { '1': [1000] })).toBeNull()
  })
})

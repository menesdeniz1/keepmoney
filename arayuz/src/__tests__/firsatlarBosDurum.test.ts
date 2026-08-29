/**
 * BACKLOG D3 kabul ölçütü: üç durum üç ayrı metin veriyor.
 */
import { describe, expect, it } from 'vitest'

import type { Izleme, UrunOzet } from '../api/tipler'
import { firsatlarBosDurumu } from '../yardimcilar/firsatlarBosDurum'

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

describe('firsatlarBosDurumu', () => {
  it('firsatlar doluysa null döner — gösterilecek boş durum yok', () => {
    const dolu = [izleme({ urun: urun({ id: 1, ad: 'A' }) })]
    expect(firsatlarBosDurumu([], dolu)).toBeNull()
  })

  it('sorgular henüz yüklenmediyse (undefined) null döner', () => {
    expect(firsatlarBosDurumu(undefined, [])).toBeNull()
    expect(firsatlarBosDurumu([], undefined)).toBeNull()
  })

  it("hiç ürün yoksa 'hic_urun_yok'", () => {
    expect(firsatlarBosDurumu([], [])).toEqual({ tur: 'hic_urun_yok' })
  })

  it("ürün var ama HİÇBİRİNİN sinyali yoksa 'gecmis_yetersiz', gerçek gün sayısından kalan hesaplanır", () => {
    const izlemeler = [
      izleme({ urun: urun({ id: 1, ad: 'A', sinyal: null, gecmis_gun: 2 }) }),
      izleme({ urun: urun({ id: 2, ad: 'B', sinyal: null, gecmis_gun: 4 }) }),
    ]
    expect(firsatlarBosDurumu(izlemeler, [], 7)).toEqual({
      tur: 'gecmis_yetersiz',
      urunSayisi: 2,
      kalanGun: 3, // 7 - en ilerideki (4)
    })
  })

  it("gecmis_gun hiç yazılmamışsa (null) 0 gün birikmiş sayılır, kalanGun eşiğin tamamı", () => {
    const izlemeler = [izleme({ urun: urun({ id: 1, ad: 'A', sinyal: null, gecmis_gun: null }) })]
    expect(firsatlarBosDurumu(izlemeler, [], 7)).toEqual({
      tur: 'gecmis_yetersiz',
      urunSayisi: 1,
      kalanGun: 7,
    })
  })

  it("en az bir ürünün sinyali varsa (yeterli geçmiş) ama hiçbiri dip/ucuz değilse 'iyi_fiyat_yok'", () => {
    const izlemeler = [
      izleme({ urun: urun({ id: 1, ad: 'A', sinyal: 'pahali' }) }),
      izleme({ urun: urun({ id: 2, ad: 'B', sinyal: null }) }), // hâlâ biriktiriyor, önemsiz
    ]
    expect(firsatlarBosDurumu(izlemeler, [], 7)).toEqual({ tur: 'iyi_fiyat_yok' })
  })

  it('kalanGun asla negatif olmaz', () => {
    const izlemeler = [
      izleme({ urun: urun({ id: 1, ad: 'A', sinyal: null, gecmis_gun: 100 }) }),
    ]
    const durum = firsatlarBosDurumu(izlemeler, [], 7)
    expect(durum).toEqual({ tur: 'gecmis_yetersiz', urunSayisi: 1, kalanGun: 0 })
  })
})

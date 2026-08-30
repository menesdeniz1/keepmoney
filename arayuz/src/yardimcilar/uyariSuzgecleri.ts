/**
 * BACKLOG G2 — bildirimleri türe göre süz: hedef · düşüş · set · bozuk
 * kaynak · okunmamış. "Düşüş" YUZDE ve DIP'i BİRLİKTE gösterir — ikisi de
 * kullanıcı için aynı soruyu cevaplar ("fiyat düştü mü"), backend'de ayrı
 * `tur` değerleri olması bunu arayüze sızdırmamalı. `SAHTE_INDIRIM`
 * bilinçli olarak hızlı süzgeçlerde YOK — "Tümü" görünümünde hâlâ görünür,
 * yalnızca kendi hızlı filtresi yok (düşük sıklıklı, niş bir tür).
 */
import type { UyariTuru } from '../api/tipler'

export type UyariSuzgeci = 'tumu' | 'hedef' | 'dusus' | 'set' | 'bozuk_kaynak' | 'okunmamis'

export const SUZGEC_SECENEKLERI: { deger: UyariSuzgeci; etiket: string }[] = [
  { deger: 'tumu', etiket: 'Tümü' },
  { deger: 'hedef', etiket: 'Hedef' },
  { deger: 'dusus', etiket: 'Düşüş' },
  { deger: 'set', etiket: 'Set' },
  { deger: 'bozuk_kaynak', etiket: 'Bozuk kaynak' },
  { deger: 'okunmamis', etiket: 'Okunmamış' },
]

export interface UyariSorguParametreleri {
  tur: UyariTuru[] | null
  sadeceOkunmamis: boolean
}

/** Bir süzgeç seçimini backend'in `GET /api/uyarilar` sorgu parametrelerine
 *  çevirir. "okunmamış" `tur` GÖNDERMEZ — okunma durumu türden bağımsız
 *  ayrı bir eksen (`sadece_okunmamis`), ikisi karıştırılmamalı. */
export function suzgeciCoz(secim: UyariSuzgeci): UyariSorguParametreleri {
  switch (secim) {
    case 'hedef':
      return { tur: ['HEDEF'], sadeceOkunmamis: false }
    case 'dusus':
      return { tur: ['YUZDE', 'DIP'], sadeceOkunmamis: false }
    case 'set':
      return { tur: ['SET_HEDEF'], sadeceOkunmamis: false }
    case 'bozuk_kaynak':
      return { tur: ['KAYNAK_BOZUK'], sadeceOkunmamis: false }
    case 'okunmamis':
      return { tur: null, sadeceOkunmamis: true }
    case 'tumu':
      return { tur: null, sadeceOkunmamis: false }
  }
}

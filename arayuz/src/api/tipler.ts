/**
 * API sözleşmesi — backend `keepmoney/semalar.py` ile birebir.
 *
 * Elle yazıldı, üretilmedi. Sebep: OpenAPI'den tip üretmek (openapi-typescript)
 * bir adım daha kurulum ve senkron derdi getiriyor; sözleşme bu boyutta elle
 * takip edilebilir. Alan sayısı ikiye katlanırsa üretime geçilir.
 */

export type Sinyal = 'dip' | 'ucuz' | 'pahali'
export type TrendYonu = 'dusuyor' | 'yukseliyor' | 'sabit'
export type UyariTuru =
  | 'HEDEF'
  | 'DIP'
  | 'SAHTE_INDIRIM'
  | 'SET_HEDEF'
  | 'KAYNAK_BOZUK'

export interface Kullanici {
  id: number
  eposta: string
  telegram_bagli: boolean
  created_at: string
}

export interface Kaynak {
  id: number
  url: string
  host: string
  satici: string | null
  son_fiyat: number | null
  durum: 'OK' | 'ENGELLI' | 'OLU' | 'HATA' | 'BEKLEMEDE'
  son_kontrol: string | null
  /** Mağazaya gidiş linki — ortaklık etiketi varsa burada. */
  cikis_url: string
  /** true ise kullanıcıya AÇIKÇA "ortaklık bağlantısı" olarak gösterilir. */
  ortaklik: boolean
}

export interface FiyatNoktasi {
  gun: string
  fiyat: number
}

/** "Bu iyi bir fiyat mı?" — ürünün kalbi. */
export interface Baglam {
  sinyal: Sinyal
  emoji: string
  /** Kullanıcıya gösterilecek insan cümlesi. Backend üretir — tek kaynak. */
  yorum: string
  dip90: number
  medyan90: number
  yuzdelik: number
  tum_zamanlar_dibi: number
  tum_zamanlar_dibi_tarih: string
  /** "Kaç gündür bu kadar ucuz değildi" — 0 = rekor değil. */
  en_dusuk_gun: number
  gun_sayisi: number
  sahte_indirim: boolean
  trend_yonu: TrendYonu
  iyi_firsat: boolean
}

export interface UrunOzet {
  id: number
  ad: string
  kategori: string | null
  guncel_fiyat: number | null
  guncel_satici: string | null
  puan: number | null
  yorum_sayisi: number | null
  son_kontrol: string | null
}

export interface UrunDetay extends UrunOzet {
  kaynaklar: Kaynak[]
  gecmis: FiyatNoktasi[]
  baglam: Baglam | null
}

export interface Izleme {
  id: number
  hedef_fiyat: number | null
  acil_fiyat: number | null
  aktif: boolean
  kilitli: boolean
  kilitli_fiyat: number | null
  sustur_bitis: string | null
  set_id: number | null
  urun: UrunOzet
}

export interface IzlemeDetay extends Omit<Izleme, 'urun'> {
  urun: UrunDetay
}

export interface KmSet {
  id: number
  ad: string
  hedef_butce: number | null
  toplam: number
  eksik_uye: number
  hedefte: boolean
  uye_sayisi: number
}

export interface Uyari {
  id: number
  tur: UyariTuru
  baslik: string
  mesaj: string
  okundu: boolean
  created_at: string
  watch_id: number | null
}

export interface IzlemeEkleGirdi {
  url: string
  hedef_fiyat?: number | null
  acil_fiyat?: number | null
  set_id?: number | null
}

export interface IzlemeGuncelleGirdi {
  hedef_fiyat?: number | null
  acil_fiyat?: number | null
  aktif?: boolean
  kilitli?: boolean
  kilitli_fiyat?: number | null
  set_id?: number | null
  sustur_gun?: number | null
}

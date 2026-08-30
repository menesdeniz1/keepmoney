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
  | 'YUZDE'
  | 'DIP'
  | 'SAHTE_INDIRIM'
  | 'SET_HEDEF'
  | 'KAYNAK_BOZUK'

export interface Kullanici {
  id: number
  eposta: string
  telegram_bagli: boolean
  eposta_dogrulandi: boolean
  created_at: string
}

export interface SetGuncelleGirdi {
  ad?: string
  hedef_butce?: number | null
}

export interface Kaynak {
  id: number
  url: string
  host: string
  satici: string | null
  son_fiyat: number | null
  durum: 'OK' | 'ENGELLI' | 'OLU' | 'HATA' | 'BEKLEMEDE' | 'STOKTA_YOK'
  son_kontrol: string | null
  /** Mağazaya gidiş linki — ortaklık etiketi varsa burada. */
  cikis_url: string
  /** true ise kullanıcıya AÇIKÇA "ortaklık bağlantısı" olarak gösterilir. */
  ortaklik: boolean
  /** Toplayıcıda aynı ürünü satan mağaza sayısı (toplayıcı değilse null). */
  satici_sayisi: number | null
  /**
   * Toplayıcıda ikinci en ucuz fiyat. En ucuzdan belirgin yüksekse, o "en
   * ucuz" muhtemelen hatalı girilmiş TEK bir listedir — kullanıcı bunu
   * görmeli, çünkü geçmişi olmayan üründe elimizdeki tek uyarı işareti bu.
   */
  ikinci_fiyat: number | null
}

/**
 * Toplayıcı aramasından çıkan aday. Sunucuda HİÇBİR ŞEYE yazılmaz —
 * kullanıcı seçene kadar sistem bağ kurmaz. Otomatik eşleştirme yok:
 * benzer adlı iki ürünün fiyatını karıştırmak, grafiğe işleyen ve geri
 * alınamayan bir veri hatası olurdu.
 */
export interface KaynakOnerisi {
  ad: string
  url: string
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
  /**
   * BACKLOG A4: worker'ın her taramada hesaplayıp attığı bağlam artık
   * saklanıyor — kart, ürüne tıklamadan bu beşini gösterebilir. `null`
   * ikisinden biri demek: geçmiş `gecmis_gun < 7` (A7'nin "biriktiriliyor"
   * hâli) ya da ürün hiç taranmadı. `UrunDetay.baglam` (canlı hesap) bunun
   * yerini TUTMAZ — kart bu saklanan değeri, detay sayfası anlık hesabı
   * gösterir; ikisi arasında bir tarama turu kadar fark olabilir.
   */
  sinyal: Sinyal | null
  dip90: number | null
  medyan90: number | null
  yuzdelik: number | null
  gecmis_gun: number | null
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
  // Bir ürün BİRDEN ÇOK sette olabilir.
  set_idler: number[]
  // BACKLOG E1/E3 — hedef_fiyat ile BİRLİKTE kurulabilir (worker.py'nin
  // öncelik sırası: acil → hedef → yüzde → dip, ikisi birbirini
  // dışlamaz). `yeniden_kur_gun`: `null` = varsayılan (7 gün), `0` = "hiç".
  dusus_yuzdesi: number | null
  yeniden_kur_gun: number | null
  // BACKLOG E4 — arayüzün "N gün sonra yeniden uyarır" hesabı için. Salt
  // okunur: PATCH'te YOK, yalnızca `yeniden_kur: true` komutuyla sıfırlanır.
  son_bildirim_ts: string | null
  urun: UrunOzet
}

export interface IzlemeDetay extends Omit<Izleme, 'urun'> {
  urun: UrunDetay
}

export interface SetUyesi {
  izleme_id: number
  ad: string
  fiyat: number | null
  kilitli: boolean
}

export interface KmSet {
  id: number
  ad: string
  hedef_butce: number | null
  toplam: number
  eksik_uye: number
  hedefte: boolean
  uye_sayisi: number
  uyeler: SetUyesi[]
}

/** Toplu üyelik sonucu — KISMİ BAŞARI taşır: eklenenler ve sebepleriyle
 *  atlananlar. "Bir şeyler oldu" demek yerine hangi ürünün neden alınmadığı
 *  söylenir. */
export interface UyelikSonucu {
  eklendi: number[]
  atlandi: { id: number; sebep: string }[]
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
  set_idler?: number[] | null
}

export interface IzlemeGuncelleGirdi {
  hedef_fiyat?: number | null
  acil_fiyat?: number | null
  aktif?: boolean
  kilitli?: boolean
  kilitli_fiyat?: number | null
  set_idler?: number[] | null
  sustur_gun?: number | null
  dusus_yuzdesi?: number | null
  yeniden_kur_gun?: number | null
  // BACKLOG E4 — "tek tıkla şimdi yeniden kur" komutu, sütun değil.
  yeniden_kur?: boolean
}

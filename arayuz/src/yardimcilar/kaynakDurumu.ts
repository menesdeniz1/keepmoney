import type { Kaynak } from '../api/tipler'

/**
 * BACKLOG F3 — kaynaklar sadece host adıyla listeleniyordu, okunamama
 * SEBEBİ hiç görünmüyordu. Worker'ın yazdığı ham durum kodları
 * (`keepmoney/worker.py::kaynak_oku`) burada tek yerden insan cümlesine
 * çevrilir.
 *
 * STOKTA_YOK teknik olarak BAŞARILI bir okumadır (worker.py: "sayfa sağlam,
 * ürünün o an fiyatı yok") ama kullanıcı için sonuç aynı: bu mağazadan şu an
 * alamıyor. Tabloda "okunamayan" sebepleriyle aynı sütunda görünmesi doğru.
 */
export const DURUM_METNI: Record<Kaynak['durum'], string> = {
  OK: 'okunuyor',
  ENGELLI: 'bot duvarı',
  OLU: 'ölü link',
  HATA: 'okuma hatası',
  BEKLEMEDE: 'bekliyor',
  STOKTA_YOK: 'stokta yok',
}

/**
 * En ucuz kaynağın id'si — yalnızca ŞU AN okunabilen (durum OK), fiyatı
 * bilinen kaynaklar arasından. STOKTA_YOK ya da ENGELLİ bir kaynağın eski
 * fiyatı "en ucuz" işaretlenirse kullanıcı satın alamayacağı bir mağazaya
 * yönlenir — bu, `setler.py::ozet()`teki "eksik fiyatla hedefte deme"
 * ilkesiyle aynı gerekçe.
 */
export function enUcuzKaynak(
  kaynaklar: Pick<Kaynak, 'id' | 'durum' | 'son_fiyat'>[],
): number | null {
  const okunabilir = kaynaklar.filter((k) => k.durum === 'OK' && k.son_fiyat != null)
  if (okunabilir.length === 0) return null
  return okunabilir.reduce((en, k) => (k.son_fiyat! < en.son_fiyat! ? k : en)).id
}

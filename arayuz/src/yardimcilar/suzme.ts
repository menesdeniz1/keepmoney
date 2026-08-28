/**
 * BACKLOG C2 — panel liste süzmesi. Saf mantık, `siralama.ts` ile aynı
 * gerekçeyle ayrı: `ListeKontrol.tsx` bunu tüketir, testi kolaylaştırıyor.
 *
 * Süzgeç kategorileri BİRBİRİYLE VE mantığıyla birleşir (kabul ölçütü);
 * aynı kategori içindeki durum etiketleri (`durumlar`) BİRBİRİYLE VEYA —
 * kart zaten aynı anda birden çok durum rozetini gösterebiliyor
 * (`IzlemeKarti.tsx`: duraklatıldı + susturuldu + sabit aynı anda
 * görünebilir), süzgecin bunu "ya biri ya diğeri" gibi davranması yanlış
 * olurdu.
 */
import type { Izleme } from '../api/tipler'

export type SinyalSuzgeci = 'hepsi' | 'dip' | 'dip_ucuz'
export type DurumEtiketi = 'hedefli' | 'susturulmus' | 'duraklatilmis' | 'okunamayan'

export interface SuzgecDurumu {
  arama: string
  sinyal: SinyalSuzgeci
  setId: number | null
  magaza: string | null
  durumlar: DurumEtiketi[]
}

export const SUZGEC_BOS: SuzgecDurumu = {
  arama: '',
  sinyal: 'hepsi',
  setId: null,
  magaza: null,
  durumlar: [],
}

export const SINYAL_SUZGEC_SECENEKLERI: { deger: SinyalSuzgeci; etiket: string }[] = [
  { deger: 'hepsi', etiket: 'Tüm sinyaller' },
  { deger: 'dip', etiket: 'Yalnızca dip' },
  { deger: 'dip_ucuz', etiket: 'Dip + ucuz' },
]

export const DURUM_SECENEKLERI: { deger: DurumEtiketi; etiket: string }[] = [
  { deger: 'hedefli', etiket: 'Hedefi olanlar' },
  { deger: 'susturulmus', etiket: 'Susturulmuşlar' },
  { deger: 'duraklatilmis', etiket: 'Duraklatılmışlar' },
  { deger: 'okunamayan', etiket: 'Okunamayanlar' },
]

// `IzlemeKarti.tsx`'teki `susturulmus` hesabıyla AYNI — orada rozet
// gösterimi için, burada süzgeç eşleşmesi için, ikisi ıraksarsa kart ve
// süzgeç birbiriyle çelişen sonuç gösterirdi.
function susturulmusMu(izleme: Izleme): boolean {
  return izleme.sustur_bitis !== null && new Date(`${izleme.sustur_bitis}Z`) > new Date()
}

function durumEslesiyorMu(izleme: Izleme, etiket: DurumEtiketi): boolean {
  switch (etiket) {
    case 'hedefli':
      return izleme.hedef_fiyat !== null
    case 'susturulmus':
      return susturulmusMu(izleme)
    case 'duraklatilmis':
      return !izleme.aktif
    case 'okunamayan':
      // `UrunOzet.guncel_fiyat` yalnızca en az bir kaynaktan başarılı bir
      // okuma olduysa dolar — null, worker'ın fiyatı hiç çekemediği anlamına
      // gelir (bkz. `Kaynak.durum`: ENGELLI/OLU/HATA/STOKTA_YOK), "henüz
      // taranmadı" ile aynı görünür ama kullanıcı için ayrım önemsiz: her
      // iki durumda da "şu an elimde fiyat yok".
      return izleme.urun.guncel_fiyat === null
  }
}

export function izlemeleriSuz(izlemeler: Izleme[], suzgec: SuzgecDurumu): Izleme[] {
  const aramaKucuk = suzgec.arama.trim().toLocaleLowerCase('tr')
  return izlemeler.filter((i) => {
    if (aramaKucuk && !i.urun.ad.toLocaleLowerCase('tr').includes(aramaKucuk)) {
      return false
    }
    if (suzgec.sinyal === 'dip' && i.urun.sinyal !== 'dip') return false
    if (
      suzgec.sinyal === 'dip_ucuz' &&
      i.urun.sinyal !== 'dip' &&
      i.urun.sinyal !== 'ucuz'
    ) {
      return false
    }
    if (suzgec.setId !== null && !i.set_idler.includes(suzgec.setId)) return false
    if (suzgec.magaza !== null && i.urun.guncel_satici !== suzgec.magaza) return false
    if (
      suzgec.durumlar.length > 0 &&
      !suzgec.durumlar.some((d) => durumEslesiyorMu(i, d))
    ) {
      return false
    }
    return true
  })
}

export function suzgecBosMu(suzgec: SuzgecDurumu): boolean {
  return (
    suzgec.arama.trim() === '' &&
    suzgec.sinyal === 'hepsi' &&
    suzgec.setId === null &&
    suzgec.magaza === null &&
    suzgec.durumlar.length === 0
  )
}

/** Aktif çip listesi (BACKLOG C2: "kaldırılabilir çipler"). `setAdi` set adı
 *  çözümü için dışarıdan verilir — bu modül `useSetler()`'ı bilmez, saf kalır. */
export interface SuzgecCipi {
  anahtar: string
  etiket: string
  kaldir: (mevcut: SuzgecDurumu) => SuzgecDurumu
}

export function aktifCipler(
  suzgec: SuzgecDurumu,
  setAdi: (id: number) => string | undefined,
): SuzgecCipi[] {
  const cipler: SuzgecCipi[] = []

  if (suzgec.arama.trim() !== '') {
    cipler.push({
      anahtar: 'arama',
      etiket: `"${suzgec.arama.trim()}"`,
      kaldir: (m) => ({ ...m, arama: '' }),
    })
  }
  if (suzgec.sinyal !== 'hepsi') {
    const etiket =
      SINYAL_SUZGEC_SECENEKLERI.find((s) => s.deger === suzgec.sinyal)?.etiket ??
      suzgec.sinyal
    cipler.push({ anahtar: 'sinyal', etiket, kaldir: (m) => ({ ...m, sinyal: 'hepsi' }) })
  }
  if (suzgec.setId !== null) {
    const id = suzgec.setId
    cipler.push({
      anahtar: 'set',
      etiket: setAdi(id) ?? `Set #${id}`,
      kaldir: (m) => ({ ...m, setId: null }),
    })
  }
  if (suzgec.magaza !== null) {
    cipler.push({
      anahtar: 'magaza',
      etiket: suzgec.magaza,
      kaldir: (m) => ({ ...m, magaza: null }),
    })
  }
  for (const d of suzgec.durumlar) {
    const etiket = DURUM_SECENEKLERI.find((s) => s.deger === d)?.etiket ?? d
    cipler.push({
      anahtar: `durum-${d}`,
      etiket,
      kaldir: (m) => ({ ...m, durumlar: m.durumlar.filter((x) => x !== d) }),
    })
  }
  return cipler
}

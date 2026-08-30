/**
 * BACKLOG F4 — `WatchSet.sablon` sütunu vardı ama arayüzde hiç
 * kullanılmıyordu. Şablon = kontrol listesi: set kurarken seçilir, hangi
 * parçanın eksik olduğunu gösterir.
 *
 * EŞLEŞTİRME SEZGİSEL: bir parça, üyelerden birinin `kategori`si (mağaza
 * sayfasından OTOMATİK çıkarılan serbest metin) anahtar kelimelerden birini
 * içeriyorsa "eklendi" sayılır. KESİN DEĞİL — mağazalar kategoriyi farklı
 * yazar, bazen hiç yoktur — ama bahis düşük: yanlış "eksik" göstermek
 * yalnızca bilgilendirici bir satırı etkiler, hedefi/bütçeyi ASLA
 * engellemez (BACKLOG'un istediği tam olarak bu). Kesin eşleştirme
 * (kullanıcının parçayı elle seçmesi) yeni bir DB sütunu ister — F4 "Tür:
 * arayüz" olarak işaretli, kapsam dışı.
 */
export type SablonAdi = 'pc_toplama' | 'ev_kurulumu'

export interface SablonParcasi {
  ad: string
  anahtarKelimeler: string[]
}

export const SABLONLAR: Record<SablonAdi, { etiket: string; parcalar: SablonParcasi[] }> = {
  // Her parçanın hem tekil-iyelik ("kartı") hem çoğul ("kartları") hâli
  // AYRI AYRI listelendi: Türkçe ünsüz yumuşaması (kaynak→kaynağı) çoğul
  // ekiyle GERİ ALINMAZ (kaynaklar, yumuşamaz) — tek bir "kök" substring
  // ikisini BİRDEN yakalayamaz, gerçekten denenip GÖRÜLDÜ (bkz. testler).
  pc_toplama: {
    etiket: 'PC Toplama',
    parcalar: [
      { ad: 'İşlemci (CPU)', anahtarKelimeler: ['işlemci', 'cpu', 'processor'] },
      { ad: 'Ekran kartı (GPU)',
        anahtarKelimeler: ['ekran kartı', 'ekran kartları', 'gpu', 'graphics card'] },
      { ad: 'Bellek (RAM)', anahtarKelimeler: ['ram', 'bellek', 'memory'] },
      { ad: 'SSD / Depolama', anahtarKelimeler: ['ssd', 'nvme', 'depolama', 'hard disk', 'hdd'] },
      { ad: 'Güç kaynağı (PSU)',
        anahtarKelimeler: ['güç kaynağı', 'güç kaynakları', 'psu', 'power supply'] },
      { ad: 'Kasa', anahtarKelimeler: ['kasa', 'case', 'chassis'] },
      { ad: 'Monitör', anahtarKelimeler: ['monitör', 'monitor'] },
    ],
  },
  ev_kurulumu: {
    etiket: 'Ev kurulumu',
    parcalar: [
      { ad: 'Router / Modem', anahtarKelimeler: ['router', 'modem'] },
      { ad: 'Akıllı priz', anahtarKelimeler: ['akıllı priz', 'akıllı prizler', 'smart plug'] },
      { ad: 'Güvenlik kamerası', anahtarKelimeler: ['kamera', 'camera'] },
      { ad: 'Akıllı ampul', anahtarKelimeler: ['ampul', 'bulb', 'aydınlatma'] },
    ],
  },
}

export const SABLON_SECENEKLERI: { deger: SablonAdi | ''; etiket: string }[] = [
  { deger: '', etiket: 'Boş (şablonsuz)' },
  { deger: 'pc_toplama', etiket: SABLONLAR.pc_toplama.etiket },
  { deger: 'ev_kurulumu', etiket: SABLONLAR.ev_kurulumu.etiket },
]

function bilinenSablonMu(sablon: string | null): sablon is SablonAdi {
  return sablon === 'pc_toplama' || sablon === 'ev_kurulumu'
}

/** Bilinmeyen/null şablon → şablonsuz set gibi davran (boş liste): eski
 *  davranış korunur, hiçbir kontrol listesi gösterilmez. */
export function eksikParcalar(
  sablon: string | null,
  uyeler: { kategori: string | null }[],
): SablonParcasi[] {
  if (!bilinenSablonMu(sablon)) return []
  const kategoriler = uyeler.map((u) => (u.kategori ?? '').toLocaleLowerCase('tr-TR'))
  return SABLONLAR[sablon].parcalar.filter((parca) =>
    !parca.anahtarKelimeler.some((kelime) => {
      const arananKelime = kelime.toLocaleLowerCase('tr-TR')
      return kategoriler.some((k) => k.includes(arananKelime))
    }))
}

export function sablonEtiketi(sablon: string | null): string | null {
  return bilinenSablonMu(sablon) ? SABLONLAR[sablon].etiket : null
}

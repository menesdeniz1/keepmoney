/**
 * BACKLOG F1 — "₺104.826 / bütçe ₺90.000" yazıyordu, ne kadar aştığı yoktu.
 * Saf mantık, `bicim.ts::hedefeKalan` ile aynı katman ayrımı.
 *
 * Fiyatı eksik üye varken ya da set boşken aşıp aşmadığı BİLİNMİYOR —
 * `ozet()`teki "boş set hedefte sayılmaz" gerekçesiyle aynı: eksik toplamla
 * "aştın" ya da "altındasın" demek yanıltır. Bu iki durum ayrı tutuluyor
 * (`bos` / `eksik`) — ikisi de aynı nötr görünümü kullanacak olsa da, ayrı
 * bir mesaj yazmak istenirse ileride kolayca ayrışabilsin diye.
 */
export type ButceDurumu =
  | { tur: 'butcesiz' }
  | { tur: 'bos' }
  | { tur: 'eksik' }
  | { tur: 'asiyor'; fark: number; yuzde: number }
  | { tur: 'altinda' }

export function butceDurumu(
  toplam: number,
  hedefButce: number | null,
  uyeSayisi: number,
  eksikUye: number,
): ButceDurumu {
  if (hedefButce == null) return { tur: 'butcesiz' }
  if (uyeSayisi === 0) return { tur: 'bos' }
  if (eksikUye > 0) return { tur: 'eksik' }
  if (toplam > hedefButce) {
    const fark = toplam - hedefButce
    return { tur: 'asiyor', fark, yuzde: Math.round((fark / hedefButce) * 100) }
  }
  return { tur: 'altinda' }
}

/** En pahalı üyenin `izleme_id`si — birden az üyede ya da tüm fiyatlar
 *  bilinmiyorsa işaretlenecek bir şey yok. */
export function enPahaliUye(
  uyeler: { izleme_id: number; fiyat: number | null }[],
): number | null {
  const fiyatliUyeler = uyeler.filter((u) => u.fiyat !== null)
  if (fiyatliUyeler.length < 2) return null
  return fiyatliUyeler.reduce((en, u) => (u.fiyat! > en.fiyat! ? u : en)).izleme_id
}

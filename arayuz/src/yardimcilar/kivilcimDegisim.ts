/**
 * Kıvılcım dizisinden "ilk noktadan son noktaya % değişim" hesabı.
 *
 * BACKLOG A8'de `IzlemeKarti.tsx` İÇİNDE satır içi yazılmıştı; BACKLOG C1
 * (sıralama) AYNI hesaba Panel seviyesinde ihtiyaç duyunca buraya taşındı
 * — iki yerde iki ayrı hesap, biri güncellenip diğeri unutulursa sessizce
 * ıraksardı.
 */
export function kivilcimDegisimiHesapla(veri: number[] | undefined): number | null {
  if (!veri || veri.length < 2) return null
  const ilk = veri[0]
  const son = veri[veri.length - 1]
  if (!ilk || !son) return null
  return ((son - ilk) / ilk) * 100
}

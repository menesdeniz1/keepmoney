/**
 * BACKLOG E4 — "Kartta ve detayda: '3 gün sonra yeniden uyarır' veya
 * 'susturuldu — 12 Eylül'e kadar'". Saf mantık, `uyariKurulumu.ts` ile
 * aynı katman ayrımı — bu modül KURULUMU değil, GEÇERLİ DURUMU anlatır.
 */
import type { Izleme } from '../api/tipler'
import { tarih } from './bicim'
import { YENIDEN_KUR_VARSAYILAN } from './uyariKurulumu'

export type YenidenKurmaDurumu =
  | { tur: 'susturuldu'; tarih: string }
  | { tur: 'bekliyor'; kalanGun: number }
  | { tur: 'hic_uyarmaz' }
  | null

function isoTarihe(iso: string): Date {
  return new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
}

/**
 * Susturma ÖNCELİKLİDİR: kullanıcı AKTİF olarak sesi kapatmış, bu her
 * zaman rearm beklemesinden daha belirleyici bir bilgidir.
 *
 * `son_bildirim_ts` yoksa (hiç bildirim gitmemiş) gösterilecek bir
 * bekleme durumu da yoktur — `null` döner.
 */
export function yenidenKurmaDurumu(
  izleme: Pick<Izleme, 'sustur_bitis' | 'son_bildirim_ts' | 'yeniden_kur_gun'>,
  simdi: Date = new Date(),
): YenidenKurmaDurumu {
  if (izleme.sustur_bitis && isoTarihe(izleme.sustur_bitis) > simdi) {
    return { tur: 'susturuldu', tarih: izleme.sustur_bitis }
  }

  if (izleme.son_bildirim_ts == null) return null

  if (izleme.yeniden_kur_gun === 0) {
    return { tur: 'hic_uyarmaz' }
  }

  const kurGun = izleme.yeniden_kur_gun ?? YENIDEN_KUR_VARSAYILAN
  const rearmZamani = isoTarihe(izleme.son_bildirim_ts).getTime() + kurGun * 86_400_000
  const kalanMs = rearmZamani - simdi.getTime()
  if (kalanMs <= 0) return null // süre zaten doldu, bir sonraki taramada uyarır

  return { tur: 'bekliyor', kalanGun: Math.ceil(kalanMs / 86_400_000) }
}

export function yenidenKurmaMetni(durum: YenidenKurmaDurumu): string | null {
  if (durum === null) return null
  switch (durum.tur) {
    case 'susturuldu':
      return `susturuldu — ${tarih(durum.tarih)}'e kadar`
    case 'bekliyor':
      return `${durum.kalanGun} gün sonra yeniden uyarır`
    case 'hic_uyarmaz':
      return 'bir daha uyarmayacak (yeniden kurma: hiç)'
  }
}

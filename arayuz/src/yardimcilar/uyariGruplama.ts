/**
 * BACKLOG G1 — düz liste; uyarı biriktikçe okunmaz hâle geliyordu.
 * "Bugün · Dün · Bu hafta · Daha eski" başlıkları altında bölümleniyor.
 *
 * SIRALAMA KORUNUR, YENİDEN SIRALAMA YOK: liste zaten `created_at DESC`
 * sıralı gelir (bkz. `uyari.py::listele` — `id` ikinci anahtar, tam bu
 * yüzden). Burada yapılan tek şey ardışık aynı-grup öğeleri tek başlık
 * altında BÖLÜMLEMEK — sayfalama (infinite query) bu yüzden kırılmaz:
 * her sayfa geldiğinde tüm liste yeniden bölümlenir ama hiçbir öğe yer
 * değiştirmez, yalnızca başlıklar kayar/uzar.
 */
import type { Uyari } from '../api/tipler'
import { turkiyeGunAnahtari } from './bicim'

export type UyariGrubu = 'bugun' | 'dun' | 'bu_hafta' | 'daha_eski'

export const GRUP_BASLIGI: Record<UyariGrubu, string> = {
  bugun: 'Bugün',
  dun: 'Dün',
  bu_hafta: 'Bu hafta',
  daha_eski: 'Daha eski',
}

function gunFarki(gunAnahtari: string, simdiGunAnahtari: string): number {
  const a = new Date(`${gunAnahtari}T00:00:00Z`)
  const b = new Date(`${simdiGunAnahtari}T00:00:00Z`)
  return Math.round((b.getTime() - a.getTime()) / 86_400_000)
}

export function uyariGrubu(createdAtIso: string, simdi: Date = new Date()): UyariGrubu {
  const d = new Date(createdAtIso.endsWith('Z') ? createdAtIso : `${createdAtIso}Z`)
  const fark = gunFarki(turkiyeGunAnahtari(d), turkiyeGunAnahtari(simdi))
  // fark <= 0: aynı gün ya da (saat dilimi/saat senkron sapmasıyla) az
  // ileri bir zaman damgası — ikisi de "bugün" sayılır, gelecek bir bölüm
  // yaratmaz.
  if (fark <= 0) return 'bugun'
  if (fark === 1) return 'dun'
  if (fark <= 6) return 'bu_hafta'
  return 'daha_eski'
}

export interface UyariBolumu<T> {
  grup: UyariGrubu
  ogeler: T[]
}

export function uyarilariGrupla<T extends Pick<Uyari, 'created_at'>>(
  uyarilar: T[],
  simdi: Date = new Date(),
): UyariBolumu<T>[] {
  const bolumler: UyariBolumu<T>[] = []
  for (const u of uyarilar) {
    const grup = uyariGrubu(u.created_at, simdi)
    const sonBolum = bolumler[bolumler.length - 1]
    if (sonBolum && sonBolum.grup === grup) {
      sonBolum.ogeler.push(u)
    } else {
      bolumler.push({ grup, ogeler: [u] })
    }
  }
  return bolumler
}

/**
 * Tipli API istemcisi.
 *
 * TOKEN YÖNETİMİ YOK — bilerek. Oturum httpOnly çerezde duruyor (bkz.
 * docs/MIMARI.md K22); JavaScript token'ı ne okuyabilir ne yazabilir, bu
 * yüzden XSS ile çalınamaz. Tek yapmamız gereken `credentials: 'include'`.
 *
 * localStorage'da token tutmak yaygın ama zayıf bir kalıptır: sayfaya sızan
 * herhangi bir üçüncü parti script token'ı okuyup dışarı gönderebilir.
 */
import type {
  Izleme,
  IzlemeDetay,
  IzlemeEkleGirdi,
  IzlemeGuncelleGirdi,
  KmSet,
  Kullanici,
  Uyari,
} from './tipler'

const TABAN = '/api'

export class ApiHatasi extends Error {
  constructor(
    mesaj: string,
    readonly durum: number,
  ) {
    super(mesaj)
    this.name = 'ApiHatasi'
  }
}

async function istek<T>(
  yol: string,
  ayar: RequestInit & { gövde?: unknown } = {},
): Promise<T> {
  const { gövde, ...kalan } = ayar
  const yanit = await fetch(`${TABAN}${yol}`, {
    ...kalan,
    credentials: 'include',
    headers: {
      ...(gövde !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...kalan.headers,
    },
    ...(gövde !== undefined ? { body: JSON.stringify(gövde) } : {}),
  })

  if (!yanit.ok) {
    // FastAPI hataları {detail: "..."} ya da doğrulama için {detail: [...]}
    const veri = await yanit.json().catch(() => ({}))
    const ayrinti = (veri as { detail?: unknown }).detail
    const mesaj =
      typeof ayrinti === 'string'
        ? ayrinti
        : Array.isArray(ayrinti)
          ? 'Girdi geçersiz'
          : `İstek başarısız (${yanit.status})`
    throw new ApiHatasi(mesaj, yanit.status)
  }

  if (yanit.status === 204) return undefined as T
  return (await yanit.json()) as T
}

// ── Kimlik ──────────────────────────────────────────────────────
export const api = {
  kayit: (eposta: string, parola: string) =>
    istek<Kullanici>('/auth/kayit', { method: 'POST', gövde: { eposta, parola } }),

  giris: (eposta: string, parola: string) =>
    istek<{ erisim_tokeni: string }>('/auth/giris', {
      method: 'POST',
      gövde: { eposta, parola },
    }),

  cikis: () => istek<void>('/auth/cikis', { method: 'POST' }),

  ben: () => istek<Kullanici>('/auth/ben'),

  telegramBaglanti: () =>
    istek<{ baglanti: string; gecerlilik_dk: number }>(
      '/auth/telegram/baglanti',
      { method: 'POST' },
    ),

  telegramKaldir: () => istek<void>('/auth/telegram', { method: 'DELETE' }),

  // ── İzleme ────────────────────────────────────────────────────
  izlemeler: () => istek<Izleme[]>('/izlemeler'),

  izleme: (id: number) => istek<IzlemeDetay>(`/izlemeler/${id}`),

  izlemeEkle: (girdi: IzlemeEkleGirdi) =>
    istek<Izleme>('/izlemeler', { method: 'POST', gövde: girdi }),

  izlemeGuncelle: (id: number, girdi: IzlemeGuncelleGirdi) =>
    istek<Izleme>(`/izlemeler/${id}`, { method: 'PATCH', gövde: girdi }),

  izlemeSil: (id: number) =>
    istek<void>(`/izlemeler/${id}`, { method: 'DELETE' }),

  // ── Set ───────────────────────────────────────────────────────
  setler: () => istek<KmSet[]>('/setler'),

  setOlustur: (ad: string, hedef_butce?: number | null) =>
    istek<KmSet>('/setler', { method: 'POST', gövde: { ad, hedef_butce } }),

  setSil: (id: number) => istek<void>(`/setler/${id}`, { method: 'DELETE' }),

  // ── Uyarı ─────────────────────────────────────────────────────
  uyarilar: (sadeceOkunmamis = false) =>
    istek<Uyari[]>(`/uyarilar?sadece_okunmamis=${sadeceOkunmamis}`),

  okunmamisSayisi: () => istek<{ okunmamis: number }>('/uyarilar/sayi'),

  uyariOkundu: (id: number) =>
    istek<void>(`/uyarilar/${id}/okundu`, { method: 'POST' }),

  hepsiOkundu: () =>
    istek<{ isaretlenen: number }>('/uyarilar/hepsi-okundu', { method: 'POST' }),
}

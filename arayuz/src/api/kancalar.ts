/**
 * TanStack Query kancaları — sunucu durumu.
 *
 * Neden Redux/Zustand yok: bu uygulamada durumun neredeyse tamamı SUNUCU
 * durumu (izlemeler, fiyatlar, uyarılar). Sunucu durumunu global store'a
 * kopyalamak, önbellek geçersizleştirme ve bayatlık problemini elle çözmek
 * demektir — TanStack Query bunun için var. Gerçek istemci durumu (form
 * alanları, açık modal) bileşen içinde `useState` ile kalır.
 */
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query'

import { api } from './istemci'
import type {
  Izleme,
  IzlemeDetay,
  IzlemeEkleGirdi,
  IzlemeGuncelleGirdi,
  KmSet,
  Kullanici,
  SetGecmisNoktasi,
  SetGuncelleGirdi,
  UyariTuru,
} from './tipler'

/** Sorgu anahtarları tek yerde — yazım hatası kaynaklı "neden tazelenmiyor"
 *  hatalarının en yaygın sebebi dağınık anahtar dizileridir. */
export const anahtar = {
  ben: ['ben'] as const,
  izlemeler: ['izlemeler'] as const,
  izleme: (id: number) => ['izleme', id] as const,
  kivilcimlar: ['kivilcimlar'] as const,
  kivilcimlarGunle: (gun: number) => ['kivilcimlar', gun] as const,
  firsatlar: ['firsatlar'] as const,
  setler: ['setler'] as const,
  setGecmis: (id: number) => ['set-gecmis', id] as const,
  // BACKLOG G2 — `tur`/`watchId` de anahtara girer: aksi hâlde süzgeç
  // değişince önbellek eskisini gösterir (bu dosyanın kendi kuralı, üstteki
  // yorum).
  uyarilar: (sadeceOkunmamis: boolean, tur: UyariTuru[] | null, watchId: number | null) =>
    ['uyarilar', sadeceOkunmamis, tur, watchId] as const,
  uyariSayisi: ['uyari-sayisi'] as const,
}

export function useBen(): UseQueryResult<Kullanici> {
  return useQuery({
    queryKey: anahtar.ben,
    queryFn: api.ben,
    retry: false, // 401 tekrar denenmez — oturum yok demektir
    staleTime: 5 * 60_000,
  })
}

export function useIzlemeler(): UseQueryResult<Izleme[]> {
  return useQuery({ queryKey: anahtar.izlemeler, queryFn: api.izlemeler })
}

/**
 * Kart başına minik grafik verisi (BACKLOG A5/A8) — AYRI ve GECİKMELİ
 * yüklenir: `IzlemeKarti` bu kancayı KENDİ İÇİNDE çağırır, `useIzlemeler()`
 * ile YARIŞMAZ, kart onsuz da tam görünür (bkz. Kivilcim.tsx'in yer
 * ayıran boş durumu).
 *
 * 35 kartın HER BİRİ bu kancayı çağırsa bile TEK bir HTTP isteği gider —
 * TanStack Query aynı `queryKey` için istekleri TEKİLLEŞTİRİR ve sonucu
 * tüm çağıranlara dağıtır. Bu, backend'in kendi garantisiyle (A5: tek SQL
 * sorgusu) aynı ilkenin istemci tarafındaki karşılığı.
 */
export function useKivilcimlar(): UseQueryResult<Record<string, number[]>> {
  return useQuery({
    queryKey: anahtar.kivilcimlar,
    queryFn: () => api.kivilcimlar(),
    // Fiyat geçmişi dakikalar içinde değişmez; panel her odaklanmada bu
    // isteği tekrarlamasın.
    staleTime: 5 * 60_000,
  })
}

/**
 * BACKLOG C4 — "Son 30 günde en büyük düşüş" kutucuğu. `useKivilcimlar()`in
 * (varsayılan 90 gün) AYNI DEĞİL: farklı `queryKey`, dolayısıyla TanStack
 * Query bunu 35 kartın paylaştığı istekle TEKİLLEŞTİRMEZ, kendi tek başına
 * gider — kutucuk sayfa başına bir kez göründüğü için bu kabul edilebilir.
 */
export function useKivilcimlar30Gun(): UseQueryResult<Record<string, number[]>> {
  return useQuery({
    queryKey: anahtar.kivilcimlarGunle(30),
    queryFn: () => api.kivilcimlar(30),
    staleTime: 5 * 60_000,
  })
}

/** BACKLOG D2 — Fırsatlar sayfası. */
export function useFirsatlar(): UseQueryResult<Izleme[]> {
  return useQuery({ queryKey: anahtar.firsatlar, queryFn: api.firsatlar })
}

export function useIzleme(id: number): UseQueryResult<IzlemeDetay> {
  return useQuery({
    queryKey: anahtar.izleme(id),
    queryFn: () => api.izleme(id),
    enabled: Number.isFinite(id),
  })
}

export function useSetler(): UseQueryResult<KmSet[]> {
  return useQuery({ queryKey: anahtar.setler, queryFn: api.setler })
}

export function useSetGecmis(id: number): UseQueryResult<SetGecmisNoktasi[]> {
  return useQuery({
    queryKey: anahtar.setGecmis(id),
    queryFn: () => api.setGecmis(id),
    enabled: Number.isFinite(id),
  })
}

/** Sayfa boyutu — sunucudaki üst sınırla (100) uyumlu kalmalı. */
export const UYARI_SAYFA = 50

/**
 * Bildirimler SAYFALI çekilir.
 *
 * Eskiden tek istekle ilk 50 kayıt geliyordu ve daha eskisine ulaşmanın
 * hiçbir yolu yoktu — liste sessizce kesiliyordu.
 */
export function useUyarilar({
  sadeceOkunmamis = false, tur = null, watchId = null,
}: {
  sadeceOkunmamis?: boolean
  tur?: UyariTuru[] | null
  watchId?: number | null
} = {}) {
  return useInfiniteQuery({
    queryKey: anahtar.uyarilar(sadeceOkunmamis, tur, watchId),
    queryFn: ({ pageParam }) =>
      api.uyarilar({ sadeceOkunmamis, tur, watchId, offset: pageParam as number, limit: UYARI_SAYFA }),
    initialPageParam: 0,
    // Dolu sayfa geldiyse devamı olabilir; eksik sayfa son sayfadır.
    getNextPageParam: (sonSayfa, tumSayfalar) =>
      sonSayfa.length < UYARI_SAYFA ? undefined : tumSayfalar.length * UYARI_SAYFA,
  })
}

export function useOkunmamisSayisi() {
  return useQuery({
    queryKey: anahtar.uyariSayisi,
    queryFn: api.okunmamisSayisi,
    // Zil rozeti arka planda tazelensin; 60 sn yeterli, sunucuyu yormaz.
    refetchInterval: 60_000,
  })
}

// ── Mutasyonlar ────────────────────────────────────────────────

export function useIzlemeEkle() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (girdi: IzlemeEkleGirdi) => api.izlemeEkle(girdi),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: anahtar.izlemeler })
      void qc.invalidateQueries({ queryKey: anahtar.setler })
    },
  })
}

export function useIzlemeGuncelle(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (girdi: IzlemeGuncelleGirdi) => api.izlemeGuncelle(id, girdi),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: anahtar.izleme(id) })
      void qc.invalidateQueries({ queryKey: anahtar.izlemeler })
      void qc.invalidateQueries({ queryKey: anahtar.setler })
    },
  })
}

export function useIzlemeSil() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.izlemeSil(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: anahtar.izlemeler })
      void qc.invalidateQueries({ queryKey: anahtar.setler })
    },
  })
}

/**
 * Toplayıcıda aynı ürünü satan başka mağazaları arar.
 *
 * `enabled: false` ile başlar — arama YAVAŞ (~1-8 sn, gerekirse gerçek
 * tarayıcı açılıyor) ve dış siteye yük bindiriyor. Sayfa her açıldığında
 * kendiliğinden çalışması kabul edilemez; kullanıcı açıkça istemeli.
 */
export function useKaynakOnerileri(id: number) {
  return useQuery({
    queryKey: ['kaynak-onerileri', id] as const,
    queryFn: () => api.kaynakOnerileri(id),
    enabled: false,
    // Aday listesi kısa ömürlü olmalı: fiyatlar ve listeler değişiyor.
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

/** Kullanıcının SEÇTİĞİ adayı ürüne kaynak olarak bağlar. */
export function useKaynakEkle(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (url: string) => api.kaynakEkle(id, url),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: anahtar.izleme(id) })
      void qc.invalidateQueries({ queryKey: anahtar.izlemeler })
    },
  })
}

export function useSetOlustur() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ad, butce, sablon }: { ad: string; butce?: number | null; sablon?: string | null }) =>
      api.setOlustur(ad, butce, sablon),
    onSuccess: () => void qc.invalidateQueries({ queryKey: anahtar.setler }),
  })
}

export function useSetGuncelle() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, girdi }: { id: number; girdi: SetGuncelleGirdi }) =>
      api.setGuncelle(id, girdi),
    onSuccess: () => void qc.invalidateQueries({ queryKey: anahtar.setler }),
  })
}

export function useSetSil() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.setSil(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: anahtar.setler })
      void qc.invalidateQueries({ queryKey: anahtar.izlemeler })
    },
  })
}

export function useSetUyeEkle() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ setId, idler }: { setId: number; idler: number[] }) =>
      api.setUyeEkle(setId, idler),
    onSuccess: (_veri, { setId }) => {
      void qc.invalidateQueries({ queryKey: anahtar.setler })
      // İzleme listesi de tazelenir: kartlarda üyelik rozeti gösteriliyor.
      void qc.invalidateQueries({ queryKey: anahtar.izlemeler })
      // BACKLOG F2: üye eklenince geçmiş grafiği de yeniden hesaplanmalı.
      void qc.invalidateQueries({ queryKey: anahtar.setGecmis(setId) })
    },
  })
}

export function useSetUyeCikar() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ setId, izlemeId }: { setId: number; izlemeId: number }) =>
      api.setUyeCikar(setId, izlemeId),
    onSuccess: (_veri, { setId }) => {
      void qc.invalidateQueries({ queryKey: anahtar.setler })
      void qc.invalidateQueries({ queryKey: anahtar.izlemeler })
      void qc.invalidateQueries({ queryKey: anahtar.setGecmis(setId) })
    },
  })
}

export function useUyariOkundu() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.uyariOkundu(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['uyarilar'] })
      void qc.invalidateQueries({ queryKey: anahtar.uyariSayisi })
    },
  })
}

export function useHepsiOkundu() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.hepsiOkundu,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['uyarilar'] })
      void qc.invalidateQueries({ queryKey: anahtar.uyariSayisi })
    },
  })
}

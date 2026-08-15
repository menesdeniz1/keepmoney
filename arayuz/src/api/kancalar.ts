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
  SetGuncelleGirdi,
} from './tipler'

/** Sorgu anahtarları tek yerde — yazım hatası kaynaklı "neden tazelenmiyor"
 *  hatalarının en yaygın sebebi dağınık anahtar dizileridir. */
export const anahtar = {
  ben: ['ben'] as const,
  izlemeler: ['izlemeler'] as const,
  izleme: (id: number) => ['izleme', id] as const,
  setler: ['setler'] as const,
  uyarilar: (sadeceOkunmamis: boolean) => ['uyarilar', sadeceOkunmamis] as const,
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

/** Sayfa boyutu — sunucudaki üst sınırla (100) uyumlu kalmalı. */
export const UYARI_SAYFA = 50

/**
 * Bildirimler SAYFALI çekilir.
 *
 * Eskiden tek istekle ilk 50 kayıt geliyordu ve daha eskisine ulaşmanın
 * hiçbir yolu yoktu — liste sessizce kesiliyordu.
 */
export function useUyarilar(sadeceOkunmamis = false) {
  return useInfiniteQuery({
    queryKey: anahtar.uyarilar(sadeceOkunmamis),
    queryFn: ({ pageParam }) =>
      api.uyarilar(sadeceOkunmamis, pageParam as number, UYARI_SAYFA),
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

export function useSetOlustur() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ad, butce }: { ad: string; butce?: number | null }) =>
      api.setOlustur(ad, butce),
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

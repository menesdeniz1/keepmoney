/**
 * BACKLOG D3 — Fırsatlar sayfasının boş listesi ÜÇ FARKLI SEBEPTEN olabilir
 * ve üçü ayrı cümle ister; aynı ekranda hepsine "boş" demek yanıltıcı.
 * Saf mantık, `siralama.ts`/`suzme.ts` ile aynı katman ayrımı.
 */
import type { Izleme } from '../api/tipler'

/**
 * `/api/firsatlar`'ın parametresiz çağrıda uyguladığı GERÇEK varsayılan
 * eşik (`FIRSAT_VARSAYILAN_EN_AZ_GUN`, keepmoney/servisler/izleme.py) —
 * `Firsatlar.tsx` bu ucu HİÇBİR PARAMETRE VERMEDEN çağırıyor (istemci.ts),
 * yani bu sabit backend'in şu anki GERÇEK davranışıyla eşleşiyor. Diğer
 * eşiklerin (`analiz.MIN_GUN`) aksine bu sayı hiçbir API alanında GİZLİ
 * DEĞİL — bu SAYFANIN kendi isteğinin bir parçası, D1'in kendi örnek
 * çağrısında da yazılı. Backend'deki varsayılan değişirse burası da
 * güncellenmeli.
 */
export const FIRSAT_ESIGI_GUN = 7

export type FirsatBosDurumu =
  | { tur: 'hic_urun_yok' }
  | { tur: 'gecmis_yetersiz'; urunSayisi: number; kalanGun: number }
  | { tur: 'iyi_fiyat_yok' }
  | null

/**
 * `firsatlar` (D1'in süzülmüş listesi) boş değilse `null` — gösterilecek
 * bir boş durum yok. Boşsa, `izlemeler` (TÜM ürünler, süzülmemiş) hangi
 * sebebe göre karar verilir:
 *
 * 1. Hiç ürün yok.
 * 2. Ürün var ama HİÇBİRİNİN sinyali yok (`urun.sinyal === null` — A7'nin
 *    "biriktiriliyor" durumu, `worker.py`de gecmis_gun MIN_GUN'un altında
 *    kaldığı sürece sinyal hiç yazılmaz).
 * 3. En az bir ürünün sinyali var (yeterli geçmiş biriktirilmiş) ama
 *    hiçbiri dip/ucuz değil — hepsi "pahalı" ya da normal aralıkta.
 */
export function firsatlarBosDurumu(
  izlemeler: Izleme[] | undefined,
  firsatlar: Izleme[] | undefined,
  esikGun: number = FIRSAT_ESIGI_GUN,
): FirsatBosDurumu {
  if (!firsatlar || firsatlar.length > 0) return null
  if (!izlemeler) return null
  if (izlemeler.length === 0) return { tur: 'hic_urun_yok' }

  const sinyalliler = izlemeler.filter((i) => i.urun.sinyal !== null)
  if (sinyalliler.length === 0) {
    const enIlerideki = Math.max(0, ...izlemeler.map((i) => i.urun.gecmis_gun ?? 0))
    return {
      tur: 'gecmis_yetersiz',
      urunSayisi: izlemeler.length,
      kalanGun: Math.max(0, esikGun - enIlerideki),
    }
  }

  return { tur: 'iyi_fiyat_yok' }
}

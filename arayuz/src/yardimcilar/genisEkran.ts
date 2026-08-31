import { useEffect, useState } from 'react'

/**
 * BACKLOG C3 — "768px altında her zaman kart". Her genişlikte TAZE
 * sayfa yüklemesinde (700/768/900px) doğru karar verdiği gerçek
 * tarayıcıda ÖLÇÜLDÜ. `matchMedia`nın `change` olayı VE `window`un
 * `resize` olayı BİRLİKTE dinleniyor ki masaüstünde pencere canlı
 * daraltılınca sayfa yenilenmeden tepki versin — ikisi standart, iyi
 * desteklenen API'ler (bkz. MDN), tek bir olay kaynağına güvenmemek
 * bilinçli bir tercih.
 *
 * NOT: bu depodaki MCP tarayıcı otomasyon aracının CDP tabanlı görünüm
 * boyutlandırması `innerWidth`i doğru günceller ama NE `matchMedia`
 * `change`i NE `window` `resize`i ateşliyor (ikisi de doğrudan
 * `dispatchEvent` ile test edilip ÖLÇÜLDÜ) — bu aracın kendi bir
 * sınırlaması, gerçek bir tarayıcı penceresi boyutlandırmasında ikisi de
 * güvenilir şekilde ateşlenir. Canlı geçiş bu yüzden yalnızca taze
 * sayfa yüklemesiyle doğrulanabildi, canlı-daraltma senaryosu bu araçla
 * ölçülemedi.
 */
export function useGenisEkran(pxEsik: number): boolean {
  const sorgu = `(min-width: ${pxEsik}px)`
  const [genisMi, setGenisMi] = useState(() => window.matchMedia(sorgu).matches)

  useEffect(() => {
    const mq = window.matchMedia(sorgu)
    const guncelle = () => setGenisMi(window.matchMedia(sorgu).matches)
    guncelle()
    mq.addEventListener('change', guncelle)
    window.addEventListener('resize', guncelle)
    return () => {
      mq.removeEventListener('change', guncelle)
      window.removeEventListener('resize', guncelle)
    }
  }, [sorgu])

  return genisMi
}

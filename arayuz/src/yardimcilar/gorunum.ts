/**
 * BACKLOG C3 — Panel kart/tablo görünüm tercihi. Saf mantık; `Panel.tsx`
 * kullanır — `siralama.ts`/`grafikAraligi.ts` ile AYNI ayrım gerekçesi.
 */
export type GorunumTercihi = 'kart' | 'tablo'

export const GORUNUM_ANAHTARI = 'km:panel-gorunum'
export const GORUNUM_VARSAYILAN: GorunumTercihi = 'kart'

export function gorunumGecerliMi(deger: string | null): deger is GorunumTercihi {
  return deger === 'kart' || deger === 'tablo'
}

export function gorunumBaslangici(): GorunumTercihi {
  try {
    const kayitli = localStorage.getItem(GORUNUM_ANAHTARI)
    return gorunumGecerliMi(kayitli) ? kayitli : GORUNUM_VARSAYILAN
  } catch {
    // Gizli sekme / depolama kapalı — sessizce varsayılana düş.
    return GORUNUM_VARSAYILAN
  }
}

/**
 * BACKLOG C3 kabul ölçütü: "768px altında her zaman kart" — kullanıcının
 * SAKLI tercihi 'tablo' olsa bile dar ekranda tablo GÖSTERİLMEZ. Tercih
 * bozulmaz (localStorage'da 'tablo' olarak kalır, geniş ekrana dönünce
 * geri gelir), yalnızca o an EKRANDA görünen şey değişir.
 */
export function efektifGorunum(
  tercih: GorunumTercihi,
  genisEkranMi: boolean,
): GorunumTercihi {
  return genisEkranMi ? tercih : 'kart'
}

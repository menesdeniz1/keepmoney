import { Link } from 'react-router-dom'
import { BellOff, Clock, Lock, PauseCircle } from 'lucide-react'

import { useKivilcimlar } from '../api/kancalar'
import type { Izleme } from '../api/tipler'
import Kivilcim from './Kivilcim'
import SinyalRozeti from './SinyalRozeti'
import { goreliZaman, hedefeKalan, kisaTl, tl, yuzde } from '../yardimcilar/bicim'
import { kivilcimDegisimiHesapla } from '../yardimcilar/kivilcimDegisim'
import { yenidenKurmaDurumu, yenidenKurmaMetni } from '../yardimcilar/yenidenKurma'

/** Yüzde farkı yeşil/kırmızı boyar — DÜŞÜŞ her zaman iyi haber (ucuzlamış),
 * artış nötr/kırmızı. `yuzde()` yönü zaten oka çeviriyor, burada sadece renk. */
function farkRengi(y: number): string {
  return y < 0
    ? 'text-green-600 dark:text-green-400'
    : 'text-slate-500 dark:text-slate-400'
}

export default function IzlemeKarti({ izleme }: { izleme: Izleme }) {
  const { urun } = izleme
  const durum = hedefeKalan(urun.guncel_fiyat, izleme.hedef_fiyat)
  // BACKLOG E4: susturma VE rearm beklemesi TEK bir hesaptan geliyor
  // (`yenidenKurma.ts`) — ikisini burada ayrı ayrı türetmek (eskiden
  // olduğu gibi) susturma mantığının iki yerde ıraksama riskini taşırdı.
  const rearmDurum = yenidenKurmaDurumu(izleme)
  const susturulmus = rearmDurum?.tur === 'susturuldu'

  // BACKLOG A8: kıvılcım verisi AYRI ve GECİKMELİ — bu kanca kendi isteğini
  // açar, `izlemeler` listesini beklemez. 35 kartın hepsi aynı queryKey'i
  // çağırsa da TanStack Query TEK istekte birleştirir (kancalar.ts).
  const { data: kivilcimlar } = useKivilcimlar()
  const kivilcimVerisi = kivilcimlar?.[String(izleme.id)]

  // Medyana göre % fark: "bugünün fiyatı 90 günlük ortalamaya göre nasıl".
  const medyanFarki =
    urun.medyan90 != null && urun.guncel_fiyat != null
      ? ((urun.guncel_fiyat - urun.medyan90) / urun.medyan90) * 100
      : null

  // "N günlük değişim": SABİT "30 gün" YAZILMIYOR — kıvılcım verisi tarih
  // taşımıyor (A5'in kendi tasarımı: "eksen yok, yer kaplar"), yani 30
  // günlük bir pencereyi KIVILCIM VERİSİNDEN doğru kesmek mümkün değil.
  // Bunun yerine GERÇEK veri aralığının başı/sonu karşılaştırılıyor ve
  // etiket urun.gecmis_gun'daki GERÇEK gün sayısını gösteriyor. Hesap
  // `yardimcilar/kivilcimDegisim.ts`'te — BACKLOG C1 (sıralama) aynı
  // hesaba Panel seviyesinde de ihtiyaç duyuyor.
  const kivilcimDegisim = kivilcimDegisimiHesapla(kivilcimVerisi)

  return (
    <Link
      to={`/izleme/${izleme.id}`}
      // `min-w-0` BACKLOG A8'de eklendi — CSS Grid'in bilinen tuzağı:
      // grid item'ın kendisi `min-width: auto` (varsayılan) kalırsa,
      // İÇİNDEKİ sıkıştırılamaz bir öğe (burada: Kivilcim'in sabit 56px
      // SVG'si + shrink-0'lı sağ blok) TÜM SÜTUNU kendi genişliğine göre
      // büyütür — GERÇEK TARAYICIDA (390px) ölçüldü: `min-w-0` olmadan
      // kart 1099px'e taşıyordu, TÜM kartlar (sinyalsiz olanlar dahil)
      // aynı genişliğe zorlanmıştı çünkü grid sütunları paylaşılıyor.
      className="block min-w-0 rounded-lg border border-slate-200 bg-white p-4
                 transition hover:border-slate-300 hover:shadow-sm
                 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <SinyalRozeti
            sinyal={urun.sinyal}
            yuzdelik={urun.yuzdelik}
            gecmisGun={urun.gecmis_gun}
          />
          <h3 className="mt-1.5 truncate font-medium">{urun.ad}</h3>
          <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
            {urun.guncel_satici ?? 'bilinmiyor'} ·{' '}
            {goreliZaman(urun.son_kontrol)}
            {medyanFarki !== null && (
              <>
                {' · medyana göre '}
                <span className={farkRengi(medyanFarki)}>{yuzde(medyanFarki)}</span>
              </>
            )}
          </p>
        </div>

        <div className="shrink-0 text-right">
          <div className="font-mono text-lg font-semibold">
            {tl(urun.guncel_fiyat)}
          </div>
          {durum && (
            <div
              className={`text-xs font-medium ${
                durum.hedefte
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-slate-500 dark:text-slate-400'
              }`}
            >
              {durum.hedefte
                ? '🎯 hedefte'
                : `hedefe ${kisaTl(durum.fark)} kaldı`}
            </div>
          )}
          <div className="mt-1.5 flex items-center justify-end gap-1.5">
            {kivilcimDegisim !== null && (
              <span className={`text-[11px] tabular-nums ${farkRengi(kivilcimDegisim)}`}>
                {yuzde(kivilcimDegisim)}
                {urun.gecmis_gun != null && (
                  <span className="text-slate-400 dark:text-slate-600">
                    {' '}· {urun.gecmis_gun}g
                  </span>
                )}
              </span>
            )}
            <Kivilcim veri={kivilcimVerisi} sinyal={urun.sinyal} />
          </div>
        </div>
      </div>

      {(susturulmus || !izleme.aktif || izleme.kilitli || rearmDurum?.tur === 'bekliyor'
        || rearmDurum?.tur === 'hic_uyarmaz') && (
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500 dark:text-slate-400">
          {!izleme.aktif && (
            <span className="inline-flex items-center gap-1">
              <PauseCircle size={13} /> duraklatıldı
            </span>
          )}
          {susturulmus && (
            <span className="inline-flex items-center gap-1">
              <BellOff size={13} /> {yenidenKurmaMetni(rearmDurum)}
            </span>
          )}
          {/* Susturma YOKKEN rearm beklemesi ya da "hiç" durumu — ikisi
              AYNI ANDA gösterilmez (yenidenKurma.ts susturmayı önceliklendirir). */}
          {!susturulmus && (rearmDurum?.tur === 'bekliyor' || rearmDurum?.tur === 'hic_uyarmaz') && (
            <span className="inline-flex items-center gap-1">
              <Clock size={13} /> {yenidenKurmaMetni(rearmDurum)}
            </span>
          )}
          {izleme.kilitli && (
            <span className="inline-flex items-center gap-1">
              <Lock size={13} /> {tl(izleme.kilitli_fiyat)} sabit
            </span>
          )}
        </div>
      )}
    </Link>
  )
}

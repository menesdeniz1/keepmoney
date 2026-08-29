import { useState } from 'react'

import { useIzlemeGuncelle } from '../api/kancalar'
import type { Izleme, UrunOzet } from '../api/tipler'
import { tl } from '../yardimcilar/bicim'
import {
  ozetCumlesi,
  taslaktanPatchGovdesi,
  YENIDEN_KUR_SECENEKLERI,
  YENIDEN_KUR_VARSAYILAN,
  YUZDE_ESIGI_GUN,
  yuzdeKullanilabilirMi,
  yuzdeOnizlemesi,
  type UyariTaslagi,
} from '../yardimcilar/uyariKurulumu'

/**
 * BACKLOG E3 — "Hedef fiyat" tek kutusunun yerine geçen kurulum paneli.
 *
 * Hedef fiyat ve yüzde düşüş BAĞIMSIZ onay kutuları — İKİSİ BİRDEN
 * açılabilir (bkz. `uyariKurulumu.ts`'in üst yorumu: worker.py'nin
 * öncelik sırası tam da bunun için var). "Dip kırılınca" KAPATILAMAZ
 * bir bilgi satırı — `Watch`te bunu temsil eden sütun yok, worker her
 * zaman uyguluyor.
 */
export default function UyariKurulumu({
  izleme,
  urun,
}: {
  izleme: Izleme
  urun: UrunOzet
}) {
  const guncelle = useIzlemeGuncelle(izleme.id)

  const [hedefAcik, setHedefAcik] = useState(izleme.hedef_fiyat != null)
  const [hedefMetin, setHedefMetin] = useState(
    izleme.hedef_fiyat != null ? String(izleme.hedef_fiyat) : '',
  )
  const [yuzdeAcik, setYuzdeAcik] = useState(izleme.dusus_yuzdesi != null)
  const [yuzdeMetin, setYuzdeMetin] = useState(
    izleme.dusus_yuzdesi != null ? String(izleme.dusus_yuzdesi) : '',
  )
  const [yenidenKurGun, setYenidenKurGun] = useState(
    izleme.yeniden_kur_gun ?? YENIDEN_KUR_VARSAYILAN,
  )

  const yuzdeMumkunMu = yuzdeKullanilabilirMi(urun.gecmis_gun)

  const hedefSayi = hedefAcik ? Number(hedefMetin) || null : null
  const yuzdeSayi = yuzdeAcik && yuzdeMumkunMu ? Number(yuzdeMetin) || null : null

  const taslak: UyariTaslagi = {
    hedefFiyat: hedefSayi,
    yuzde: yuzdeSayi,
    yenidenKurGun,
  }
  const onizleme = yuzdeOnizlemesi(urun.medyan90, yuzdeSayi)
  const ozet = ozetCumlesi(taslak, urun.medyan90)

  function kaydet(e: React.FormEvent) {
    e.preventDefault()
    guncelle.mutate(taslaktanPatchGovdesi(taslak))
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4
                    dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-sm font-medium">Uyarı kur</h2>

      <form onSubmit={kaydet} className="space-y-3">
        <label className="flex items-start gap-2 text-sm">
          <input
            id="hedef-fiyat-onay"
            type="checkbox"
            checked={hedefAcik}
            onChange={(e) => setHedefAcik(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-slate-300 dark:border-slate-700"
          />
          <span className="flex-1">
            <span className="font-medium">Hedef fiyat</span>
            {hedefAcik && (
              <>
                <input
                  id="hedef-fiyat"
                  type="number"
                  min="1"
                  value={hedefMetin}
                  onChange={(e) => setHedefMetin(e.target.value)}
                  placeholder="örn. 45000"
                  className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-1.5
                             text-sm dark:border-slate-700 dark:bg-slate-950"
                />
                {/* Sunucu tarafı davranış (servisler/izleme.py::guncelle):
                    hedef GERÇEKTEN değişince susturma kalkar — kullanıcı
                    yeni eşikten bildirim bekliyor, eski eşiğin dedup kaydı
                    yeni eşiği susturmamalı. */}
                <p className="mt-1 text-xs text-slate-500">
                  Hedefi değiştirmek susturmayı kaldırır.
                </p>
              </>
            )}
          </span>
        </label>

        <label
          className={`flex items-start gap-2 text-sm ${!yuzdeMumkunMu ? 'opacity-60' : ''}`}
        >
          <input
            id="yuzde-dususu-onay"
            type="checkbox"
            checked={yuzdeAcik}
            disabled={!yuzdeMumkunMu}
            onChange={(e) => setYuzdeAcik(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-slate-300 dark:border-slate-700"
          />
          <span className="flex-1">
            <span className="font-medium">Yüzde düşüş</span>
            {!yuzdeMumkunMu && (
              <p className="mt-0.5 text-xs text-slate-500">
                {urun.gecmis_gun != null
                  ? `Yeterli geçmiş birikince kullanılabilir (~${
                      YUZDE_ESIGI_GUN - urun.gecmis_gun
                    } gün kaldı).`
                  : 'Yeterli geçmiş birikince kullanılabilir.'}
              </p>
            )}
            {yuzdeMumkunMu && yuzdeAcik && (
              <>
                <div className="mt-1 flex items-center gap-1.5">
                  <input
                    id="yuzde-dususu"
                    type="number"
                    min="1"
                    max="90"
                    value={yuzdeMetin}
                    onChange={(e) => setYuzdeMetin(e.target.value)}
                    placeholder="örn. 15"
                    className="w-24 rounded-md border border-slate-300 px-3 py-1.5 text-sm
                               dark:border-slate-700 dark:bg-slate-950"
                  />
                  <span className="text-slate-500">%</span>
                </div>
                {/* Kabul ölçütü: "Önizleme yazarken anlık güncelleniyor" —
                    kaydetmeyi BEKLEMEZ, saf hesap her render'da çalışır. */}
                {onizleme != null && (
                  <p id="yuzde-onizleme" className="mt-1 text-xs text-slate-500">
                    → yaklaşık {tl(onizleme)} ve altı
                  </p>
                )}
              </>
            )}
          </span>
        </label>

        <p className="flex items-start gap-2 text-sm text-slate-500 dark:text-slate-400">
          <span aria-hidden="true">✓</span>
          <span>
            <span className="font-medium text-slate-700 dark:text-slate-300">
              Dip kırılınca
            </span>{' '}
            (her zaman açık) — ürün 90 günün ya da tüm zamanların dibini
            kırınca, yukarıdaki seçimlerden bağımsız haber verilir.
          </span>
        </p>

        <div>
          <label htmlFor="yeniden-kur" className="mb-1 block text-xs text-slate-500">
            Yeniden kurma süresi
          </label>
          <select
            id="yeniden-kur"
            value={yenidenKurGun}
            onChange={(e) => setYenidenKurGun(Number(e.target.value))}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm
                       dark:border-slate-700 dark:bg-slate-950"
          >
            {YENIDEN_KUR_SECENEKLERI.map((s) => (
              <option key={s.deger} value={s.deger}>
                {s.etiket}
              </option>
            ))}
          </select>
        </div>

        <p id="uyari-ozet" className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600
                      dark:bg-slate-950 dark:text-slate-400">
          {ozet}
        </p>

        <button
          disabled={guncelle.isPending}
          className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white
                     disabled:opacity-50 dark:bg-white dark:text-slate-900"
        >
          {guncelle.isPending ? '…' : 'Kaydet'}
        </button>
      </form>
    </div>
  )
}

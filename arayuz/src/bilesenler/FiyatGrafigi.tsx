/**
 * Keepa tarzı fiyat geçmişi grafiği.
 *
 * Tasarım kararları:
 *  • Gün başına TEK nokta — backend zaten günlük minimuma indirgiyor (K4).
 *    Ham okumaları çizmek, sık taranan ürünü yanıltıcı biçimde "yoğun"
 *    gösterirdi.
 *  • Hedef fiyat kesikli yatay çizgi: kullanıcı "ne kadar kaldı"yı grafikten
 *    okuyabilsin.
 *  • 90 günün dibi ayrı bir referans çizgisi — "bu iyi fiyat mı" sorusunun
 *    görsel karşılığı.
 *  • Alan dolgusu (area) değil çizgi: alan, fiyat grafiğinde "hacim" çağrışımı
 *    yapıyor ve yanıltıcı.
 *  • BACKLOG B1 — zaman aralığı düğmeleri: tüm geçmiş tek görünümde
 *    eziliyordu, son haftanın hareketi 120 günün içinde kayboluyordu.
 *    Tamamen istemci tarafı — `gecmis` zaten geliyor, yalnızca dilimleniyor.
 */
import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { Baglam, FiyatNoktasi } from '../api/tipler'
import { kisaTl, tl } from '../yardimcilar/bicim'
import {
  GRAFIK_ARALIK_ANAHTARI,
  GRAFIK_ARALIK_SECENEKLERI,
  type GrafikAraligi,
  grafikAraligaGoreSuz,
  grafikAraligiYetersiz,
  grafikBaslangicAraligi,
} from '../yardimcilar/grafikAraligi'

interface Props {
  gecmis: FiyatNoktasi[]
  hedefFiyat?: number | null
  baglam?: Baglam | null
  yukseklik?: number
}

const SINYAL_RENGI: Record<string, string> = {
  dip: '#16a34a',
  ucuz: '#ca8a04',
  pahali: '#dc2626',
}

function gunEtiketi(gun: string): string {
  const [, ay, tarih] = gun.split('-')
  return `${tarih}.${ay}`
}

export default function FiyatGrafigi({
  gecmis,
  hedefFiyat,
  baglam,
  yukseklik = 280,
}: Props) {
  const [araligi, setAraligi] = useState<GrafikAraligi>(grafikBaslangicAraligi)

  function araligiSec(yeni: GrafikAraligi) {
    setAraligi(yeni)
    try {
      localStorage.setItem(GRAFIK_ARALIK_ANAHTARI, yeni)
    } catch {
      // Depolama kapalıysa seçim yalnızca bu oturumda kalır — sorun değil.
    }
  }

  const secilenGun = GRAFIK_ARALIK_SECENEKLERI.find((s) => s.deger === araligi)?.gun ?? null
  const gorunenGecmis = grafikAraligaGoreSuz(gecmis, secilenGun)

  if (gecmis.length < 2) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed
                   border-slate-300 text-sm text-slate-500 dark:border-slate-700"
        style={{ height: yukseklik }}
      >
        Grafik için en az iki günlük veri gerekiyor — ilk taramalar sürüyor.
      </div>
    )
  }

  // Seçili aralıkta veri kalmayabilir (örn. ürün 10 gün önce eklendi, "7g"
  // seçiliyken TÜM okumalar bugünden 8 gün önceye ait) — GRAFİĞİ BOŞ
  // ÇİZMEK yerine tüm geçmişe düş, kullanıcı boş bir kutuyla karşılaşmasın.
  const veri = gorunenGecmis.length >= 2 ? gorunenGecmis : gecmis

  const renk = baglam ? (SINYAL_RENGI[baglam.sinyal] ?? '#0ea5e9') : '#0ea5e9'
  const fiyatlar = veri.map((n) => n.fiyat)
  const enDusuk = Math.min(...fiyatlar)
  const enYuksek = Math.max(...fiyatlar)
  // Y eksenini fiyat aralığına oturt: 0'dan başlatmak, %2'lik oynamaları
  // görünmez yapar ve grafiği işe yaramaz hâle getirir.
  const pay = Math.max((enYuksek - enDusuk) * 0.15, enDusuk * 0.02)

  return (
    <div>
      <div
        role="group"
        aria-label="Grafik zaman aralığı"
        className="mb-2 flex justify-end gap-1"
      >
        {GRAFIK_ARALIK_SECENEKLERI.map((s) => {
          const yetersiz = grafikAraligiYetersiz(gecmis, s.gun)
          const secili = araligi === s.deger
          return (
            <button
              key={s.deger}
              type="button"
              aria-pressed={secili}
              disabled={yetersiz}
              onClick={() => araligiSec(s.deger)}
              className={`rounded px-2 py-1 text-xs font-medium transition
                         disabled:cursor-not-allowed disabled:opacity-40
                         ${
                           secili
                             ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900'
                             : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
                         }`}
            >
              {s.etiket}
            </button>
          )
        })}
      </div>

      <ResponsiveContainer width="100%" height={yukseklik}>
        <LineChart data={veri} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
          <XAxis
            dataKey="gun"
            tickFormatter={gunEtiketi}
            tick={{ fontSize: 11 }}
            minTickGap={24}
          />
          <YAxis
            domain={[enDusuk - pay, enYuksek + pay]}
            tickFormatter={(v: number) => kisaTl(v)}
            tick={{ fontSize: 11 }}
            width={78}
          />
          <Tooltip
            formatter={(v) => [tl(Number(v)), 'Fiyat']}
            labelFormatter={(g) => `${g}`}
            contentStyle={{ fontSize: 13, borderRadius: 8 }}
          />

          {baglam && (
            <ReferenceLine
              y={baglam.dip90}
              stroke="#16a34a"
              strokeDasharray="4 4"
              label={{ value: '90g dip', position: 'insideTopLeft', fontSize: 10 }}
            />
          )}
          {hedefFiyat != null && (
            <ReferenceLine
              y={hedefFiyat}
              stroke="#6366f1"
              strokeDasharray="6 3"
              label={{ value: 'hedefin', position: 'insideBottomLeft', fontSize: 10 }}
            />
          )}

          <Line
            type="stepAfter"
            dataKey="fiyat"
            stroke={renk}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

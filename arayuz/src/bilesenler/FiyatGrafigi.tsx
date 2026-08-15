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
 */
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

  const renk = baglam ? (SINYAL_RENGI[baglam.sinyal] ?? '#0ea5e9') : '#0ea5e9'
  const fiyatlar = gecmis.map((n) => n.fiyat)
  const enDusuk = Math.min(...fiyatlar)
  const enYuksek = Math.max(...fiyatlar)
  // Y eksenini fiyat aralığına oturt: 0'dan başlatmak, %2'lik oynamaları
  // görünmez yapar ve grafiği işe yaramaz hâle getirir.
  const pay = Math.max((enYuksek - enDusuk) * 0.15, enDusuk * 0.02)

  return (
    <ResponsiveContainer width="100%" height={yukseklik}>
      <LineChart data={gecmis} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
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
  )
}

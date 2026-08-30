/**
 * BACKLOG F2 — "Bu PC geçen ay ne kadardı" sorusunun görsel karşılığı.
 * `FiyatGrafigi.tsx` ile aynı tasarım dili (stepAfter çizgi, gün başına tek
 * nokta, referans çizgisi) ama zaman aralığı düğmeleri YOK — BACKLOG bunu
 * istemiyor, B1 zaten ürün grafiğine özel bir özellik.
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

import type { SetGecmisNoktasi } from '../api/tipler'
import { kisaTl, tl } from '../yardimcilar/bicim'

function gunEtiketi(gun: string): string {
  const [, ay, tarih] = gun.split('-')
  return `${tarih}.${ay}`
}

export default function SetGecmisGrafigi({
  gecmis,
  hedefButce,
  yukseklik = 240,
}: {
  gecmis: SetGecmisNoktasi[]
  hedefButce?: number | null
  yukseklik?: number
}) {
  const bilinenler = gecmis
    .map((n) => n.toplam)
    .filter((t): t is number => t !== null)

  if (bilinenler.length < 2) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed
                   border-slate-300 text-sm text-slate-500 dark:border-slate-700"
        style={{ height: yukseklik }}
      >
        Grafik için en az iki günlük veri gerekiyor.
      </div>
    )
  }

  const sinirlar = hedefButce != null ? [...bilinenler, hedefButce] : bilinenler
  const enDusuk = Math.min(...sinirlar)
  const enYuksek = Math.max(...sinirlar)
  // 0'dan başlatmak küçük oynamaları görünmez yapar (bkz. FiyatGrafigi).
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
          formatter={(v) => [v == null ? 'veri eksik' : tl(Number(v)), 'Toplam']}
          labelFormatter={(g) => `${g}`}
          contentStyle={{ fontSize: 13, borderRadius: 8 }}
        />

        {hedefButce != null && (
          <ReferenceLine
            y={hedefButce}
            stroke="#6366f1"
            strokeDasharray="6 3"
            label={{ value: 'bütçe', position: 'insideBottomLeft', fontSize: 10 }}
          />
        )}

        {/* `connectNulls` YOK (varsayılan false): eksik günün `toplam`ı
            `null` — çizgi burada KESİLİR, yanlış bir bağ kurulmaz. */}
        <Line
          type="stepAfter"
          dataKey="toplam"
          stroke="#0ea5e9"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

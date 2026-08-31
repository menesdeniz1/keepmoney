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
 *  • BACKLOG B3 — mağaza başına çizgi: VARSAYILAN GÖRÜNÜM BİRLEŞİK KALIR.
 *    Grafiği ilk açılışta çizgi çorbasına çevirmek, analizi cümleye çeviren
 *    üstünlüğümüzü kaybettirir — "Mağazalara ayır" düğmesiyle bilinçli
 *    olarak geçilir. Tek kaynaklı üründe (`seriler` boş, bkz. B2) düğme
 *    hiç görünmez.
 */
import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { Baglam, FiyatNoktasi, KaynakSerisi } from '../api/tipler'
import { kisaTl, tl } from '../yardimcilar/bicim'
import {
  GRAFIK_ARALIK_ANAHTARI,
  GRAFIK_ARALIK_SECENEKLERI,
  type GrafikAraligi,
  grafikAraligaGoreSuz,
  grafikAraligiYetersiz,
  grafikBaslangicAraligi,
} from '../yardimcilar/grafikAraligi'
import {
  anahtar,
  birlesikVeri,
  enUcuzKaynakId,
  gorunurFiyatAraligi,
  kaynakStili,
} from '../yardimcilar/kaynakRenkleri'
import { stokBosluklariniBul } from '../yardimcilar/stokBosluklari'

interface Props {
  gecmis: FiyatNoktasi[]
  hedefFiyat?: number | null
  baglam?: Baglam | null
  yukseklik?: number
  seriler?: KaynakSerisi[]
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
  seriler = [],
}: Props) {
  const [araligi, setAraligi] = useState<GrafikAraligi>(grafikBaslangicAraligi)
  const [ayrilmisMi, setAyrilmisMi] = useState(false)
  const [gizliKaynaklar, setGizliKaynaklar] = useState<Set<number>>(new Set())

  function araligiSec(yeni: GrafikAraligi) {
    setAraligi(yeni)
    try {
      localStorage.setItem(GRAFIK_ARALIK_ANAHTARI, yeni)
    } catch {
      // Depolama kapalıysa seçim yalnızca bu oturumda kalır — sorun değil.
    }
  }

  function kaynagiAcKapa(kaynakId: number) {
    setGizliKaynaklar((onceki) => {
      const yeni = new Set(onceki)
      if (yeni.has(kaynakId)) yeni.delete(kaynakId)
      else yeni.add(kaynakId)
      return yeni
    })
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

  // Ayrılmış görünümdeki her kaynak, AYNI zaman aralığı seçimine göre
  // süzülür (B1 düğmeleri iki görünümde de aynı işi yapar). `veri`deki AYNI
  // geri düşme kuralı KAYNAK BAŞINA da uygulanır: bir kaynağın geçmişi
  // seçili aralığın tamamen dışında kalabilir (ör. eski bir mağaza linki,
  // yeni eklenen bir kaynakla aynı üründe) — o kaynağın çizgisi sessizce
  // kaybolmak yerine kendi tam geçmişine düşer.
  const suzulmusSeriler = seriler.map((s) => {
    const suzulmus = grafikAraligaGoreSuz(s.noktalar, secilenGun)
    return { ...s, noktalar: suzulmus.length >= 2 ? suzulmus : s.noktalar }
  })
  const gorunurSeriler = suzulmusSeriler.filter((s) => !gizliKaynaklar.has(s.kaynak_id))
  const cokluVeri = birlesikVeri(suzulmusSeriler)
  const enUcuzId = enUcuzKaynakId(gorunurSeriler)

  const renk = baglam ? (SINYAL_RENGI[baglam.sinyal] ?? '#0ea5e9') : '#0ea5e9'

  // Y ekseni: ayrılmış görünümde yalnızca GÖRÜNÜR (gizlenmemiş) kaynaklara
  // göre ölçeklenir — bir mağaza gizlenince kalanlara göre daralır/genişler.
  const ayrilmisAralik = ayrilmisMi
    ? gorunurFiyatAraligi(suzulmusSeriler, gizliKaynaklar)
    : null
  // BACKLOG B4 — stok-yok günlerinin `fiyat: null`ı buraya karışırsa
  // `Math.min(...[10, null])` `null`ı 0'a çevirip aralığı bozar; süzülür.
  const bilinenFiyatlar = veri.map((n) => n.fiyat).filter((f): f is number => f != null)
  const birlesikAralik = bilinenFiyatlar.length > 0
    ? { enDusuk: Math.min(...bilinenFiyatlar), enYuksek: Math.max(...bilinenFiyatlar) }
    : { enDusuk: 0, enYuksek: 0 }

  // BACKLOG B4 — hatch deseni yalnızca BİRLEŞİK görünümde: ayrılmış
  // görünümde her çizginin KENDİ boşluğu zaten `connectNulls=false` ile
  // kesik çiziliyor, üstüne taramalı arka plan eklemek hangi boşluğun
  // hangi mağazaya ait olduğunu belirsizleştirirdi. Açıklama metni ise
  // HER İKİ görünümde de geçerli — o yüzden ikisini birlikte kontrol eder.
  const stokBosluklari = ayrilmisMi ? [] : stokBosluklariniBul(veri)
  const herhangiBirBoslukVar = stokBosluklari.length > 0
    || suzulmusSeriler.some((s) => s.noktalar.some((n) => !n.stokta))
  const { enDusuk, enYuksek } = ayrilmisMi
    ? (ayrilmisAralik ?? { enDusuk: 0, enYuksek: 0 })
    : birlesikAralik
  // Y eksenini fiyat aralığına oturt: 0'dan başlatmak, %2'lik oynamaları
  // görünmez yapar ve grafiği işe yaramaz hâle getirir.
  const pay = Math.max((enYuksek - enDusuk) * 0.15, enDusuk * 0.02)

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div
          role="group"
          aria-label="Grafik zaman aralığı"
          className="flex gap-1"
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

        {/* Tek kaynaklı üründe `seriler` boş (bkz. B2) — düğme hiç
            görünmez, kabul ölçütü tam bu. */}
        {seriler.length > 0 && (
          <button
            type="button"
            onClick={() => setAyrilmisMi((v) => !v)}
            className="text-xs font-medium text-slate-500 hover:underline
                       dark:text-slate-400"
          >
            {ayrilmisMi ? '← Birleşik görünüme dön' : 'Mağazalara ayır'}
          </button>
        )}
      </div>

      <ResponsiveContainer width="100%" height={yukseklik}>
        <LineChart data={ayrilmisMi ? cokluVeri : veri}
                   margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
          <defs>
            {/* BACKLOG B4 — "arka plana soluk tarama deseni". 45°'lik
                çizgiler; açık/karanlık temada da okunur kalsın diye orta
                gri + düşük opaklık (renge değil TEMAYA bağlı bir seçim). */}
            <pattern id="stokYokDeseni" width="6" height="6"
                     patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill="transparent" />
              <line x1="0" y1="0" x2="0" y2="6" stroke="#94a3b8" strokeWidth="2.5" />
            </pattern>
          </defs>
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
            formatter={(v, adi) => [v == null ? 'Stokta yok' : tl(Number(v)), ayrilmisMi ? adi : 'Fiyat']}
            labelFormatter={(g) => `${g}`}
            contentStyle={{ fontSize: 13, borderRadius: 8 }}
          />

          {stokBosluklari.map((a) => (
            <ReferenceArea
              key={`${a.baslangic}-${a.bitis}`}
              x1={a.baslangic}
              x2={a.bitis}
              fill="url(#stokYokDeseni)"
              fillOpacity={0.5}
              stroke="none"
              ifOverflow="visible"
            />
          ))}

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

          {ayrilmisMi ? (
            gorunurSeriler.map((s) => {
              const stil = kaynakStili(s.host, gorunurSeriler.length)
              return (
                <Line
                  key={s.kaynak_id}
                  type="stepAfter"
                  dataKey={anahtar(s.kaynak_id)}
                  name={s.host}
                  stroke={stil.renk}
                  strokeDasharray={stil.desen}
                  strokeWidth={s.kaynak_id === enUcuzId ? 3 : 1.5}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              )
            })
          ) : (
            <Line
              type="stepAfter"
              dataKey="fiyat"
              stroke={renk}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
              connectNulls={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>

      {ayrilmisMi && (
        <div
          role="group"
          aria-label="Kaynakları göster/gizle"
          className="mt-2 flex flex-wrap gap-2"
        >
          {suzulmusSeriler.map((s) => {
            const stil = kaynakStili(s.host, suzulmusSeriler.length)
            const gizli = gizliKaynaklar.has(s.kaynak_id)
            return (
              <button
                key={s.kaynak_id}
                type="button"
                aria-pressed={!gizli}
                onClick={() => kaynagiAcKapa(s.kaynak_id)}
                className={`inline-flex items-center gap-1.5 rounded px-2 py-1
                           text-xs transition ${
                             gizli
                               ? 'text-slate-400 line-through dark:text-slate-600'
                               : 'text-slate-700 dark:text-slate-300'
                           }`}
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: gizli ? '#94a3b8' : stil.renk }}
                />
                {s.host}
              </button>
            )
          })}
        </div>
      )}

      {herhangiBirBoslukVar && (
        <p className="mt-2 text-xs text-slate-400 dark:text-slate-600">
          kesik çizgi = stokta yok
        </p>
      )}
    </div>
  )
}

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

import type { Baglam, FiyatNoktasi, Kaynak, KaynakSerisi } from '../api/tipler'
import { kisaTl, tl, yuzde } from '../yardimcilar/bicim'
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
import { magazaAdi, tooltipVerisiOlustur, type TooltipVerisi } from '../yardimcilar/tooltipVerisi'

interface Props {
  gecmis: FiyatNoktasi[]
  hedefFiyat?: number | null
  baglam?: Baglam | null
  yukseklik?: number
  seriler?: KaynakSerisi[]
  // BACKLOG B5 — tooltip'te "hangi mağaza" göstermek için. Tek kaynaklı
  // üründe (`seriler` boş) BİRLEŞİK görünümde de kullanılır; çok kaynaklı
  // üründe her çizginin adı zaten kendi mağazasını taşıyor.
  kaynaklar?: Kaynak[]
}

/**
 * BACKLOG B5 — hover (fare) ve "sabitlenmiş" (dokunmatik tık) tooltip AYNI
 * kutuyu paylaşır: ıraksama olursa masaüstünde görülen ile telefonda
 * görülen farklı bilgi taşırdı.
 */
function TooltipKutusu({ gun, veriler }: { gun: string; veriler: TooltipVerisi[] }) {
  if (veriler.length === 0) return null
  return (
    <div
      className="min-w-[150px] rounded-lg border border-slate-200 bg-white p-2.5
                 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900"
    >
      <div className="font-medium text-slate-700 dark:text-slate-300">{gun}</div>
      {veriler[0]!.tumZamanlarDibiMi && (
        <div
          className="mt-1 inline-flex items-center gap-1 rounded bg-amber-100 px-1.5 py-0.5
                     text-[10px] font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        >
          🏆 tüm zamanların dibi
        </div>
      )}
      <div className="mt-1.5 space-y-1.5">
        {veriler.map((v, i) => (
          <div key={i}>
            {v.magaza && (
              <div className="text-[11px] text-slate-400 dark:text-slate-500">{v.magaza}</div>
            )}
            <div className="font-mono font-semibold text-slate-900 dark:text-slate-100">
              {v.fiyat == null ? 'Stokta yok' : tl(v.fiyat)}
            </div>
            {v.medyanFarki != null && (
              <div
                className={v.medyanFarki < 0
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-slate-500 dark:text-slate-400'}
              >
                medyana göre {yuzde(v.medyanFarki)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
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
  kaynaklar = [],
}: Props) {
  const [araligi, setAraligi] = useState<GrafikAraligi>(grafikBaslangicAraligi)
  const [ayrilmisMi, setAyrilmisMi] = useState(false)
  const [gizliKaynaklar, setGizliKaynaklar] = useState<Set<number>>(new Set())
  // BACKLOG B5 — "telefonda dokununca tooltip çıkıyor ve kaybolmuyor".
  // recharts'ın kendi hover/dokunma durumuna GÜVENMİYORUZ (dokunuşta
  // `touchend` çoğu tarayıcıda `mouseleave` gibi davranıp tooltip'i hemen
  // kapatıyor) — tıklama recharts'ta hem fare hem dokunma için AYNI, tek
  // ve güvenilir olay. Sabitlenen nokta yalnızca elle kapatılır.
  const [sabitNokta, setSabitNokta] = useState<{ gun: string; x: number; y: number } | null>(null)

  function araligiSec(yeni: GrafikAraligi) {
    setAraligi(yeni)
    setSabitNokta(null)
    try {
      localStorage.setItem(GRAFIK_ARALIK_ANAHTARI, yeni)
    } catch {
      // Depolama kapalıysa seçim yalnızca bu oturumda kalır — sorun değil.
    }
  }

  function kaynagiAcKapa(kaynakId: number) {
    setSabitNokta(null)
    setGizliKaynaklar((onceki) => {
      const yeni = new Set(onceki)
      if (yeni.has(kaynakId)) yeni.delete(kaynakId)
      else yeni.add(kaynakId)
      return yeni
    })
  }

  function grafigeTiklandi(state: { activeLabel?: string; activeCoordinate?: { x: number; y: number } }) {
    if (state?.activeLabel == null || !state.activeCoordinate) return
    const gun = state.activeLabel
    const { x, y } = state.activeCoordinate
    // Aynı noktaya tekrar dokununca kapanır — sabitlemeyi kaldırmanın en
    // doğal yolu, ayrı bir "kapat" düğmesi aramaya gerek kalmaz.
    setSabitNokta((onceki) => (onceki?.gun === gun ? null : { gun, x, y }))
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

  // BACKLOG B5 — hover VE sabitlenmiş tooltip AYNI günü AYNI şekilde
  // çözer. Ayrılmış görünümde görünür her çizgi için bir satır; birleşik
  // görünümde tek satır, mağaza YALNIZCA tek kaynaklı üründe biliniyor
  // (bkz. tooltipVerisi.ts — çok kaynaklı üründe "Mağazalara ayır" bu
  // soruyu zaten cevaplıyor).
  function noktaVerileriniOlustur(gun: string): TooltipVerisi[] {
    if (ayrilmisMi) {
      return gorunurSeriler
        .map((s) => {
          const nokta = s.noktalar.find((n) => n.gun === gun)
          if (!nokta) return null
          const kaynakBilgisi = kaynaklar.find((k) => k.id === s.kaynak_id)
          return tooltipVerisiOlustur(nokta, {
            medyan90: baglam?.medyan90,
            tumZamanlarDibiTarih: baglam?.tum_zamanlar_dibi_tarih,
            magaza: kaynakBilgisi ? magazaAdi(kaynakBilgisi) : s.host,
          })
        })
        .filter((v): v is TooltipVerisi => v !== null)
    }
    const nokta = veri.find((n) => n.gun === gun)
    if (!nokta) return []
    return [tooltipVerisiOlustur(nokta, {
      medyan90: baglam?.medyan90,
      tumZamanlarDibiTarih: baglam?.tum_zamanlar_dibi_tarih,
      magaza: kaynaklar.length === 1 ? magazaAdi(kaynaklar[0]!) : null,
    })]
  }

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

      {/* `relative` — sabitlenmiş tooltip (B5) recharts'ın verdiği piksel
          koordinatına göre BU kutunun içinde konumlanıyor. */}
      <div className="relative">
        <ResponsiveContainer width="100%" height={yukseklik}>
          <LineChart data={ayrilmisMi ? cokluVeri : veri}
                     margin={{ top: 8, right: 12, bottom: 4, left: 4 }}
                     onClick={grafigeTiklandi}>
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
          {/* BACKLOG B5 — özel içerik: recharts'ın varsayılan `formatter`ı
              yalnızca ham değeri görür, `stokta`/`medyanFarki`/`magaza`ya
              erişemez (B4'te ÖLÇÜLDÜ: null değerli satırları formatter'a
              hiç ULAŞTIRMIYOR). Sabitlenmişken hover kutusu GİZLENİR —
              ikisi aynı anda görünüp kafa karıştırmasın. */}
          <Tooltip
            content={({ active, label }) =>
              active && label != null && !sabitNokta
                ? <TooltipKutusu gun={String(label)} veriler={noktaVerileriniOlustur(String(label))} />
                : null}
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

        {/* BACKLOG B5 — sabitlenmiş tooltip: `onClick`ten gelen SVG piksel
            koordinatı bu `relative` kutunun içinde 1:1 karşılık düşer. Kenara
            taşmayı tamamen engellemek yerine kabaca ortalıyor — grafiğin
            kendisi zaten dar bir alanda (kart genişliği) çiziliyor. */}
        {sabitNokta && (
          <div
            className="pointer-events-none absolute z-10"
            style={{ left: sabitNokta.x, top: sabitNokta.y, transform: 'translate(-50%, -100%)' }}
          >
            <div className="pointer-events-auto -mt-2">
              <TooltipKutusu gun={sabitNokta.gun} veriler={noktaVerileriniOlustur(sabitNokta.gun)} />
              <button
                type="button"
                onClick={() => setSabitNokta(null)}
                className="mt-1 w-full rounded bg-slate-900/85 py-1 text-center text-[11px]
                           text-white hover:bg-slate-900 dark:bg-white/85 dark:text-slate-900
                           dark:hover:bg-white"
              >
                kapat ✕
              </button>
            </div>
          </div>
        )}
      </div>

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

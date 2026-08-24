/**
 * BACKLOG A8 kabul ölçütü: "kıvılcım ucu 500 ms gecikse bile kart
 * bozulmuyor, sıçrama olmuyor (yer önceden ayrılmış)". Bu, veri gelmeden
 * ÖNCEKİ ve SONRAKİ durumun AYNI BOYUTU tutmasıyla ölçülür — birim testin
 * doğrulayabileceği tek somut kısım bu (görsel sıçramanın kendisi ancak
 * gerçek tarayıcıda gözlemlenebilir).
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Kivilcim from '../bilesenler/Kivilcim'

describe('Kivilcim', () => {
  it('veri yokken (henüz gelmedi) sabit boyutlu boş yer tutucu döner — SVG YOK', () => {
    const { container } = render(<Kivilcim veri={undefined} sinyal={null} />)
    expect(container.querySelector('svg')).toBeNull()
    const yerTutucu = container.firstElementChild as HTMLElement
    expect(yerTutucu.style.width).toBe('56px')
    expect(yerTutucu.style.height).toBe('20px')
  })

  it('tek noktalı veride de yer tutucu döner — bir nokta çizgi oluşturmaz', () => {
    const { container } = render(<Kivilcim veri={[1000]} sinyal="dip" />)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('yer tutucunun boyutu SVG ile BİREBİR AYNI — sıçrama olmaması bunun kanıtı', () => {
    const bos = render(<Kivilcim veri={undefined} sinyal={null} />)
    const dolu = render(<Kivilcim veri={[1000, 900, 950]} sinyal="dip" />)
    const bosEl = bos.container.firstElementChild as SVGElement | HTMLElement
    const doluSvg = dolu.container.querySelector('svg')
    expect(doluSvg).not.toBeNull()
    expect(bosEl.getAttribute('width') ?? bosEl.style.width.replace('px', ''))
      .toBe(doluSvg?.getAttribute('width'))
  })

  it('yeterli veride SVG çizer, nokta sayısı kadar polyline noktası üretir', () => {
    const { container } = render(<Kivilcim veri={[1000, 950, 1100, 900]} sinyal="ucuz" />)
    const cizgi = container.querySelector('polyline')
    expect(cizgi).not.toBeNull()
    const noktalar = cizgi?.getAttribute('points')?.trim().split(' ')
    expect(noktalar?.length).toBe(4)
  })

  it('sinyale göre farklı renk sınıfı taşır', () => {
    const dip = render(<Kivilcim veri={[1000, 900]} sinyal="dip" />)
    const pahali = render(<Kivilcim veri={[1000, 900]} sinyal="pahali" />)
    const notr = render(<Kivilcim veri={[1000, 900]} sinyal={null} />)

    const sinifi = (c: HTMLElement) => c.querySelector('svg')?.getAttribute('class') ?? ''
    const uc = [dip, pahali, notr].map((r) => sinifi(r.container))
    expect(new Set(uc).size).toBe(3)
    for (const s of uc) expect(s).toMatch(/dark:/)
  })

  it('sabit fiyatta (hepsi aynı) sıfıra bölme hatası vermez', () => {
    // aralık = enYuksek - enDusuk = 0 — kod bunu `|| 1` ile koruyor.
    const { container } = render(<Kivilcim veri={[1000, 1000, 1000]} sinyal="dip" />)
    const cizgi = container.querySelector('polyline')
    expect(cizgi?.getAttribute('points')).not.toContain('NaN')
  })

  it('erişilebilirlik: role=img ve anlamlı aria-label taşır', () => {
    const { container } = render(<Kivilcim veri={[1000, 900]} sinyal="dip" />)
    const svg = container.querySelector('svg')
    expect(svg?.getAttribute('role')).toBe('img')
    expect(svg?.getAttribute('aria-label')).toBeTruthy()
  })
})

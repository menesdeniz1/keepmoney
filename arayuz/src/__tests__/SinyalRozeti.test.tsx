/**
 * BACKLOG A6 kabul ölçütleri: üç sinyal durumu + null durumu doğru
 * çiziliyor, metin ekran okuyucuya geçiyor (yalnız renk/emoji değil).
 *
 * Proje `@testing-library/react` + jsdom'u ZATEN kurmuştu (vite.config.ts,
 * package.json) ama hiç kullanmıyordu — mevcut testler yalnızca saf
 * fonksiyonları (bicim.ts, istemci.ts) sınıyordu. Bu, bir React bileşenini
 * render eden ilk test; SinyalRozeti'nin entegre olacağı IzlemeKarti henüz
 * A8'de yazılmadığı için uçtan uca (Playwright) bir sınama noktası yok —
 * bu görsel/durumsal doğruluğu ölçebilecek tek yer burası.
 *
 * `@testing-library/jest-dom` (toBeInTheDocument vb.) KURULU DEĞİL — yeni
 * bağımlılık eklemeden, ham vitest/DOM API'leriyle yazıldı: `getByText`
 * zaten bulamazsa fırlatır, `queryByText` bulamazsa `null` döner.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import SinyalRozeti from '../bilesenler/SinyalRozeti'

describe('SinyalRozeti', () => {
  it('dip sinyalini doğru metinle çizer', () => {
    render(<SinyalRozeti sinyal="dip" yuzdelik={92} gecmisGun={30} />)
    expect(screen.getByText('90 günün dibi')).toBeTruthy()
    expect(screen.getByText('· %92')).toBeTruthy()
  })

  it('ucuz sinyalini doğru metinle çizer', () => {
    render(<SinyalRozeti sinyal="ucuz" yuzdelik={60} gecmisGun={30} />)
    expect(screen.getByText('ucuz dönem')).toBeTruthy()
  })

  it('pahalı sinyalini doğru metinle çizer', () => {
    render(<SinyalRozeti sinyal="pahali" yuzdelik={10} gecmisGun={30} />)
    expect(screen.getByText('pahalı dönem')).toBeTruthy()
  })

  it('üç sinyal de FARKLI renk sınıfı taşır — yalnızca metne güvenmiyoruz', () => {
    const { container: dip } = render(
      <SinyalRozeti sinyal="dip" yuzdelik={92} gecmisGun={30} />)
    const { container: ucuz } = render(
      <SinyalRozeti sinyal="ucuz" yuzdelik={60} gecmisGun={30} />)
    const { container: pahali } = render(
      <SinyalRozeti sinyal="pahali" yuzdelik={10} gecmisGun={30} />)

    const sinifi = (c: HTMLElement) => c.querySelector('span')?.className ?? ''
    const sinifler = [dip, ucuz, pahali].map(sinifi)
    expect(new Set(sinifler).size).toBe(3)          // üçü de birbirinden farklı
    for (const s of sinifler) {
      expect(s).toMatch(/dark:/)                     // karanlık tema varyantı var
    }
  })

  it('sinyal null iken renkli rozet DEĞİL, nötr "biriktiriliyor" metni gösterir', () => {
    render(<SinyalRozeti sinyal={null} yuzdelik={null} gecmisGun={3} />)
    expect(screen.getByText('geçmiş biriktiriliyor')).toBeTruthy()
    expect(screen.getByText('· 3 gün')).toBeTruthy()
    // Sinyal metinlerinden hiçbiri yanlışlıkla görünmüyor:
    expect(screen.queryByText('90 günün dibi')).toBeNull()
    expect(screen.queryByText('pahalı dönem')).toBeNull()
  })

  it('gecmisGun null iken gün sayacı hiç gösterilmez (sahte "0 gün" değil)', () => {
    render(<SinyalRozeti sinyal={null} yuzdelik={null} gecmisGun={null} />)
    expect(screen.getByText('geçmiş biriktiriliyor')).toBeTruthy()
    expect(screen.queryByText(/gün/)).toBeNull()
  })

  it('metin gerçek DOM içeriği — yalnızca renkle/emojiyle anlatılmıyor', () => {
    // Ekran okuyucu erişilebilirliği: aria-hidden OLMAYAN düz metin.
    const { container } = render(
      <SinyalRozeti sinyal="pahali" yuzdelik={5} gecmisGun={30} />)
    const rozet = container.querySelector('span')
    expect(rozet?.getAttribute('aria-hidden')).toBeNull()
    expect(rozet?.textContent).toContain('pahalı dönem')
  })
})

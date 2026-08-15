/**
 * API istemcisi testleri — hata çevirisi ve oturum düşme olayı.
 *
 * Gerçek ağ yok: `fetch` sahteleniyor.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiHatasi, OTURUM_BITTI, api } from '../api/istemci'

function yanitVer(durum: number, govde: unknown = {}) {
  const sahte = vi.fn().mockResolvedValue({
    ok: durum >= 200 && durum < 300,
    status: durum,
    json: () => Promise.resolve(govde),
  })
  vi.stubGlobal('fetch', sahte)
  return sahte
}

afterEach(() => vi.unstubAllGlobals())

/** `fetch`e giden ayar nesnesi. Sıkı kipte indeksli erişim `undefined`
 *  olabilir; daraltmayı tek yerde yapıyoruz. */
function cagriAyari(sahte: ReturnType<typeof vi.fn>): RequestInit {
  const cagri = sahte.mock.calls[0]
  expect(cagri).toBeDefined()
  return cagri![1] as RequestInit
}

describe('hata çevirisi', () => {
  it('FastAPI metin hatasını kullanıcıya taşır', async () => {
    yanitVer(400, { detail: 'Bu ürünü zaten izliyorsun' })
    await expect(api.izlemeler()).rejects.toThrow('Bu ürünü zaten izliyorsun')
  })

  it('doğrulama hatası dizisini okunur mesaja çevirir', async () => {
    // FastAPI 422'de {detail: [{loc, msg, type}, ...]} döner; bunu ham
    // göstermek kullanıcıya hiçbir şey ifade etmez.
    yanitVer(422, { detail: [{ loc: ['body', 'url'], msg: 'invalid' }] })
    await expect(api.izlemeler()).rejects.toThrow('Girdi geçersiz')
  })

  it('gövdesiz hatada durum kodunu gösterir', async () => {
    yanitVer(500, {})
    await expect(api.izlemeler()).rejects.toThrow('(500)')
  })

  it('durum kodunu hataya taşır', async () => {
    yanitVer(404, { detail: 'yok' })
    await expect(api.izleme(1)).rejects.toMatchObject({
      durum: 404,
      name: 'ApiHatasi',
    })
    expect(new ApiHatasi('x', 1)).toBeInstanceOf(Error)
  })

  it('204 yanıtta gövde okumaya çalışmaz', async () => {
    yanitVer(204)
    await expect(api.izlemeSil(1)).resolves.toBeUndefined()
  })
})

describe('oturum düşme olayı', () => {
  it('korumalı uçtan gelen 401 olayı yayar', async () => {
    // Token uygulama açıkken dolabiliyor. Bu olay olmadan kullanıcı ekranda
    // kırık hata kutularıyla kalıyordu.
    yanitVer(401, { detail: 'Geçersiz veya eksik oturum' })
    const dinleyici = vi.fn()
    window.addEventListener(OTURUM_BITTI, dinleyici)

    await expect(api.izlemeler()).rejects.toThrow()
    expect(dinleyici).toHaveBeenCalledTimes(1)

    window.removeEventListener(OTURUM_BITTI, dinleyici)
  })

  it('yanlış paroladaki 401 olay yaymaz', async () => {
    // Aksi halde giriş ekranında yanlış parola yazmak "oturumun bitti"
    // akışını tetikler ve formu sıfırlar.
    yanitVer(401, { detail: 'E-posta veya parola hatalı' })
    const dinleyici = vi.fn()
    window.addEventListener(OTURUM_BITTI, dinleyici)

    await expect(api.giris('a@b.com', 'yanlis')).rejects.toThrow()
    expect(dinleyici).not.toHaveBeenCalled()

    window.removeEventListener(OTURUM_BITTI, dinleyici)
  })

  it('henüz giriş yapılmamışken /auth/ben olay yaymaz', async () => {
    // Uygulama açılışında oturum yoksa bu 401 BEKLENENDİR.
    yanitVer(401, { detail: 'Geçersiz veya eksik oturum' })
    const dinleyici = vi.fn()
    window.addEventListener(OTURUM_BITTI, dinleyici)

    await expect(api.ben()).rejects.toThrow()
    expect(dinleyici).not.toHaveBeenCalled()

    window.removeEventListener(OTURUM_BITTI, dinleyici)
  })
})

describe('istek biçimi', () => {
  it('oturum çerezini taşır', async () => {
    const f = yanitVer(200, [])
    await api.izlemeler()
    expect(cagriAyari(f)).toMatchObject({ credentials: 'include' })
  })

  it('gövdesiz isteğe Content-Type eklemez', async () => {
    const f = yanitVer(200, [])
    await api.izlemeler()
    const ayar = cagriAyari(f)
    expect((ayar.headers as Record<string, string>)['Content-Type']).toBeUndefined()
  })

  it('gövdeli isteği JSON olarak gönderir', async () => {
    const f = yanitVer(200, {})
    await api.izlemeGuncelle(3, { hedef_fiyat: 100 })
    const ayar = cagriAyari(f)
    expect(ayar.method).toBe('PATCH')
    expect(JSON.parse(ayar.body as string)).toEqual({ hedef_fiyat: 100 })
  })

  it('hedef fiyatı temizlemek için açık null gönderebilir', async () => {
    // Sunucu tarafında açık null "temizle" demek; arayüz bunu gönderebilmeli.
    const f = yanitVer(200, {})
    await api.izlemeGuncelle(3, { hedef_fiyat: null })
    expect(JSON.parse(cagriAyari(f).body as string))
      .toEqual({ hedef_fiyat: null })
  })
})

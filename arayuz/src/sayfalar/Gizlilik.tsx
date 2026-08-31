import { Link } from 'react-router-dom'

/**
 * Gizlilik metni — OTURUM İSTEMEZ.
 *
 * Giriş duvarının arkasındaki gizlilik metni işe yaramaz: kişi hesap
 * açmadan ÖNCE neyin toplandığını okuyabilmeli, kayıt ekranındaki onay
 * bağlantısı da buraya gidiyor.
 *
 * METNİN İÇERİĞİ KODDAN ÇIKARILDI, taslaktan değil: hangi sütunun
 * gerçekten yazıldığı `keepmoney/models.py`de, neyin silindiği
 * `servisler/kullanici.py::hesabi_sil`de, neyin dışa aktarıldığı
 * `kisisel_verileri_disa_aktar`da. Buradaki her cümlenin karşılığı
 * kodda vardır ve testlerle bağlıdır.
 *
 * HUKUKİ YETERLİLİK AYRI BİR KONUDUR. Bu metin sistemin ne yaptığını
 * DOĞRU anlatır; bir hukukçunun KVKK m.10 aydınlatma yükümlülüğü
 * açısından yeterli bulup bulmayacağı ayrıca değerlendirilmelidir
 * (bkz. docs/CALISTIRMA.md — yayın öncesi dış gereksinimler).
 */
export default function Gizlilik() {
  return (
    <HukukiSayfa baslik="Gizlilik ve Kişisel Verilerin Korunması">
      <Bolum baslik="Hangi verileri topluyoruz">
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>E-posta adresin.</strong> Hesabını tanımlamak, giriş
            yapmanı ve parolanı sıfırlamanı sağlamak için. Başka bir amaçla
            kullanılmaz, üçüncü taraflarla paylaşılmaz.
          </li>
          <li>
            <strong>Parolanın karması (hash).</strong> Parolanın kendisi
            hiçbir yerde saklanmaz; geri döndürülemez biçimde (bcrypt)
            saklanır.
          </li>
          <li>
            <strong>Takip ettiğin ürün linkleri ve fiyat hedeflerin.</strong>{' '}
            Servisin çalışması için zorunlu: bunlar olmadan hangi fiyatı
            izleyeceğimizi bilemeyiz.
          </li>
          <li>
            <strong>Telegram sohbet kimliğin</strong> — yalnızca botu kendin
            bağlarsan. Bağlantıyı istediğin an kaldırabilirsin.
          </li>
          <li>
            <strong>Sana gönderilen bildirimlerin geçmişi.</strong>
          </li>
        </ul>
      </Bolum>

      <Bolum baslik="Neyi toplamıyoruz">
        <p>
          Ad, soyad, telefon, adres, doğum tarihi veya ödeme bilgisi
          İSTEMİYORUZ ve saklamıyoruz. Reklam veya analitik amacıyla üçüncü
          taraf izleyici (tracker) kullanmıyoruz; tarayıcında yalnızca oturum
          çerezi ve senin ekran tercihlerin tutulur.
        </p>
      </Bolum>

      <Bolum baslik="Ürün fiyat geçmişi kişisel veri değildir">
        <p>
          Bir ürünün dünkü fiyatı kimseye ait değildir ve kimseyi
          tanımlamaz. Fiyat geçmişi ürün bazında, kullanıcıdan bağımsız
          tutulur; hesabını sildiğinde bu geçmiş silinmez çünkü aynı ürünü
          izleyen diğer kullanıcıların hafızasıdır. Silinen şey KİŞİYE
          BAĞLANABİLEN her şeydir.
        </p>
      </Bolum>

      <Bolum baslik="Haklarını nasıl kullanırsın">
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>Verilerine erişme ve taşıma:</strong> Ayarlar sayfasından{' '}
            <em>"Verilerimi indir"</em> ile hesabına bağlı tüm veriyi tek bir
            JSON dosyası olarak indirebilirsin.
          </li>
          <li>
            <strong>Silme:</strong> Ayarlar sayfasından{' '}
            <em>"Hesabımı sil"</em>. Hesabın, izlemelerin, setlerin ve
            bildirim geçmişin kalıcı olarak silinir. Geri alınamaz.
          </li>
          <li>
            <strong>Düzeltme:</strong> Ürün adlarını ve tüm uyarı ayarlarını
            arayüzden istediğin zaman değiştirebilirsin.
          </li>
        </ul>
      </Bolum>

      <Bolum baslik="Güvenlik">
        <p>
          Oturum bilgin yalnızca sunucunun okuyabildiği (httpOnly) bir
          çerezde tutulur; sayfadaki hiçbir betik onu okuyamaz. Parolanı
          değiştirdiğinde o ana kadar açık olan tüm oturumlar düşer.
          Parola sıfırlama ve e-posta doğrulama bağlantıları kısa ömürlü,
          tek kullanımlıktır ve veritabanında karma hâlinde saklanır.
        </p>
      </Bolum>

      <Bolum baslik="Mağaza bağlantıları">
        <p>
          Bir mağazaya gittiğinde bağlantıya ortaklık (affiliate) etiketi
          eklenmiş olabilir ve alışverişinden küçük bir komisyon alabiliriz.
          <strong> Ödediğin fiyat değişmez</strong> ve bu, hangi mağazanın en
          ucuz gösterildiğini etkilemez — sıralama yalnızca fiyata göredir.
        </p>
      </Bolum>
    </HukukiSayfa>
  )
}

export function HukukiSayfa({
  baslik,
  children,
}: {
  baslik: string
  children: React.ReactNode
}) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <Link to="/" className="text-sm text-slate-500 hover:underline">
        ← KeepMoney
      </Link>
      <h1 className="mt-4 text-2xl font-semibold">{baslik}</h1>
      <div className="mt-6 space-y-6 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        {children}
      </div>
      <p className="mt-10 border-t border-slate-200 pt-4 text-xs text-slate-400 dark:border-slate-800">
        Sorularını{' '}
        <a href="mailto:destek@keepmoney.com" className="underline">
          destek@keepmoney.com
        </a>{' '}
        adresine iletebilirsin.
      </p>
    </div>
  )
}

export function Bolum({
  baslik,
  children,
}: {
  baslik: string
  children: React.ReactNode
}) {
  return (
    <section>
      <h2 className="mb-2 font-medium text-slate-900 dark:text-slate-100">
        {baslik}
      </h2>
      {children}
    </section>
  )
}

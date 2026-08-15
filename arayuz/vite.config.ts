import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    // PWA: telefona ikon olarak eklenebilsin, çevrimdışı açılsın.
    // Elle service worker yazmak yerine plugin: önbellek geçersizleştirme
    // (bayat uygulama kabuğu) elle yazılan SW'lerin en yaygın hatasıdır.
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'KeepMoney — fiyat hafızası',
        short_name: 'KeepMoney',
        description: 'Fiyatı değil, doğru alım zamanını takip et.',
        lang: 'tr',
        theme_color: '#0f172a',
        background_color: '#f8fafc',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'ikon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'ikon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'ikon-512.png', sizes: '512x512', type: 'image/png',
            purpose: 'maskable' },
        ],
      },
      workbox: {
        // API YANITLARI ÖNBELLEĞE ALINMAZ. Fiyat verisi bayatlarsa ürünün
        // tüm iddiası çöker — kullanıcı dünkü fiyata bakıp "dip" sanır.
        // Yalnızca uygulama kabuğu çevrimdışı çalışır.
        navigateFallbackDenylist: [/^\/api/, /^\/metrics/, /^\/saglik/],
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
      },
    }),
  ],
  server: {
    port: 5173,
    // API'ye vekil: tarayıcı her şeyi aynı kaynaktan görür, böylece
    // httpOnly oturum çerezi geliştirmede de sorunsuz taşınır.
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: {
    rollupOptions: {
      output: {
        // Satıcı kodu ayrı parçada: uygulama kodu her deploy'da değişir ama
        // React/Recharts değişmez — kullanıcı onları yeniden indirmesin.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          sorgu: ['@tanstack/react-query'],
        },
      },
    },
  },
  test: { environment: 'jsdom', globals: true },
})

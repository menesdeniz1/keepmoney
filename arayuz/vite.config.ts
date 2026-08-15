import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
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

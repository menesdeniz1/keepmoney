import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Fiyatlar dakikalar mertebesinde değişir; her odaklanmada yeniden
      // çekmek sunucuyu boşuna yorar.
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: (deneme, hata) => {
        // 4xx tekrar denenmez — istemci hatasıdır, tekrar aynı sonucu verir.
        const durum = (hata as { durum?: number }).durum
        if (durum && durum >= 400 && durum < 500) return false
        return deneme < 2
      },
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)

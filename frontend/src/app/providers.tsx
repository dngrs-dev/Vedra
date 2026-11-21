import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { BrowserRouter } from 'react-router-dom';

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } }
});

/**
 * BrowserRouter → чистые адреса: / (лендинг), /map (карта), /report (отчёт).
 * Хостинг должен отдавать index.html для любых путей (SPA fallback):
 * Vercel — vercel.json, Netlify — public/_redirects (оба файла уже в проекте).
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{children}</BrowserRouter>
    </QueryClientProvider>
  );
}

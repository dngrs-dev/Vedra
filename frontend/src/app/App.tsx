import { lazy, Suspense, useEffect } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { Toaster } from '@/components/ui/Toaster';
import { pl } from '@/constants/pl';
import { LandingPage } from '@/pages/LandingPage';
import { MapPage } from '@/pages/MapPage';

const ReportPage = lazy(() => import('@/pages/ReportPage').then((module) => ({ default: module.ReportPage })));

/** Название вкладки браузера для каждой страницы (по-польски) */
const TITLES: Record<string, string> = {
  '/map': 'Vedra - Mapa',
  '/report': 'Vedra - Raport'
};
const DEFAULT_TITLE = 'Vedra - Strona główna';

export function App() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = TITLES[pathname.replace(/\/+$/, '')] ?? DEFAULT_TITLE;
  }, [pathname]);

  return (
    <>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/report" element={
          <Suspense fallback={<p className="report-wrap" role="status">{pl.backend.loadingReport}</p>}>
            <ReportPage />
          </Suspense>
        } />
        <Route path="*" element={<LandingPage />} />
      </Routes>
      <Toaster />
    </>
  );
}

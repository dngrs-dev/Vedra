import { useEffect } from 'react';
import { Route, Routes, useLocation } from 'react-router-dom';
import { Toaster } from '@/components/ui/Toaster';
import { LandingPage } from '@/pages/LandingPage';
import { MapPage } from '@/pages/MapPage';
import { ReportPage } from '@/pages/ReportPage';

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
        <Route path="/report" element={<ReportPage />} />
        <Route path="*" element={<LandingPage />} />
      </Routes>
      <Toaster />
    </>
  );
}

import { Route, Routes } from 'react-router-dom';
import { Toaster } from '@/components/ui/Toaster';
import { LandingPage } from '@/pages/LandingPage';
import { MapPage } from '@/pages/MapPage';
import { ReportPage } from '@/pages/ReportPage';

export function App() {
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

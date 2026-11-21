import { AppShell } from '@/components/layout/AppShell';
import { AnalysisPanel } from '@/features/analysis/components/AnalysisPanel';
import { ParcelMap } from '@/features/analysis/components/ParcelMap';

/** Главная: слева карта, справа форма + результаты (макет main-design). */
export function HomePage() {
  return (
    <AppShell>
      <ParcelMap />
      <AnalysisPanel />
    </AppShell>
  );
}

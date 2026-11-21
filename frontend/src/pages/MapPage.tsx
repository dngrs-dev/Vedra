import { AppShell } from '@/components/layout/AppShell';
import { AnalysisPanel } from '@/features/analysis/components/AnalysisPanel';
import { ParcelMap } from '@/features/analysis/components/ParcelMap';

/** /map — слева карта, справа форма + результаты (макет main-design). */
export function MapPage() {
  return (
    <AppShell>
      <ParcelMap />
      <AnalysisPanel />
    </AppShell>
  );
}

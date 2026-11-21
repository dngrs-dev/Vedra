import { useCallback, useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AnalysisPanel } from '@/features/analysis/components/AnalysisPanel';
import { MapIntroModal } from '@/features/analysis/components/MapIntroModal';
import { ParcelMap } from '@/features/analysis/components/ParcelMap';

/** /map — слева карта, справа форма + результаты. При входе показывается окно-инструкция. */
export function MapPage() {
  const [showIntro, setShowIntro] = useState(true);
  const closeIntro = useCallback(() => setShowIntro(false), []);

  return (
    <>
      <AppShell>
        <ParcelMap />
        <AnalysisPanel />
      </AppShell>
      {showIntro && <MapIntroModal onClose={closeIntro} />}
    </>
  );
}

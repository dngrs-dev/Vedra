import { useCallback, useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { HelpIcon } from '@/components/ui/Icons';
import { AnalysisPanel } from '@/features/analysis/components/AnalysisPanel';
import { useAnalysis } from '@/features/analysis/hooks/useAnalysis';
import { MapIntroModal } from '@/features/analysis/components/MapIntroModal';
import { MapResults } from '@/features/analysis/components/MapResults';
import { ParcelMap } from '@/features/analysis/components/ParcelMap';
import { SelectModeToggle } from '@/features/analysis/components/SelectModeToggle';
import { storageGet, storageSet } from '@/utils/storage';

/** Ключ в localStorage: пользователь попросил больше не показывать инструкцию */
const INTRO_HIDDEN_KEY = 'vedra.mapIntroHidden';

/**
 * /map - слева карта, справа форма + результаты.
 * При входе показывается окно-инструкция (если пользователь не отметил «Zapamiętaj mój wybór»).
 * Кнопка «Jak korzystać» в верхней панели открывает его снова.
 */
export function MapPage() {
  const [hidden, setHidden] = useState(() => storageGet(INTRO_HIDDEN_KEY) === '1');
  const [showIntro, setShowIntro] = useState(!hidden);
  // Gdy są wyniki, mapa jest trochę niższa - nagłówek „Co jeśli?” i analizy AI widać już na pierwszym ekranie
  const { jobs } = useAnalysis({ active: false });
  const hasResults = jobs.some((job) => job.report);

  const closeIntro = useCallback((remember: boolean) => {
    storageSet(INTRO_HIDDEN_KEY, remember ? '1' : null);
    setHidden(remember);
    setShowIntro(false);
  }, []);

  return (
    <>
      <AppShell
        headerCenter={<SelectModeToggle />}
        headerActions={
          <button type="button" className="help-btn" onClick={() => setShowIntro(true)} title="Instrukcja obsługi mapy">
            <HelpIcon />
            <span>Jak korzystać</span>
          </button>
        }
      >
        <div className={`map-col${hasResults ? ' map-col--results' : ''}`}>
          <ParcelMap />
          <MapResults />
        </div>
        <AnalysisPanel />
      </AppShell>
      {showIntro && <MapIntroModal onClose={closeIntro} initialRemember={hidden} />}
    </>
  );
}

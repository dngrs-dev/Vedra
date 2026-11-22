import { useCallback, useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { HelpIcon } from '@/components/ui/Icons';
import { AnalysisPanel } from '@/features/analysis/components/AnalysisPanel';
import { MapIntroModal } from '@/features/analysis/components/MapIntroModal';
import { ParcelMap } from '@/features/analysis/components/ParcelMap';
import { WeatherCard } from '@/features/analysis/components/WeatherCard';
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

  const closeIntro = useCallback((remember: boolean) => {
    storageSet(INTRO_HIDDEN_KEY, remember ? '1' : null);
    setHidden(remember);
    setShowIntro(false);
  }, []);

  return (
    <>
      <AppShell
        headerCenter={<WeatherCard />}
        headerActions={
          <button type="button" className="help-btn" onClick={() => setShowIntro(true)} aria-label="Jak korzystać z mapy">
            <HelpIcon />
            <span>Jak korzystać</span>
          </button>
        }
      >
        <ParcelMap />
        <AnalysisPanel />
      </AppShell>
      {showIntro && <MapIntroModal onClose={closeIntro} initialRemember={hidden} />}
    </>
  );
}

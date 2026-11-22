import { useState } from 'react';
import { ChevronIcon } from '@/components/ui/Icons';
import { ScenarioSimulator } from './ScenarioSimulator';

/**
 * «Co jeśli?» w raporcie jako rozwijany blok (jak pytanie w FAQ). Po rozwinięciu: cała symulacja i prognoza
 * oraz przycisk «Zapytaj AI» - o to, czy pytać AI, rolnik decyduje sam.
 * Symulator montuje się przy pierwszym rozwinięciu, więc zanim ktoś go otworzy, nie ma żadnych zapytań.
 */
export function ScenarioAccordion({ analysisId }: { analysisId: string }) {
  const [opened, setOpened] = useState(false);
  return (
    <details className="card scenario-acc" onToggle={(e) => { if (e.currentTarget.open) setOpened(true); }}>
      <summary>
        <span className="scenario-acc__text">
          <b>Co jeśli? Symulacja działań i prognoza AI</b>
          <small>Sprawdź, jak retencja, próchnica, międzyplony i nawadnianie zmienią zapas wody - i zapytaj AI o poradę.</small>
        </span>
        <ChevronIcon size={20} />
      </summary>
      {opened && <ScenarioSimulator analysisId={analysisId} embedded />}
    </details>
  );
}

import { useScenarioStore } from '../scenarioStore';

/** Pole wyboru obok «Pobierz PDF»: czy dołączyć symulację „Co jeśli?” (z aktualnymi suwakami) do raportu PDF. */
export function ScenarioToggle() {
  const include = useScenarioStore((s) => s.includeInPdf);
  const setInclude = useScenarioStore((s) => s.setIncludeInPdf);
  return (
    <label className="scenario-toggle scenario-toggle--compact">
      <input type="checkbox" checked={include} onChange={(e) => setInclude(e.target.checked)} />
      <span>Dołącz „Co jeśli?” do PDF</span>
    </label>
  );
}

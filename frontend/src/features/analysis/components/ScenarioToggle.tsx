import { useScenarioStore } from '../scenarioStore';

/** Галочка «Co jeśli?»: одна для экрана (под картой и в raporcie) и для PDF. */
export function ScenarioToggle({ compact = false }: { compact?: boolean }) {
  const show = useScenarioStore((s) => s.showScenarios);
  const setShow = useScenarioStore((s) => s.setShowScenarios);
  return (
    <label className={`scenario-toggle${compact ? ' scenario-toggle--compact' : ''}`}>
      <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
      <span>
        <b>Symulacja „Co jeśli?”</b>
        {!compact && <small>{show ? 'Widoczna na ekranie i w raporcie PDF.' : 'Ukryta na ekranie i w raporcie PDF.'}</small>}
      </span>
    </label>
  );
}

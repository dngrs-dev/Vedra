import { useAnalysis } from '../hooks/useAnalysis';
import { useScenarioStore } from '../scenarioStore';
import { ScenarioSimulator } from './ScenarioSimulator';
import { ScenarioToggle } from './ScenarioToggle';

/**
 * Под картой на /map: симулятор «co jeśli» и ответы AI во всю ширину (страница прокручивается).
 * Расчёт уже идёт в правой панели - здесь только читаем результат из кэша (active: false).
 */
export function MapResults() {
  const { jobs } = useAnalysis({ active: false });
  const ready = jobs.filter((job) => job.report && job.analysisId);
  const show = useScenarioStore((s) => s.showScenarios);
  if (!ready.length) return null;

  return (
    <section className="map-results" aria-label="Symulacja działań i analiza AI">
      <ScenarioToggle />
      {show && ready.map((job) => (
        <div key={job.code} className="map-results__crop">
          {ready.length > 1 && <h2 className="analysis-crop">{job.report!.crop_name_pl}</h2>}
          <ScenarioSimulator analysisId={job.analysisId!} />
        </div>
      ))}
    </section>
  );
}

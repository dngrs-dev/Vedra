import { pl } from '@/constants/pl';
import { useAnalysis } from '../hooks/useAnalysis';
import { useScenarioStore } from '../scenarioStore';
import { ScenarioSimulator } from './ScenarioSimulator';
import { ScenarioToggle } from './ScenarioToggle';

export const MAP_RESULTS_ID = 'map-results';

/** Płynne przewinięcie do symulacji „Co jeśli?” i analizy AI pod mapą (przycisk w panelu i w podpowiedzi mapy). */
export function scrollToMapResults() {
  document.getElementById(MAP_RESULTS_ID)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

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
    <section id={MAP_RESULTS_ID} className="map-results" aria-labelledby="map-results-title">
      <header className="map-results__head">
        <h2 id="map-results-title">{pl.panel.scenariosTitle}</h2>
        <p>{pl.panel.scenariosLead}</p>
      </header>
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

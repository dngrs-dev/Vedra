import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/Card';
import { getAiInsight, simulateScenarios } from '@/services/scenarioApi';
import type { AiInsight, Levers, ScenarioReport, ScenarioResult, ScenarioRisk } from '@/types/scenario';
import { fmtDate } from '@/utils/format';
import { useAiStore } from '../aiStore';
import { NO_ACTION, useScenarioStore } from '../scenarioStore';
import { useAiStatus } from '../hooks/useAiStatus';
import { AiConsentModal } from './AiConsentModal';


const RISK: Record<ScenarioRisk, { label: string; cls: string }> = {
  low: { label: 'Niskie ryzyko', cls: 'badge--ok' },
  medium: { label: 'Umiarkowane ryzyko', cls: 'badge--mid' },
  high: { label: 'Wysokie ryzyko', cls: 'badge--bad' }
};

interface Slider {
  key: keyof Levers;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
  unit: string;
}

const SLIDERS: Slider[] = [
  { key: 'retention_mm', label: 'Retencja krajobrazowa', hint: 'zastawki, oczka wodne, zatrzymanie spływu', min: 0, max: 60, step: 5, unit: 'mm' },
  { key: 'organic_matter_pct', label: 'Więcej próchnicy w glebie', hint: 'obornik, resztki, uproszczona uprawa', min: 0, max: 3, step: 0.25, unit: 'p.p.' },
  { key: 'cover_pct', label: 'Międzyplony, resztki, mulcz', hint: 'okryta powierzchnia gleby', min: 0, max: 100, step: 10, unit: '%' },
  { key: 'irrigation_limit_mm', label: 'Nawadnianie - limit wody w sezonie', hint: '0 = bez nawadniania', min: 0, max: 300, step: 10, unit: 'mm' }
];
const DOSE: Slider = { key: 'irrigation_dose_mm', label: 'Jednorazowa dawka', hint: 'netto, gdy roślina zaczyna cierpieć', min: 10, max: 50, step: 5, unit: 'mm' };

const num = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 });

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function Delta({ base, value, unit, better }: { base: number; value: number; unit: string; better: 'lower' | 'higher' }) {
  const diff = value - base;
  if (Math.abs(diff) < 0.05) return <span className="sim-delta">bez zmian</span>;
  const good = better === 'lower' ? diff < 0 : diff > 0;
  return (
    <span className={`sim-delta ${good ? 'sim-delta--good' : 'sim-delta--bad'}`}>
      {diff > 0 ? '+' : '-'}{num.format(Math.abs(diff))} {unit}
    </span>
  );
}

function Chart({ base, custom }: { base: ScenarioResult; custom: ScenarioResult }) {
  const W = 320;
  const H = 120;
  const n = Math.max(base.series.length, custom.series.length);
  if (n < 2) return null;
  const line = (r: ScenarioResult) =>
    r.series.map((p, i) => `${((i / (n - 1)) * W).toFixed(1)},${(H - (p.available_pct / 100) * H).toFixed(1)}`).join(' ');
  const first = base.series[0]?.day;
  const last = base.series[base.series.length - 1]?.day;
  return (
    <figure className="sim-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
        aria-label="Zapas wody dostępnej w glebie: bez działań i w Twoim wariancie">
        {[25, 50, 75].map((y) => (
          <line key={y} x1="0" x2={W} y1={H - (y / 100) * H} y2={H - (y / 100) * H} className="sim-chart__grid" />
        ))}
        <polyline points={line(base)} className="sim-chart__base" />
        <polyline points={line(custom)} className="sim-chart__custom" />
      </svg>
      <figcaption>
        <span><i className="sim-lg sim-lg--base" />Bez działań</span>
        <span><i className="sim-lg sim-lg--custom" />Twój wariant</span>
        <span className="muted">{first && fmtDate(first)} - {last && fmtDate(last)} · zapas wody w glebie (%)</span>
      </figcaption>
    </figure>
  );
}

function Comparison({ data }: { data: ScenarioReport }) {
  const b = data.baseline.outcome;
  const c = data.custom.outcome;
  return (
    <div className="sim-compare">
      <div className="sim-col">
        <h3>Bez działań</h3>
        <span className={`badge ${RISK[b.risk].cls}`}>{RISK[b.risk].label}</span>
        <dl className="factors">
          <div><dt>Dni ze stresem wodnym</dt><dd>{b.stress_days} z {b.days}</dd></div>
          <div><dt>Niedobór wody dla uprawy</dt><dd>{num.format(b.et_deficit_pct)}%</dd></div>
          <div><dt>Najniższy zapas wody</dt><dd>{num.format(b.min_available_pct)}%</dd></div>
        </dl>
      </div>
      <div className="sim-col sim-col--custom">
        <h3>Twój wariant</h3>
        <span className={`badge ${RISK[c.risk].cls}`}>{RISK[c.risk].label}</span>
        <dl className="factors">
          <div><dt>Dni ze stresem wodnym</dt><dd>{c.stress_days} <Delta base={b.stress_days} value={c.stress_days} unit="dni" better="lower" /></dd></div>
          <div><dt>Niedobór wody dla uprawy</dt><dd>{num.format(c.et_deficit_pct)}% <Delta base={b.et_deficit_pct} value={c.et_deficit_pct} unit="p.p." better="lower" /></dd></div>
          <div><dt>Najniższy zapas wody</dt><dd>{num.format(c.min_available_pct)}% <Delta base={b.min_available_pct} value={c.min_available_pct} unit="p.p." better="higher" /></dd></div>
        </dl>
      </div>
    </div>
  );
}

function Budget({ data }: { data: ScenarioReport }) {
  const b = data.baseline.outcome.budget;
  const c = data.custom.outcome.budget;
  const rows: [string, number, number][] = [
    ['Opad', b.precipitation_mm, c.precipitation_mm],
    ['Nawadnianie', b.irrigation_mm, c.irrigation_mm],
    ['Woda oddana z retencji', b.retention_release_mm, c.retention_release_mm],
    ['Zużycie wody przez uprawę (ET)', b.actual_et_mm, c.actual_et_mm],
    ['Ucieka poza strefę korzeni', b.losses_mm, c.losses_mm],
    ['Zatrzymane przez retencję', b.retained_mm, c.retained_mm]
  ];
  return (
    <table className="sim-table">
      <thead><tr><th>Bilans wody (mm)</th><th>Bez działań</th><th>Twój wariant</th></tr></thead>
      <tbody>
        {rows.map(([label, base, custom]) => (
          <tr key={label}><td>{label}</td><td>{num.format(base)}</td><td>{num.format(custom)}</td></tr>
        ))}
        <tr className="muted"><td>Woda dostępna w strefie korzeni (pojemność)</td><td>{num.format(data.baseline.taw_mm)}</td><td>{num.format(data.custom.taw_mm)}</td></tr>
      </tbody>
    </table>
  );
}

function Presets({ data, onPick }: { data: ScenarioReport; onPick: (levers: Levers) => void }) {
  const base = data.baseline.outcome;
  const worst = Math.max(base.stress_days, 1);
  return (
    <table className="sim-table sim-presets">
      <thead><tr><th>Działanie</th><th>Dni stresu</th><th>Niedobór</th><th /></tr></thead>
      <tbody>
        <tr className="muted"><td>Bez działań</td><td>{base.stress_days}</td><td>{num.format(base.et_deficit_pct)}%</td><td /></tr>
        {data.presets.map((p) => (
          <tr key={p.id}>
            <td>
              <b>{p.title_pl}</b>
              <div className="sim-bar"><i style={{ width: `${(p.outcome.stress_days / worst) * 100}%` }} /></div>
              <small className="muted">{p.description_pl}</small>
            </td>
            <td>{p.outcome.stress_days}</td>
            <td>{num.format(p.outcome.et_deficit_pct)}%</td>
            <td><button type="button" className="link-btn" onClick={() => onPick(p.levers)}>Ustaw</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function AiPanel({ insight }: { insight: AiInsight }) {
  return (
    <div className="sim-ai__body">
      <p className="sim-ai__source">
        {insight.source === 'llm' ? `Analiza AI · ${insight.model ?? 'Claude'}` : 'Podsumowanie automatyczne (bez AI)'}
      </p>
      {insight.note_pl && <p className="muted small">{insight.note_pl}</p>}
      <p className="sim-ai__headline">{insight.headline_pl}</p>
      <dl className="sim-ai__list">
        <dt>Prognoza bez działań</dt><dd>{insight.forecast_pl}</dd>
        <dt>Co zrobić</dt><dd>{insight.best_action_pl}</dd>
      </dl>
      <ul>{insight.reasoning_pl.map((r) => <li key={r}>{r}</li>)}</ul>
      {insight.caveats_pl.length > 0 && (
        <p className="muted small">Ograniczenia: {insight.caveats_pl.join(' ')}</p>
      )}
    </div>
  );
}

/** «Co jeśli?» - как меняется риск засухи и водный баланс при разных действиях фермера + комментарий ИИ. */
export function ScenarioSimulator({ analysisId }: { analysisId: string }) {
  // Общие для карты, страницы raportu и PDF (галочка «Dołącz do PDF»)
  const levers = useScenarioStore((s) => s.levers[analysisId] ?? NO_ACTION);
  const storeLevers = useScenarioStore((s) => s.setLevers);
  const setLevers = (next: Levers | ((prev: Levers) => Levers)) =>
    storeLevers(analysisId, typeof next === 'function' ? next(levers) : next);
  const debounced = useDebounced(levers, 350);
  const [askedFor, setAskedFor] = useState<Levers | null>(null);
  const [consentOpen, setConsentOpen] = useState(false);
  const aiEnabled = useAiStore((s) => s.enabled);
  const consentFor = useAiStore((s) => s.consentFor);
  const grantConsent = useAiStore((s) => s.grantConsent);
  const { data: aiStatus } = useAiStatus();
  // RODO: dane trafiają do zewnętrznej usługi tylko po zgodzie na tego konkretnego dostawcę
  const needsConsent = !!aiStatus?.external;
  const consented = needsConsent && consentFor === aiStatus.provider;

  const sim = useQuery({
    queryKey: ['scenarios', analysisId, debounced],
    queryFn: ({ signal }) => simulateScenarios(analysisId, debounced, signal),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false
  });

  const ai = useQuery({
    queryKey: ['ai-insight', analysisId, askedFor],
    queryFn: ({ signal }) => getAiInsight(analysisId, askedFor!, consented, signal),
    enabled: askedFor !== null,
    staleTime: Infinity,
    retry: false
  });

  const set = (key: keyof Levers, value: number) => setLevers((prev) => ({ ...prev, [key]: value }));
  const render = (s: Slider) => (
    <label className="sim-slider" key={s.key}>
      <span className="sim-slider__head">
        <b>{s.label}</b>
        <output>{s.key === 'organic_matter_pct' ? `+${num.format(levers[s.key])}` : num.format(levers[s.key])} {s.unit}</output>
      </span>
      <input type="range" min={s.min} max={s.max} step={s.step} value={levers[s.key]}
        onChange={(e) => set(s.key, Number(e.target.value))} />
      <small className="muted">{s.hint}</small>
    </label>
  );

  const data = sim.data;
  const aiStale = askedFor !== null && JSON.stringify(askedFor) !== JSON.stringify(levers);

  return (
    <Card title="Co jeśli? Symulator działań" className="sim">
      <p className="muted small">
        Sprawdź, jak zmieni się ryzyko suszy i bilans wody na polu, gdy zatrzymasz więcej wody, poprawisz glebę,
        okryjesz ją lub zaczniesz nawadniać. Porównanie z wariantem „bez działań”.
      </p>

      <div className="sim-sliders">
        {SLIDERS.map(render)}
        {levers.irrigation_limit_mm > 0 && render(DOSE)}
      </div>
      <div className="sim-actions">
        <button type="button" className="link-btn" onClick={() => setLevers(NO_ACTION)}>Wyzeruj</button>
        {sim.isFetching && <span className="muted small"><span className="spinner" /> Liczę…</span>}
      </div>

      {sim.isError && <p role="alert" className="sim-error">{sim.error.message}</p>}
      {data && (
        <>
          <Comparison data={data} />
          {data.custom.levers.retention_mm > 0 && data.custom.outcome.budget.retained_mm === 0 && (
            <p className="muted small">
              W tym okresie deszcz nie dał nadwyżek wody do zatrzymania, więc retencja nic nie zmienia.
              Działa w mokrych okresach - zatrzymuje wodę z ulew i roztopów na później.
            </p>
          )}
          <Chart base={data.baseline} custom={data.custom} />
          <details className="sim-details" open>
            <summary>Bilans wody na polu</summary>
            <Budget data={data} />
            <p className="muted small">{data.kbw_note_pl}</p>
          </details>
          <details className="sim-details">
            <summary>Porównaj pojedyncze działania</summary>
            <Presets data={data} onPick={setLevers} />
          </details>
          <details className="sim-details">
            <summary>Okres i założenia modelu</summary>
            <p className="small">{fmtDate(data.window_start)} - {fmtDate(data.window_end)}. {data.window_note_pl}</p>
            <ul className="small">{data.assumptions_pl.map((a) => <li key={a}>{a}</li>)}</ul>
          </details>
        </>
      )}

      {aiEnabled ? (
      <section className="sim-ai">
        <div className="sim-ai__head">
          <h3>Prognoza i porada AI</h3>
          <button type="button" className="btn-primary" disabled={ai.isFetching || !data}
            onClick={() => (needsConsent && !consented ? setConsentOpen(true) : setAskedFor(levers))}>
            {ai.isFetching ? 'AI analizuje…' : askedFor ? 'Zapytaj ponownie' : 'Zapytaj AI'}
          </button>
        </div>
        {!askedFor && (
          <p className="muted small">
            Model językowy przeczyta raport i wyniki symulacji, a potem napisze prostą prognozę i poradę dla Twojego pola.
            {needsConsent && !consented && ` Przed wysłaniem poprosimy o zgodę na przekazanie danych do ${aiStatus.provider_name}.`}
          </p>
        )}
        {ai.isFetching && <p className="muted small"><span className="spinner" /> To może potrwać do minuty…</p>}
        {ai.isError && <p role="alert" className="sim-error">{ai.error.message}</p>}
        {ai.data && !ai.isFetching && (
          <>
            {aiStale && <p className="muted small">Suwaki zmieniły się od ostatniego pytania - zapytaj ponownie, aby uwzględnić nowy wariant.</p>}
            <AiPanel insight={ai.data} />
          </>
        )}
      </section>
      ) : (
        <p className="muted small sim-ai-off">Analiza AI jest wyłączona - włączysz ją przełącznikiem „Analiza AI” w panelu po prawej.</p>
      )}
      {consentOpen && aiStatus && (
        <AiConsentModal
          status={aiStatus}
          onCancel={() => setConsentOpen(false)}
          onAccept={() => {
            grantConsent(aiStatus.provider);
            setConsentOpen(false);
            setAskedFor(levers);
          }}
        />
      )}
    </Card>
  );
}

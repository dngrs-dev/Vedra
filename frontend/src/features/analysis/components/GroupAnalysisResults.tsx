import { Card } from '@/components/ui/Card';
import { pl } from '@/constants/pl';
import type { AnalysisJob } from '../hooks/useAnalysis';
import { useAnalysisStore } from '../store';

const balance = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 });

function comparableResults(jobs: AnalysisJob[]) {
  const byCropAndPeriod = new Map<string, { job: AnalysisJob; value: string; verdict: string }[]>();
  for (const job of jobs) {
    const kbw = job.report?.assessment.kbw;
    if (!kbw?.period || kbw.kbw_mm === null || (kbw.verdict !== 'drought' && kbw.verdict !== 'no_drought')) continue;
    const key = JSON.stringify([job.code, kbw.period.start, kbw.period.end]);
    const rows = byCropAndPeriod.get(key) ?? [];
    rows.push({ job, value: balance.format(kbw.kbw_mm), verdict: pl.backend.verdict[kbw.verdict] });
    byCropAndPeriod.set(key, rows);
  }

  // Only show differences that the reader can see at the report's display precision.
  return [...byCropAndPeriod.values()].flatMap((rows) => (
    new Set(rows.map(({ value, verdict }) => `${value} ${verdict}`)).size > 1 ? rows : []
  ));
}

export function GroupAnalysisResults({ jobs, parcelId, showComparison = true }: {
  jobs: AnalysisJob[];
  parcelId: string | undefined;
  showComparison?: boolean;
}) {
  const setChosen = useAnalysisStore((state) => state.setResultParcelId);
  const parcels = [...new Set(jobs.map((job) => job.parcelId))];
  if (!parcels.length) return null;

  const completed = jobs.filter((job) => job.report);
  const failures = jobs.filter((job) => job.error);
  const failedParcels = new Set(failures.map(({ parcelId }) => parcelId));
  const offSeason = showComparison && completed.length > 0 && completed.every((job) => job.report?.assessment.kbw.verdict === 'off_season');
  const comparison = showComparison ? comparableResults(completed) : [];
  const { batch: copy } = pl;

  return (
    <Card title={copy.title} className="batch-summary">
      <p role="status">{copy.summary(completed.length, jobs.length, failures.length)}</p>
      {offSeason && <p className="muted">{copy.offSeason}</p>}
      <label className="batch-parcel">
        {copy.selectedParcel}
        <select className="input" value={parcelId} onChange={(event) => setChosen(event.target.value)}>
          {parcels.map((id) => <option key={id} value={id}>{id}{failedParcels.has(id) && ` · ${copy.failed}`}</option>)}
        </select>
      </label>
      {comparison.length > 0 && (
        <details>
          <summary>{copy.compare}</summary>
          <div className="batch-table-wrap">
            <table className="batch-table">
              <thead><tr><th scope="col">{copy.parcel}</th><th scope="col">{copy.crop}</th><th scope="col">{copy.result}</th></tr></thead>
              <tbody>
                {comparison.map(({ job, value, verdict }) => (
                  <tr key={`${job.parcelId}:${job.code}`}>
                    <td><button type="button" className="link-btn" onClick={() => setChosen(job.parcelId)}>{job.parcelId}</button></td>
                    <td>{job.report?.crop_name_pl ?? job.names.join(', ')}</td>
                    <td>{value}{'\u00a0mm'} · {verdict}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </Card>
  );
}

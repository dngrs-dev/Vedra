import type { ReactNode } from 'react';
import { Card } from '@/components/ui/Card';
import { pl } from '@/constants/pl';
import type { AnalysisJob } from '../hooks/useAnalysis';
import { useAnalysisStore } from '../store';

const balance = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 });

export function GroupAnalysisResults({ jobs, group, children }: {
  jobs: AnalysisJob[];
  group: boolean;
  children: (visible: AnalysisJob[]) => ReactNode;
}) {
  const chosen = useAnalysisStore((state) => state.resultParcelId);
  const setChosen = useAnalysisStore((state) => state.setResultParcelId);
  const parcels = [...new Set(jobs.map((job) => job.parcelId))];
  if (!group || !parcels.length) return children(jobs);

  const completed = jobs.filter((job) => job.report);
  const failed = jobs.filter((job) => job.error).length;
  const current = chosen && parcels.includes(chosen) ? chosen : completed[0]?.parcelId ?? parcels[0];
  const { batch: copy } = pl;

  return (
    <>
      <Card title={copy.title} className="batch-summary">
        <p role="status">{copy.summary(completed.length, jobs.length, failed)}</p>
        <label className="batch-parcel">
          {copy.selectedParcel}
          <select className="input" value={current} onChange={(event) => setChosen(event.target.value)}>
            {parcels.map((id) => <option key={id}>{id}</option>)}
          </select>
        </label>
        <details>
          <summary>{copy.compare}</summary>
          <div className="batch-table-wrap">
            <table className="batch-table">
              <thead><tr><th scope="col">{copy.parcel}</th><th scope="col">{copy.crop}</th><th scope="col">{copy.result}</th></tr></thead>
              <tbody>
                {jobs.map((job) => {
                  const kbw = job.report?.assessment.kbw;
                  const result = kbw ? [
                    kbw.kbw_mm !== null ? `${balance.format(kbw.kbw_mm)}\u00a0mm` : null,
                    pl.backend.verdict[kbw.verdict]
                  ].filter(Boolean).join(' · ') : job.error ? copy.failed : job.queued ? copy.waiting : copy.running;
                  return (
                    <tr key={`${job.parcelId}:${job.code}`}>
                      <td><button type="button" className="link-btn" onClick={() => setChosen(job.parcelId)}>{job.parcelId}</button></td>
                      <td>{job.report?.crop_name_pl ?? job.names.join(', ')}</td>
                      <td>{result}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      </Card>
      {children(jobs.filter((job) => job.parcelId === current))}
    </>
  );
}

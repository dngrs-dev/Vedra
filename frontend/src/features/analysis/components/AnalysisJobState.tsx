import { Card } from '@/components/ui/Card';
import { pl } from '@/constants/pl';
import type { AnalysisJob } from '../hooks/useAnalysis';
import { AnalysisProgress } from './AnalysisProgress';

export function AnalysisError({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <Card title={pl.error.title} className="card--error">
      <p role="alert">{message}</p>
      {retry && <button type="button" className="btn-secondary" onClick={retry}>{pl.error.retry}</button>}
    </Card>
  );
}

export function AnalysisJobState({ job }: { job: AnalysisJob }) {
  return job.error
    ? <AnalysisError message={job.error} retry={job.retry} />
    : <AnalysisProgress progress={job.progress} />;
}

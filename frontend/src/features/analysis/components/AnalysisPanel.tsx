import { useNavigate } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { pl } from '@/constants/pl';
import { useAnalysis } from '../hooks/useAnalysis';
import { useAnalysisStore } from '../store';
import { AnalysisError, AnalysisJobState } from './AnalysisJobState';
import { AnalysisProgress } from './AnalysisProgress';
import { KbwAssessmentCards } from './BackendReportCards';
import { CropSelect } from './CropSelect';
import { DateField } from './DateField';
import { GroupAnalysisResults } from './GroupAnalysisResults';

export function AnalysisPanel() {
  const parcel = useAnalysisStore((s) => s.parcel);
  const confirmed = useAnalysisStore((s) => s.confirmed);
  const confirm = useAnalysisStore((s) => s.confirm);
  const unconfirm = useAnalysisStore((s) => s.unconfirm);
  const { demo, demoMode, isGroup, jobs, resultParcelId, visibleJobs, selectionError } = useAnalysis();
  const navigate = useNavigate();

  if (!confirmed) {
    return (
      <aside className="panel" aria-label="Parametry analizy">
        <form className="panel-stage panel-setup" onSubmit={(event) => { event.preventDefault(); confirm(); }}>
          <div className="field">
            <label className="field__label" id="cropLabel">{pl.form.crop}</label>
            <CropSelect />
          </div>
          <DateField />
          <button type="submit" className="btn-primary btn-block" disabled={!parcel}
            aria-describedby={parcel ? undefined : 'panel-choose-parcel'}>
            {parcel?.parts ? pl.batch.confirm : pl.confirm.button}
          </button>
          {!parcel && <p id="panel-choose-parcel" className="muted small">{pl.panel.chooseParcel}</p>}
        </form>
      </aside>
    );
  }

  const pendingJobs = jobs.filter((job) => !job.report && !job.error);
  const running = pendingJobs.find((job) => !job.queued && job.progress.length > 0) ?? pendingJobs[0];
  if ((demoMode && demo.isPending) || running) {
    return (
      <aside className="panel" aria-label="Postęp analizy">
        <div className="panel-stage">
          <AnalysisProgress progress={running?.progress} compact />
        </div>
      </aside>
    );
  }

  const reportReady = !!demo.data || jobs.some((job) => job.report);
  return (
    <aside className="panel" aria-label="Wyniki analizy">
      <div className="panel-results">
        {selectionError && <AnalysisError message={selectionError} />}
        {demoMode && demo.isError && <AnalysisError message={demo.error.message} retry={() => void demo.refetch()} />}
        {demoMode && demo.data && (
          <div className="results">
            <div className="demo-banner" role="note">{pl.demoBanner}</div>
            <Card title={pl.backend.kbw}><p>{pl.backend.verdict.unavailable}</p></Card>
            <Card title={pl.backend.history}><p>{pl.backend.noHistory}</p></Card>
          </div>
        )}
        {isGroup && <GroupAnalysisResults jobs={jobs} parcelId={resultParcelId} showComparison={false} />}
        {visibleJobs.map((job) => (
          <section key={`${job.parcelId}:${job.code}`} className="results">
            {visibleJobs.length > 1 && (
              <h2 className="analysis-crop">{job.report?.crop_name_pl ?? job.names.join(', ')}</h2>
            )}
            {job.report ? <KbwAssessmentCards report={job.report} compact /> : <AnalysisJobState job={job} />}
          </section>
        ))}
      </div>
      <div className="panel-next">
        <button type="button" className="link-btn" onClick={unconfirm}>{pl.panel.changeInputs}</button>
        {reportReady && (
          <button type="button" className="btn-primary btn-block" onClick={() => navigate('/report')}>
            {pl.panel.openReport}
          </button>
        )}
      </div>
    </aside>
  );
}

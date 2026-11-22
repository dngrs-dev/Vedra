import { VedraMark } from '@/components/ui/Icons';
import { pl } from '@/constants/pl';
import { useAnalysis } from '../hooks/useAnalysis';
import { useAnalysisStore } from '../store';
import { AnalysisError, AnalysisJobState } from './AnalysisJobState';
import { AnalysisProgress } from './AnalysisProgress';
import { BackendReportCards } from './BackendReportCards';
import { BasisCard } from './BasisCard';
import { CropSelect } from './CropSelect';
import { DateField } from './DateField';
import { MoistureCard } from './MoistureCard';
import { RecommendationsCard } from './RecommendationsCard';
import { ScenarioSimulator } from './ScenarioSimulator';

/**
 * Правая панель. Состояния:
 *  1) делянка не выбрана → подсказка
 *  2) выбрана, не подтверждена → карточка + «Potwierdź działkę»
 *  3) подтверждена → прогресс / ошибка / результаты (расчёт на бэкенде)
 */
export function AnalysisPanel() {
  const parcel = useAnalysisStore((s) => s.parcel);
  const confirmed = useAnalysisStore((s) => s.confirmed);
  const confirm = useAnalysisStore((s) => s.confirm);
  const unconfirm = useAnalysisStore((s) => s.unconfirm);
  const { demo, demoMode, jobs, selectionError } = useAnalysis();

  return (
    <aside className="panel" aria-label="Wyniki analizy">
      <div className="field">
        <label className="field__label" id="cropLabel">{pl.form.crop}</label>
        <CropSelect />
      </div>
      <DateField />

      {!parcel && (
        <div className="empty">
          <VedraMark size={56} />
          <p>{pl.empty}</p>
          <p className="empty__tip">{pl.confirm.ctrlTip}</p>
        </div>
      )}

      {parcel?.parts && (
        <div className="parcel-chip parcel-chip--group">
          <span className="muted">{pl.confirm.group}</span>
          <strong>{parcel.parts.length}</strong>
          <span className="parcel-chip__area">{parcel.areaHa} ha</span>
          <details className="parcel-list">
            <summary>{pl.confirm.showList}</summary>
            <ul>
              {parcel.parts.map((p) => (
                <li key={p.id}><span>{p.id}</span><span className="muted">{p.areaHa} ha</span></li>
              ))}
            </ul>
          </details>
        </div>
      )}

      {parcel && !parcel.parts && (
        <div className="parcel-chip">
          <span className="muted">{parcel.isCustom ? pl.confirm.custom : pl.confirm.selected}</span>
          <strong>{parcel.isCustom ? `${parcel.areaHa} ha` : parcel.id}</strong>
          <span className="parcel-chip__area">{parcel.isCustom ? '' : `${parcel.areaHa} ha`}</span>
        </div>
      )}

      {parcel && !confirmed && (
        <div className="confirm">
          <button type="button" className="btn-primary btn-block" onClick={confirm}>{pl.confirm.button}</button>
          <p className="muted small">{pl.confirm.tip}</p>
        </div>
      )}

      {confirmed && (
        <button type="button" className="link-btn" onClick={unconfirm}>← {pl.confirm.change}</button>
      )}

      {selectionError && <AnalysisError message={selectionError} />}
      {confirmed && demoMode && demo.isError && (
        <AnalysisError message={demo.error.message} retry={() => void demo.refetch()} />
      )}

      {confirmed && demoMode && demo.isPending && <AnalysisProgress />}

      {confirmed && demo.data && (
        <div className="results">
          <div className="demo-banner" role="note">{pl.demoBanner}</div>
          <MoistureCard data={demo.data} />
          <RecommendationsCard data={demo.data} />
          <BasisCard data={demo.data} />
        </div>
      )}

      {jobs.map((job) => (
        <section key={job.code} className="results">
          <h2 className="analysis-crop">{job.report?.crop_name_pl ?? job.names.join(', ')}</h2>
          {job.report ? <BackendReportCards report={job.report} /> : <AnalysisJobState job={job} />}
          {job.report && job.analysisId && <ScenarioSimulator analysisId={job.analysisId} />}
        </section>
      ))}
    </aside>
  );
}

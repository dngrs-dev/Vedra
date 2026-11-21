import { Card } from '@/components/ui/Card';
import { DropIcon } from '@/components/ui/Icons';
import { pl } from '@/constants/pl';
import { useAnalysis } from '../hooks/useAnalysis';
import { useAnalysisStore } from '../store';
import { AnalysisProgress } from './AnalysisProgress';
import { BasisCard } from './BasisCard';
import { CropSelect } from './CropSelect';
import { DateField } from './DateField';
import { MoistureCard } from './MoistureCard';
import { RecommendationsCard } from './RecommendationsCard';

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
  const { data, isError, error, refetch, isPlaceholderData } = useAnalysis();

  return (
    <aside className="panel" aria-label="Wyniki analizy">
      <div className="field">
        <label className="field__label" id="cropLabel">{pl.form.crop}</label>
        <CropSelect />
      </div>
      <DateField />

      {!parcel && (
        <div className="empty">
          <DropIcon />
          <p>{pl.empty}</p>
          <p className="empty__tip">{pl.confirm.ctrlTip}</p>
        </div>
      )}

      {parcel && (
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

      {confirmed && isError && (
        <Card title={pl.error.title} className="card--error">
          <p>{error instanceof Error ? error.message : 'Nieznany błąd'}</p>
          <button type="button" className="btn-secondary" onClick={() => void refetch()}>{pl.error.retry}</button>
        </Card>
      )}

      {confirmed && !isError && !data && <AnalysisProgress />}

      {confirmed && data && (
        <div className={`results${isPlaceholderData ? ' is-stale' : ''}`}>
          {data.isDemo && <div className="demo-banner" role="note">{pl.demoBanner}</div>}
          <MoistureCard data={data} />
          <RecommendationsCard data={data} />
          <BasisCard data={data} />
        </div>
      )}
    </aside>
  );
}

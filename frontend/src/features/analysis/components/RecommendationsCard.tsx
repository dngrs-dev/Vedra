import { Card } from '@/components/ui/Card';
import { pl } from '@/constants/pl';
import type { Analysis, Recommendation } from '@/types/analysis';
import { fmtDate } from '@/utils/format';
import { PriorityBadge } from './Badges';

function RecoList({ title, items }: { title: string; items: Recommendation[] }) {
  if (!items.length) return null;
  return (
    <div className="reco">
      <h3>{title}</h3>
      <ul className="reco__list">
        {items.map((r) => (
          <li key={r.id}>
            <div className="reco__head">
              <strong>{r.title}</strong>
              <PriorityBadge value={r.priority} />
            </div>
            <p>{r.text}</p>
            <details className="why">
              <summary>{pl.reco.why}</summary>
              <p>{r.evidence}</p>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RecommendationsCard({ data }: { data: Analysis }) {
  const { retention, agrotechnical, irrigation } = data.recommendations;
  return (
    <Card title={pl.reco.title}>
      <RecoList title={pl.reco.retention} items={retention} />
      <RecoList title={pl.reco.agro} items={agrotechnical} />

      <div className="reco">
        <h3>{pl.reco.irrigation}</h3>
        <p>{irrigation.summary}</p>
        {irrigation.amountMm !== null && <p className="muted">Orientacyjna dawka: ok. {irrigation.amountMm} mm</p>}
      </div>
      <div className="reco reco--inline">
        <h3>{pl.reco.date}</h3>
        <b>{irrigation.optimalDate ? fmtDate(irrigation.optimalDate) : pl.reco.none}</b>
      </div>
    </Card>
  );
}

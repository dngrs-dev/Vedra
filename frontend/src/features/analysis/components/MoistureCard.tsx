import { Card } from '@/components/ui/Card';
import { Gauge } from '@/components/charts/Gauge';
import { HistoryChart } from '@/components/charts/HistoryChart';
import { MONTHS_PL, pl } from '@/constants/pl';
import type { Analysis } from '@/types/analysis';
import { ConfidenceBadge, RiskText, StateText } from './Badges';

export function MoistureCard({ data }: { data: Analysis }) {
  const months = data.criticalMonths.map((m) => MONTHS_PL[m - 1]).filter(Boolean);

  return (
    <Card title={pl.moisture.title}>
      <div className="status-line">
        <span>{pl.moisture.current}</span>
        <StateText value={data.state} />
      </div>

      <div className="moisture">
        <HistoryChart data={data.history} />

        <div className="moisture__side">
          <div className="kv">
            <span>{pl.moisture.avgRisk}</span>
            <RiskText value={data.droughtRisk.level} />
          </div>
          <div className="kv">
            <span>{pl.moisture.soil}</span>
            <Gauge value={data.soilMoisturePct} />
          </div>
        </div>
      </div>

      <div className="legend">
        <span><i className="lg lg--blue" />{pl.moisture.legendMoisture}</span>
        <span><i className="lg lg--orange" />{pl.moisture.legendRisk}</span>
      </div>

      {months.length > 0 && (
        <p className="note">
          {pl.moisture.critical} <b>{months.join(', ')}</b>
        </p>
      )}
      <div className="card__foot"><ConfidenceBadge value={data.confidence} /></div>
    </Card>
  );
}

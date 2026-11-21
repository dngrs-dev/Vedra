import { pl } from '@/constants/pl';
import type { Confidence, DroughtRiskLevel, Priority, SourceStatus, WaterState } from '@/types/analysis';

const stateTone: Record<WaterState, string> = { optimal: 'ok', attention: 'mid', critical: 'bad' };
const riskTone: Record<DroughtRiskLevel, string> = { low: 'ok', moderate: 'mid', high: 'bad' };
const confTone: Record<Confidence, string> = { high: 'ok', medium: 'mid', low: 'bad' };
const prioTone: Record<Priority, string> = { high: 'bad', medium: 'mid', low: 'ok' };
const srcTone: Record<SourceStatus, string> = { live: 'ok', cached: 'mid', unavailable: 'bad' };

export const StateText = ({ value }: { value: WaterState }) => (
  <b className={`st st--${stateTone[value]}`}>{pl.status[value]}</b>
);

export const RiskText = ({ value }: { value: DroughtRiskLevel }) => (
  <b className={`st st--${riskTone[value]}`}>{pl.risk[value]}</b>
);

export const ConfidenceBadge = ({ value }: { value: Confidence }) => (
  <span className={`badge badge--${confTone[value]}`}>
    {pl.confidence.label}: {pl.confidence[value]}
  </span>
);

export const PriorityBadge = ({ value }: { value: Priority }) => (
  <span className={`badge badge--${prioTone[value]}`}>{pl.priority[value]}</span>
);

export const SourceDot = ({ status }: { status: SourceStatus }) => (
  <span className={`dot dot--${srcTone[status]}`} title={pl.sourceStatus[status]} aria-label={pl.sourceStatus[status]} />
);

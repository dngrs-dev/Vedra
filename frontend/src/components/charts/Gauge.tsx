import { pl } from '@/constants/pl';

interface GaugeProps {
  /** 0..100 или null = brak danych */
  value: number | null;
}

const colorFor = (v: number) => (v >= 55 ? 'var(--ok)' : v >= 40 ? 'var(--mid)' : 'var(--bad)');

/** Полукруглый индикатор влажности. */
export function Gauge({ value }: GaugeProps) {
  const has = value !== null;
  return (
    <div className="gauge" role="img" aria-label={has ? `Wilgotność gleby ${value}%` : pl.moisture.noData}>
      <svg viewBox="0 0 120 70" aria-hidden="true">
        <path className="gauge__bg" d="M10 62 A50 50 0 0 1 110 62" />
        <path
          className="gauge__fg"
          d="M10 62 A50 50 0 0 1 110 62"
          pathLength={100}
          strokeDasharray={`${has ? value : 0} 100`}
          style={{ stroke: has ? colorFor(value) : 'transparent' }}
        />
      </svg>
      <div className={`gauge__val${has ? '' : ' is-empty'}`}>{has ? `${value}%` : pl.moisture.noData}</div>
    </div>
  );
}

import { useId, useState, type MouseEvent } from 'react';
import { pl } from '@/constants/pl';

export interface HistoryPoint {
  year: number;
  moisture: number;
  risk: number;
}

interface HistoryChartProps {
  data: HistoryPoint[];
  /** ширина/высота viewBox; график масштабируется по ширине контейнера */
  width?: number;
  height?: number;
  interactive?: boolean;
}

const PAD = { l: 6, r: 6, t: 8, b: 18 };

/** Двухсерийный area-график (без внешних библиотек): влажность почвы и риск засухи за 10 лет. */
export function HistoryChart({ data, width = 230, height = 120, interactive = true }: HistoryChartProps) {
  const uid = useId().replace(/:/g, '');
  const [hover, setHover] = useState<number | null>(null);
  const n = data.length;
  if (n < 2) return null;

  const x = (i: number) => PAD.l + (i * (width - PAD.l - PAD.r)) / (n - 1);
  const y = (v: number) => PAD.t + (1 - v / 100) * (height - PAD.t - PAD.b);
  const baseY = height - PAD.b;

  const path = (key: 'moisture' | 'risk') => {
    const pts = data.map((d, i) => [x(i), y(d[key])] as const);
    let line = `M${pts[0]![0]},${pts[0]![1]}`;
    for (let i = 1; i < pts.length; i++) {
      const [x0, y0] = pts[i - 1]!;
      const [x1, y1] = pts[i]!;
      const cx = (x0 + x1) / 2;
      line += ` C${cx},${y0} ${cx},${y1} ${x1},${y1}`;
    }
    return { line, area: `${line} L${x(n - 1)},${baseY} L${x(0)},${baseY} Z` };
  };
  const m = path('moisture');
  const r = path('risk');

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const vx = ((e.clientX - rect.left) / rect.width) * width;
    const idx = Math.round(((vx - PAD.l) / (width - PAD.l - PAD.r)) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, idx)));
  };

  const h = hover !== null ? data[hover] : undefined;

  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Wykres ${data[0]!.year}–${data[n - 1]!.year}: ${pl.moisture.legendMoisture} i ${pl.moisture.legendRisk}`}
        onMouseMove={interactive ? onMove : undefined}
        onMouseLeave={interactive ? () => setHover(null) : undefined}
      >
        <defs>
          <linearGradient id={`${uid}b`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#2f6fa8" stopOpacity=".35" />
            <stop offset="1" stopColor="#2f6fa8" stopOpacity="0" />
          </linearGradient>
          <linearGradient id={`${uid}o`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#e8913a" stopOpacity=".4" />
            <stop offset="1" stopColor="#e8913a" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line className="chart__axis" x1={PAD.l} x2={width - PAD.r} y1={baseY} y2={baseY} />
        <path d={m.area} fill={`url(#${uid}b)`} />
        <path d={m.line} fill="none" stroke="#2f6fa8" strokeWidth={2} vectorEffect="non-scaling-stroke" />
        <path d={r.area} fill={`url(#${uid}o)`} />
        <path d={r.line} fill="none" stroke="#e8913a" strokeWidth={2} vectorEffect="non-scaling-stroke" />

        {data.map((d, i) =>
          i % 3 === 0 || i === n - 1 ? (
            <text
              key={d.year}
              className="chart__tick"
              x={x(i)}
              y={height - 5}
              textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
            >
              {d.year}
            </text>
          ) : null
        )}

        {hover !== null && h && (
          <g>
            <line className="chart__cursor" x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={baseY} />
            <circle cx={x(hover)} cy={y(h.moisture)} r={3.2} fill="#fff" stroke="#2f6fa8" strokeWidth={2} />
            <circle cx={x(hover)} cy={y(h.risk)} r={3.2} fill="#fff" stroke="#e8913a" strokeWidth={2} />
          </g>
        )}
      </svg>

      {hover !== null && h && (
        <div className="chart__tip" style={{ left: `${(x(hover) / width) * 100}%` }}>
          <b>{h.year}</b>
          <span>{pl.moisture.legendMoisture}: {h.moisture}%</span>
          <span>{pl.moisture.legendRisk}: {h.risk}%</span>
        </div>
      )}
    </div>
  );
}

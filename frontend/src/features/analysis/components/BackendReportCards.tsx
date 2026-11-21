import type { ReactNode } from 'react';
import { Card } from '@/components/ui/Card';
import { pl } from '@/constants/pl';
import type { BackendMetric, BackendRange, BackendReport } from '@/types/backendReport';
import { fmtDate, fmtDateTime } from '@/utils/format';
import { ConfidenceBadge } from './Badges';

const number = new Intl.NumberFormat('pl-PL', { maximumSignificantDigits: 21 });
// Match the two-decimal display used for the same estimates in the backend PDF.
const balance = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 });

function formatRange({ low, mid, high }: BackendRange): string {
  return low !== null && high !== null && low !== high
    ? `${number.format(mid)} (${number.format(low)}–${number.format(high)})`
    : number.format(mid);
}

function formatMetric({ code, value, unit }: BackendMetric): string {
  if (value === null) return pl.moisture.noData;
  const display = typeof value === 'number' ? (code === 'kbw_last_balance' ? balance : number).format(value)
    : typeof value === 'string' ? value : formatRange(value);
  return unit ? `${display} ${unit}` : display;
}

function Metrics({ items }: { items: BackendMetric[] }) {
  if (!items.length) return null;
  return (
    <dl className="factors">
      {items.map((metric) => (
        <div key={metric.code}><dt>{metric.label_pl}</dt><dd>{formatMetric(metric)}</dd></div>
      ))}
    </dl>
  );
}

function SourceLink({ url, children }: { url: string; children: ReactNode }) {
  return /^https?:\/\//i.test(url) ? <a href={url} target="_blank" rel="noreferrer">{children}</a> : <>{children}</>;
}

export function BackendReportCards({ report }: { report: BackendReport }) {
  const { assessment, causes, recommendations, irrigation, data_sources, limitations_pl, references } = report;
  const { kbw, confidence, signals, vulnerability } = assessment;
  const { backend: copy } = pl;
  const waitingForPeriod = kbw.verdict === 'unavailable' && kbw.period === null;
  const showBalance = kbw.kbw_mm !== null || (kbw.period !== null && kbw.verdict === 'unavailable');

  return (
    <>
      <Card title={copy.kbw}>
        <p><strong>{waitingForPeriod ? copy.firstKbwPeriod : copy.verdict[kbw.verdict]}</strong></p>
        <p>{report.summary}</p>
        <p className="muted small">{copy.kbwDefinition}</p>
        <dl className="factors">
          {kbw.period && <div><dt>{copy.period}</dt><dd>{fmtDate(kbw.period.start)} – {fmtDate(kbw.period.end)}</dd></div>}
          {kbw.soil_category && <div><dt>{copy.soilCategory}</dt><dd>{kbw.soil_category}</dd></div>}
          {showBalance && <div><dt>KBW</dt><dd>{kbw.kbw_mm === null ? pl.moisture.noData : `${balance.format(kbw.kbw_mm)} mm`}</dd></div>}
          {typeof kbw.threshold_mm === 'number' && <div><dt>{copy.threshold}</dt><dd>{balance.format(kbw.threshold_mm)} mm</dd></div>}
          {kbw.distance_to_threshold_mm !== null && (
            <div><dt>{copy.distanceToThreshold}</dt><dd>{balance.format(kbw.distance_to_threshold_mm)} mm</dd></div>
          )}
        </dl>
        {confidence && <ConfidenceBadge value={confidence} />}
      </Card>

      {vulnerability && (
        <Card title={copy.history}>
          <p>{vulnerability.summary_pl}</p>
          {vulnerability.years_assessed.length > 0 && (
            <dl className="factors">
              <div><dt>{copy.assessedYears}</dt><dd>{vulnerability.years_assessed.join(', ')}</dd></div>
              <div><dt>{copy.droughtYears}</dt><dd>{vulnerability.drought_years.join(', ') || copy.noDroughtYears}</dd></div>
            </dl>
          )}
          <Metrics items={vulnerability.metrics} />
        </Card>
      )}

      {causes.length > 0 && (
        <Card title={copy.causes}>
          <ol className="reco__list">
            {causes.map((cause) => (
              <li key={cause.code}>
                <strong>{cause.title_pl}</strong>
                <p>{cause.explanation_pl}</p>
                <Metrics items={cause.evidence} />
              </li>
            ))}
          </ol>
        </Card>
      )}

      {(recommendations.length > 0 || irrigation) && (
        <Card title={pl.report.recommendations}>
          {Object.entries(copy.categories).map(([category, title]) => {
            const items = recommendations.filter((item) => item.category === category);
            if (!items.length) return null;
            return (
              <div className="reco" key={category}>
                <h3>{title}</h3>
                <ul className="reco__list">
                  {items.map((item) => (
                    <li key={item.id}>
                      <strong>{item.title_pl}</strong>
                      <p>{item.action_pl}</p>
                      <details className="why">
                        <summary>{pl.reco.why}</summary>
                        <p>{item.why_pl}</p>
                        <Metrics items={item.evidence} />
                        <ul>
                          {references.filter((ref) => item.reference_ids.includes(ref.id)).map((ref) => (
                            <li key={ref.id}><SourceLink url={ref.url}>{ref.title_pl}</SourceLink></li>
                          ))}
                        </ul>
                      </details>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          {irrigation && (
            <div className="reco">
              <h3>{pl.reco.irrigation}</h3>
              <p>{irrigation.why_pl}</p>
              <dl className="factors">
                {irrigation.suggested_date && <div><dt>{copy.irrigationDate}</dt><dd>{fmtDate(irrigation.suggested_date)}</dd></div>}
                {irrigation.net_dose_mm && <div><dt>{copy.irrigationDose}</dt><dd>{formatRange(irrigation.net_dose_mm)} mm</dd></div>}
              </dl>
            </div>
          )}
        </Card>
      )}

      <Card className="basis">
        <details>
          <summary className="basis__summary">{pl.basis.title}</summary>
          {signals.length > 0 && (
            <>
              <h3 className="basis__h">{copy.signals}</h3>
              <ul className="reco__list">
                {signals.map((signal) => (
                  <li key={signal.code}>
                    <strong>{copy.availability[signal.status]}</strong>
                    <p>{signal.summary_pl}</p>
                    <Metrics items={signal.metrics} />
                  </li>
                ))}
              </ul>
            </>
          )}
          <h3 className="basis__h">{pl.basis.sources}</h3>
          {data_sources.length ? (
            <ul className="sources">
              {data_sources.map((source, i) => (
                <li key={`${source.source_id}-${i}`}>
                  <div>
                    <SourceLink url={source.url}>{source.name}</SourceLink>
                    <div className="muted small">
                      {[
                        source.data_period, source.resolution, source.licence,
                        source.live ? copy.liveSource : copy.savedSource, fmtDateTime(source.fetched_at)
                      ].filter(Boolean).join(' · ')}
                    </div>
                    {source.attribution_pl && <small>{source.attribution_pl}</small>}
                  </div>
                </li>
              ))}
            </ul>
          ) : <p>{copy.noSources}</p>}
          {references.length > 0 && (
            <>
              <h3 className="basis__h">{copy.references}</h3>
              <ul>{references.map((ref) => <li key={ref.id}><SourceLink url={ref.url}>{ref.title_pl}</SourceLink></li>)}</ul>
            </>
          )}
        </details>
        {limitations_pl.length > 0 && (
          <>
            <h3 className="basis__h">{pl.report.limitations}</h3>
            <ul className="limits">{limitations_pl.map((note) => <li key={note}>{note}</li>)}</ul>
          </>
        )}
      </Card>
    </>
  );
}

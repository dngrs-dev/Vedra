import { lazy, Suspense, useId, useState, type ReactNode } from 'react';
import { Card } from '@/components/ui/Card';
import { pl } from '@/constants/pl';
import type { BackendGeometry, BackendMetric, BackendRange, BackendReport } from '@/types/backendReport';
import { fmtDate, fmtDateTime } from '@/utils/format';
import { groupRecommendations, type RecommendationSite } from '../recommendationGroups';
import { ConfidenceBadge } from './Badges';

const RecommendationMap = lazy(() => import('./RecommendationMap'));

const number = new Intl.NumberFormat('pl-PL', { maximumSignificantDigits: 21 });
// Match the two-decimal display used for the same estimates in the backend PDF.
const balance = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 });

function formatRange({ low, mid, high }: BackendRange): string {
  return low !== null && high !== null && low !== high
    ? `${number.format(mid)} (${number.format(low)}–${number.format(high)})`
    : number.format(mid);
}

function formatMetric({ value, unit }: BackendMetric, format = number): string {
  if (value === null) return pl.moisture.noData;
  const display = typeof value === 'number' ? format.format(value)
    : typeof value === 'string' ? value : formatRange(value);
  return unit ? `${display}\u00a0${unit}` : display;
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

function RecommendationSites({ sites, parcel }: { sites: RecommendationSite[]; parcel?: BackendGeometry | null }) {
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState(1);
  const id = useId();
  const site = sites.find((entry) => entry.number === selected) ?? sites[0];
  const { backend: copy } = pl;
  if (!site) return null;

  return (
    <div className="recommendation-sites">
      <button type="button" className="link-btn" aria-expanded={expanded} aria-controls={id}
        onClick={() => setExpanded(!expanded)}>
        {copy.sites} ({sites.length})
      </button>
      <div id={id} hidden={!expanded}>
        {expanded && (
          <>
            <Suspense fallback={<p role="status">{copy.loadingSiteMap}</p>}>
              <RecommendationMap parcel={parcel} sites={sites} selected={site.number} onSelect={setSelected} />
            </Suspense>
            <div className="site-controls" role="group" aria-label={copy.sites}>
              {sites.map((entry) => (
                <button key={entry.number} type="button" aria-label={`${copy.site} ${entry.number}`}
                  aria-pressed={entry.number === site.number} onClick={() => setSelected(entry.number)}>
                  {entry.number}
                </button>
              ))}
            </div>
            <div className="site-detail" aria-live="polite">
              <strong>{copy.site} {site.number}</strong>
              {site.note && <p>{site.note}</p>}
              {site.evidence.length ? <Metrics items={site.evidence} /> : <p>{copy.siteEvidence}</p>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export function BackendReportCards({ report }: { report: BackendReport }) {
  const { assessment, causes, recommendations, irrigation, data_sources, limitations_pl, references } = report;
  const { kbw, confidence, signals, vulnerability } = assessment;
  const { backend: copy } = pl;
  const showBalance = kbw.kbw_mm !== null || (kbw.period !== null && kbw.verdict === 'unavailable');
  const { verdict } = kbw;
  const historyMetrics = vulnerability?.metrics ?? [];
  const lastPeriod = historyMetrics.find((metric) => metric.code === 'kbw_last_period');
  const lastBalance = historyMetrics.find((metric) => metric.code === 'kbw_last_balance');
  const actions = groupRecommendations(recommendations);

  return (
    <>
      <Card title={copy.kbw}>
        {(verdict === 'drought' || verdict === 'no_drought') && <p><strong>{copy.verdict[verdict]}</strong></p>}
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
        {lastPeriod && lastBalance && (
          <section className="kbw-latest">
            <h3>{copy.lastKbwAssessment}</h3>
            <dl className="factors">
              <div><dt>{copy.period}</dt><dd>{formatMetric(lastPeriod)}</dd></div>
              <div><dt>{copy.balance}</dt><dd>{formatMetric(lastBalance, balance)}</dd></div>
            </dl>
          </section>
        )}
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
          <Metrics items={lastPeriod && lastBalance
            ? historyMetrics.filter((metric) => metric !== lastPeriod && metric !== lastBalance)
            : historyMetrics} />
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
            const items = actions.filter((item) => item.recommendation.category === category);
            if (!items.length) return null;
            return (
              <div className="reco" key={category}>
                <h3>{title}</h3>
                <ul className="reco__list">
                  {items.map(({ recommendation, instruction, evidence, sites }) => (
                    <li key={`${report.parcel.parcel_id}:${report.analysis_date}:${recommendation.id}`}>
                      <strong>{recommendation.title_pl}</strong>
                      <p>{instruction}</p>
                      <details className="why">
                        <summary>{pl.reco.why}</summary>
                        <p>{recommendation.why_pl}</p>
                        <Metrics items={evidence} />
                        <ul>
                          {references.filter((ref) => recommendation.reference_ids.includes(ref.id)).map((ref) => (
                            <li key={ref.id}><SourceLink url={ref.url}>{ref.title_pl}</SourceLink></li>
                          ))}
                        </ul>
                      </details>
                      {sites.length > 0 && <RecommendationSites sites={sites} parcel={report.parcel.geometry_wgs84} />}
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

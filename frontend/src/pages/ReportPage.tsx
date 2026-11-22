import { Link, Navigate } from 'react-router-dom';
import { HistoryChart } from '@/components/charts/HistoryChart';
import { ArrowLeftIcon, PrinterIcon } from '@/components/ui/Icons';
import { Card } from '@/components/ui/Card';
import { CROPS } from '@/constants/crops';
import { MONTHS_PL, pl } from '@/constants/pl';
import { AnalysisError, AnalysisJobState } from '@/features/analysis/components/AnalysisJobState';
import { BackendReportCards } from '@/features/analysis/components/BackendReportCards';
import { ConfidenceBadge } from '@/features/analysis/components/Badges';
import { GroupAnalysisResults } from '@/features/analysis/components/GroupAnalysisResults';
import { useAnalysis } from '@/features/analysis/hooks/useAnalysis';
import { useAnalysisStore } from '@/features/analysis/store';
import { reportPdfUrl } from '@/services/analysisApi';
import type { Analysis, Recommendation } from '@/types/analysis';
import type { Parcel } from '@/types/parcel';
import { fmtDate, fmtDateTime } from '@/utils/format';

function RecoBlock({ title, items }: { title: string; items: Recommendation[] }) {
  if (!items.length) return null;
  return (
    <>
      <h3>{title}</h3>
      <ul>
        {items.map((r) => (
          <li key={r.id}>
            <b>{r.title}.</b> {r.text} <em className="muted">({pl.reco.why} {r.evidence})</em>
          </li>
        ))}
      </ul>
    </>
  );
}

export function ReportPage() {
  const parcel = useAnalysisStore((s) => s.confirmed);
  const cropIds = useAnalysisStore((s) => s.cropIds);
  const { demo, demoMode, isGroup, jobs, selectionError } = useAnalysis();

  if (!parcel) return <Navigate to="/map" replace />;
  if (demoMode && demo.data) return <DemoReport parcel={parcel} cropIds={cropIds} data={demo.data} />;

  return (
    <div className="report-wrap">
      <div className="report-toolbar no-print">
        <Link to="/map" className="btn-secondary"><ArrowLeftIcon /> {pl.report.back}</Link>
      </div>
      {selectionError && <AnalysisError message={selectionError} />}
      {demoMode && (
        demo.error
          ? <AnalysisError message={demo.error.message} retry={() => void demo.refetch()} />
          : <p role="status">{pl.backend.preparing}</p>
      )}
      <GroupAnalysisResults jobs={jobs} group={isGroup}>{(visible) => visible.map((job) => {
        const report = job.report;
        if (!report || !job.analysisId) {
          return (
            <div className="backend-report results" key={`${job.parcelId}:${job.code}`}>
              <h2 className="analysis-crop">{job.names.join(', ')}</h2>
              <AnalysisJobState job={job} />
            </div>
          );
        }
        const { parcel } = report;
        return (
          <article className="report backend-report results" key={`${job.parcelId}:${job.code}`}>
            <header className="report__head">
              <div>
                <h1>{pl.report.title}</h1>
                <p className="muted">{report.crop_name_pl} · {fmtDate(report.analysis_date)}</p>
              </div>
              <a className="btn-primary no-print" href={reportPdfUrl(job.analysisId)}><PrinterIcon /> {pl.report.download}</a>
            </header>
            <Card title={pl.report.parcel}>
              <dl className="factors">
                <div><dt>Identyfikator działki</dt><dd>{parcel.parcel_id}</dd></div>
                <div><dt>Powierzchnia</dt><dd>{parcel.area_ha.toLocaleString('pl-PL')} ha</dd></div>
                <div><dt>Lokalizacja</dt><dd>{[parcel.commune, parcel.county, parcel.voivodeship].filter(Boolean).join(', ') || '—'}</dd></div>
              </dl>
            </Card>
            <BackendReportCards report={report} />
            <p className="muted small">{pl.report.disclaimer}</p>
          </article>
        );
      })}</GroupAnalysisResults>
    </div>
  );
}

function DemoReport({ parcel, cropIds, data }: { parcel: Parcel; cropIds: string[]; data: Analysis }) {
  const crops = CROPS.filter((c) => cropIds.includes(c.id)).map((c) => c.name).join(', ');
  const months = data.criticalMonths.map((m) => MONTHS_PL[m - 1]).filter(Boolean).join(', ');
  const { retention, agrotechnical, irrigation } = data.recommendations;

  return (
    <div className="report-wrap">
      <div className="report-toolbar no-print">
        <Link to="/map" className="btn-secondary"><ArrowLeftIcon /> {pl.report.back}</Link>
        <button type="button" className="btn-primary" onClick={() => window.print()}>
          <PrinterIcon /> {pl.report.print}
        </button>
      </div>

      <article className="report">
        <header className="report__head">
          <div>
            <h1>{pl.report.title}</h1>
            <p className="muted">{pl.appTitle} · {pl.appSubtitle}</p>
          </div>
          <ConfidenceBadge value={data.confidence} />
        </header>

        <div className="demo-banner">{pl.demoBanner}</div>

        <h2>{pl.report.parcel}</h2>
        <table>
          <tbody>
            {parcel.parts ? (
              <tr>
                <td>Działki ({parcel.parts.length})</td>
                <td>{parcel.parts.map((p) => p.id).join(', ')}</td>
              </tr>
            ) : (
              <tr><td>Identyfikator działki</td><td>{data.parcelId}</td></tr>
            )}
            <tr><td>Powierzchnia</td><td>{data.areaHa} ha</td></tr>
            <tr><td>Lokalizacja</td><td>{data.region}</td></tr>
            <tr><td>Uprawa</td><td>{crops}</td></tr>
            <tr><td>Data analizy</td><td>{fmtDate(data.analysisDate)}</td></tr>
            <tr><td>Raport wygenerowano</td><td>{fmtDateTime(data.generatedAt)}</td></tr>
          </tbody>
        </table>

        <h2>{pl.report.assessment}</h2>
        <table>
          <tbody>
            <tr><td>{pl.moisture.current}</td><td>{pl.status[data.state]}</td></tr>
            <tr><td>{pl.moisture.soil}</td><td>{data.soilMoisturePct === null ? pl.moisture.noData : `${data.soilMoisturePct}%`}</td></tr>
            <tr><td>{pl.moisture.avgRisk}</td><td>{pl.risk[data.droughtRisk.level]} ({data.droughtRisk.avgIndexPct}%)</td></tr>
            {months && <tr><td>{pl.moisture.critical}</td><td>{months}</td></tr>}
          </tbody>
        </table>
        <div className="report__chart">
          <HistoryChart data={data.history} width={520} height={170} interactive={false} />
          <div className="legend">
            <span><i className="lg lg--blue" />{pl.moisture.legendMoisture}</span>
            <span><i className="lg lg--orange" />{pl.moisture.legendRisk}</span>
          </div>
        </div>

        <h3>Czynniki uwzględnione w analizie</h3>
        <table>
          <tbody>
            {data.factors.map((f) => (
              <tr key={f.id}><td>{f.label}</td><td>{f.value} <span className="muted">({f.source})</span></td></tr>
            ))}
          </tbody>
        </table>

        <h2>{pl.report.recommendations}</h2>
        <RecoBlock title={pl.reco.retention} items={retention} />
        <RecoBlock title={pl.reco.agro} items={agrotechnical} />
        <h3>{pl.reco.irrigation}</h3>
        <p>
          {irrigation.summary}
          {irrigation.amountMm !== null && ` Orientacyjna dawka: ok. ${irrigation.amountMm} mm.`}
          {' '}{pl.reco.date} <b>{irrigation.optimalDate ? fmtDate(irrigation.optimalDate) : pl.reco.none}</b>
        </p>

        <h2>{pl.report.sources}</h2>
        <table>
          <thead><tr><th>Źródło</th><th>Okres</th><th>Licencja</th><th>Status / pobrano</th></tr></thead>
          <tbody>
            {data.sources.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>{s.period}</td>
                <td>{s.license}</td>
                <td>{pl.sourceStatus[s.status]}{s.fetchedAt ? `, ${fmtDateTime(s.fetchedAt)}` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2>{pl.report.limitations}</h2>
        <ul>{data.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="muted small">{pl.report.disclaimer}</p>
      </article>
    </div>
  );
}

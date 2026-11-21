import { useNavigate } from 'react-router-dom';
import { pl } from '@/constants/pl';
import { useAnalysis } from '@/features/analysis/hooks/useAnalysis';
import { fmtDateTime } from '@/utils/format';

export function Footer() {
  const navigate = useNavigate();
  const { demo, jobs } = useAnalysis();
  const reports = jobs.flatMap(({ report }) => report ? [report] : []);
  const parcel = reports[0]?.parcel;
  const region = demo.data?.region || parcel?.voivodeship || '—';
  const fetchedAt = reports.flatMap((report) => report.data_sources).reduce<string | undefined>(
    (latest, source) => !latest || Date.parse(source.fetched_at) > Date.parse(latest) ? source.fetched_at : latest,
    demo.data?.generatedAt
  );
  const updated = fetchedAt ? fmtDateTime(fetchedAt) : '—';

  return (
    <footer className="foot">
      <div className="foot__left">
        <div className="foot__upd">
          <span>{pl.footer.lastUpdate}</span>
          <b>{updated}</b>
        </div>
        <div className="foot__sep" />
        <div className="foot__weather">
          <svg viewBox="0 0 48 32" width="34" height="24" aria-hidden="true">
            <circle cx="32" cy="11" r="7" fill="#f4c542" />
            <path d="M12 28h22a7 7 0 0 0 0-14 9 9 0 0 0-17-2A8 8 0 0 0 12 28z" fill="#e8eef3" stroke="#b8c4cd" />
          </svg>
          <div>
            <div className="foot__region">{pl.footer.region} {region}</div>
            <div className="foot__small">{updated}</div>
          </div>
        </div>
      </div>
      <button type="button" className="btn-primary" disabled={!demo.data && !reports.length} onClick={() => navigate('/report')}>
        {pl.footer.report}
      </button>
    </footer>
  );
}

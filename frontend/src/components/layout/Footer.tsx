import { useNavigate } from 'react-router-dom';
import { pl } from '@/constants/pl';
import { useAnalysis } from '@/features/analysis/hooks/useAnalysis';
import { fmtDateTime } from '@/utils/format';

export function Footer() {
  const navigate = useNavigate();
  const { data } = useAnalysis();

  return (
    <footer className="foot">
      <div className="foot__left">
        <div className="foot__upd">
          <span>{pl.footer.lastUpdate}</span>
          <b>{data ? fmtDateTime(data.generatedAt) : '—'}</b>
        </div>
        <div className="foot__sep" />
        <div className="foot__weather">
          <svg viewBox="0 0 48 32" width="34" height="24" aria-hidden="true">
            <circle cx="32" cy="11" r="7" fill="#f4c542" />
            <path d="M12 28h22a7 7 0 0 0 0-14 9 9 0 0 0-17-2A8 8 0 0 0 12 28z" fill="#e8eef3" stroke="#b8c4cd" />
          </svg>
          <div>
            <div className="foot__region">{pl.footer.region} {data ? data.region : '—'}</div>
            <div className="foot__small">{data ? fmtDateTime(data.generatedAt) : '—'}</div>
          </div>
        </div>
      </div>
      <button type="button" className="btn-primary" disabled={!data} onClick={() => navigate('/report')}>
        {pl.footer.report}
      </button>
    </footer>
  );
}

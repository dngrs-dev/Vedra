import { useNavigate } from 'react-router-dom';
import { pl } from '@/constants/pl';
import { useAnalysis } from '@/features/analysis/hooks/useAnalysis';
import { useAnalysisStore } from '@/features/analysis/store';
import { FooterWeather } from './FooterWeather';

export function Footer() {
  const navigate = useNavigate();
  const { demo, jobs } = useAnalysis({ active: false });
  const selected = useAnalysisStore((s) => s.confirmed ?? s.parcel);
  const region = useAnalysisStore((s) => s.region);
  const reports = jobs.flatMap(({ report }) => report ? [report] : []);
  const parcel = reports[0]?.parcel;
  // Место: гмина и воеводство из отчёта, иначе регион демо-анализа или воеводство на карте
  const place = parcel
    ? [...new Set([parcel.commune, parcel.voivodeship].filter(Boolean))].join(', ')
    : demo.data?.region || region;

  return (
    <footer className="foot">
      <FooterWeather point={selected?.center ?? null} place={place || null} />
      <button type="button" className="btn-primary" disabled={!demo.data && !reports.length} onClick={() => navigate('/report')}>
        {pl.footer.report}
      </button>
    </footer>
  );
}

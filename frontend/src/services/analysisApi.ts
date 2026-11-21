import { z } from 'zod';
import { pl } from '@/constants/pl';
import { BackendReportSchema } from '@/types/backendReport';
import { API_URL, request } from './http';

// Job response fields from backend/app/api/routes_analyses.py and app/jobs/runner.py.
const started = z.object({ analysis_id: z.string().uuid() });
const progress = z.object({ progress: z.array(z.string()) });
const analysisStatus = z.discriminatedUnion('status', [
  progress.extend({ status: z.literal('queued') }),
  progress.extend({ status: z.literal('running') }),
  progress.extend({ status: z.literal('done'), report: BackendReportSchema }),
  progress.extend({ status: z.literal('error'), error: z.string().nullable() })
]);

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export async function startAnalysis(parcelId: string, cropCode: string, date: string) {
  const raw = await request<unknown>('/analyses', {
    method: 'POST',
    body: JSON.stringify({
      parcel_id: parcelId,
      crop_code: cropCode,
      analysis_date: date,
      include_irrigation: true
    })
  });
  const result = started.safeParse(raw);
  if (!result.success) throw new Error(pl.error.invalidResponse);
  return result.data.analysis_id;
}

export async function getAnalysisStatus(analysisId: string, signal: AbortSignal) {
  const raw = await request<unknown>(`/analyses/${encodeURIComponent(analysisId)}`, { signal });
  const result = analysisStatus.safeParse(raw);
  if (!result.success) throw new Error(pl.error.invalidResponse);
  return result.data;
}

export function reportPdfUrl(analysisId: string): string {
  return `${API_URL}/analyses/${encodeURIComponent(analysisId)}/report.pdf`;
}

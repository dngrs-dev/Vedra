import { AnalysisSchema, type Analysis, type AnalysisRequest } from '@/types/analysis';
import { request } from './http';
import { mockAnalyze } from './mockAnalysis';

const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false';

/**
 * Главная точка входа в аналитику.
 * - VITE_USE_MOCK=true  → демо-данные (пока нет бэкенда)
 * - VITE_USE_MOCK=false → POST {VITE_API_URL}/analyze, ответ валидируется zod-схемой
 *
 * Остальной фронтенд работает ТОЛЬКО через эту функцию.
 */
export async function analyze(req: AnalysisRequest, signal?: AbortSignal): Promise<Analysis> {
  if (USE_MOCK) return mockAnalyze(req, signal);

  const raw = await request<unknown>('/analyze', {
    method: 'POST',
    body: JSON.stringify(req),
    signal
  });
  return AnalysisSchema.parse(raw);
}

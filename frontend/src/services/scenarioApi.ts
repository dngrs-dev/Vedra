import { pl } from '@/constants/pl';
import { AiInsightSchema, AiStatusSchema, ScenarioReportSchema, type Levers } from '@/types/scenario';
import { request } from './http';

// Endpoints from backend/app/api/routes_scenarios.py.
export async function simulateScenarios(analysisId: string, levers: Levers, signal?: AbortSignal) {
  const raw = await request<unknown>(`/analyses/${encodeURIComponent(analysisId)}/scenarios`, {
    method: 'POST',
    body: JSON.stringify(levers),
    signal
  });
  const result = ScenarioReportSchema.safeParse(raw);
  if (!result.success) throw new Error(pl.error.invalidResponse);
  return result.data;
}

/** consent - пользователь согласился на передачу данных во внешнюю usługę AI (RODO); бэкенд это проверяет. */
export async function getAiInsight(analysisId: string, levers: Levers, consent: boolean, signal?: AbortSignal) {
  const raw = await request<unknown>(`/analyses/${encodeURIComponent(analysisId)}/ai-insight`, {
    method: 'POST',
    body: JSON.stringify({ ...levers, consent }),
    signal
  });
  const result = AiInsightSchema.safeParse(raw);
  if (!result.success) throw new Error(pl.error.invalidResponse);
  return result.data;
}

export async function getAiStatus(signal?: AbortSignal) {
  const result = AiStatusSchema.safeParse(await request<unknown>('/ai/status', { signal }));
  if (!result.success) throw new Error(pl.error.invalidResponse);
  return result.data;
}

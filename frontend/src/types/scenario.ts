import { z } from 'zod';

// Fields from backend/app/contracts/scenario.py.
export const LeversSchema = z.object({
  retention_mm: z.number(),
  organic_matter_pct: z.number(),
  cover_pct: z.number(),
  irrigation_limit_mm: z.number(),
  irrigation_dose_mm: z.number()
});
export type Levers = z.infer<typeof LeversSchema>;

const risk = z.enum(['low', 'medium', 'high']);
export type ScenarioRisk = z.infer<typeof risk>;

const outcome = z.object({
  stress_days: z.number(),
  days: z.number(),
  et_deficit_pct: z.number(),
  min_available_pct: z.number(),
  end_available_pct: z.number(),
  irrigation_events: z.number(),
  risk,
  budget: z.object({
    precipitation_mm: z.number(),
    irrigation_mm: z.number(),
    retention_release_mm: z.number(),
    actual_et_mm: z.number(),
    potential_et_mm: z.number(),
    losses_mm: z.number(),
    retained_mm: z.number(),
    storage_change_mm: z.number()
  })
});

const result = z.object({
  id: z.string(),
  title_pl: z.string(),
  description_pl: z.string(),
  levers: LeversSchema,
  taw_mm: z.number(),
  outcome,
  series: z.array(z.object({ day: z.string(), available_pct: z.number() }))
});
export type ScenarioResult = z.infer<typeof result>;

export const ScenarioReportSchema = z.object({
  analysis_id: z.string(),
  crop_name_pl: z.string(),
  window_start: z.string(),
  window_end: z.string(),
  window_note_pl: z.string(),
  baseline: result,
  custom: result,
  presets: z.array(result),
  assumptions_pl: z.array(z.string()),
  kbw_note_pl: z.string()
});
export type ScenarioReport = z.infer<typeof ScenarioReportSchema>;

export const AiInsightSchema = z.object({
  source: z.enum(['llm', 'rules']),
  model: z.string().nullable(),
  headline_pl: z.string(),
  forecast_pl: z.string(),
  best_action_pl: z.string(),
  reasoning_pl: z.array(z.string()),
  caveats_pl: z.array(z.string()),
  note_pl: z.string().nullable()
});
export type AiInsight = z.infer<typeof AiInsightSchema>;

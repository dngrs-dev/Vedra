import { z } from 'zod';

// View model for the frontend's demonstration analysis.

export const WaterStateSchema = z.enum(['optimal', 'attention', 'critical']);
export const DroughtRiskLevelSchema = z.enum(['low', 'moderate', 'high']);
export const ConfidenceSchema = z.enum(['high', 'medium', 'low']);
export const PrioritySchema = z.enum(['high', 'medium', 'low']);
export const SourceStatusSchema = z.enum(['live', 'cached', 'unavailable']);

export const RecommendationSchema = z.object({
  id: z.string(),
  title: z.string(),
  text: z.string(),
  priority: PrioritySchema,
  /** Почему это рекомендуется - на каких данных основано (обязательно по ТЗ). */
  evidence: z.string()
});

export const FactorSchema = z.object({
  id: z.string(),
  label: z.string(),
  value: z.string(),
  source: z.string()
});

export const DataSourceSchema = z.object({
  id: z.string(),
  name: z.string(),
  category: z.enum(['satellite', 'weather', 'soil', 'hydrology', 'spatial']),
  period: z.string(),
  fetchedAt: z.string().nullable(),
  license: z.string(),
  status: SourceStatusSchema
});

export const AnalysisSchema = z.object({
  parcelId: z.string(),
  areaHa: z.number(),
  region: z.string(),
  analysisDate: z.string(),
  generatedAt: z.string(),

  state: WaterStateSchema,
  /** null = brak danych (komunikujemy wprost, bez pozornej precyzji) */
  soilMoisturePct: z.number().min(0).max(100).nullable(),
  droughtRisk: z.object({
    level: DroughtRiskLevelSchema,
    avgIndexPct: z.number().min(0).max(100)
  }),
  history: z.array(
    z.object({
      year: z.number().int(),
      moisture: z.number().min(0).max(100),
      risk: z.number().min(0).max(100)
    })
  ),
  /** Месяцы (1-12) наибольшего риска дефицита воды */
  criticalMonths: z.array(z.number().int().min(1).max(12)),

  factors: z.array(FactorSchema),
  recommendations: z.object({
    retention: z.array(RecommendationSchema),
    agrotechnical: z.array(RecommendationSchema),
    irrigation: z.object({
      needed: z.boolean(),
      summary: z.string(),
      optimalDate: z.string().nullable(),
      amountMm: z.number().nullable()
    })
  }),

  sources: z.array(DataSourceSchema),
  confidence: ConfidenceSchema,
  limitations: z.array(z.string()),
  isDemo: z.boolean().default(false)
});

export type Analysis = z.infer<typeof AnalysisSchema>;
export type Recommendation = z.infer<typeof RecommendationSchema>;
export type DataSource = z.infer<typeof DataSourceSchema>;
export type WaterState = z.infer<typeof WaterStateSchema>;
export type DroughtRiskLevel = z.infer<typeof DroughtRiskLevelSchema>;
export type Confidence = z.infer<typeof ConfidenceSchema>;
export type Priority = z.infer<typeof PrioritySchema>;
export type SourceStatus = z.infer<typeof SourceStatusSchema>;

export interface AnalysisRequest {
  parcelId: string;
  lat: number;
  lng: number;
  areaHa: number;
  cropIds: string[];
  date: string;
}

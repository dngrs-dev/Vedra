import { z } from 'zod';
import { ConfidenceSchema } from './analysis';

// Public fields used by the UI from backend/app/contracts/report.py.
const range = z.object({ low: z.number().nullable(), mid: z.number(), high: z.number().nullable() });
const period = z.object({ start: z.string(), end: z.string() });
const availability = z.enum(['ok', 'partial', 'missing']);
// Coordinate order and bounds follow WGS84 GeoJSON (RFC 7946).
const position = z.tuple([z.number().min(-180).max(180), z.number().min(-90).max(90)]).rest(z.number());
const line = z.array(position).min(2);
const polygon = z.array(z.array(position).min(4)).nonempty();
const geometry = z.discriminatedUnion('type', [
  z.object({ type: z.literal('Point'), coordinates: position }),
  z.object({ type: z.literal('MultiPoint'), coordinates: z.array(position).nonempty() }),
  z.object({ type: z.literal('LineString'), coordinates: line }),
  z.object({ type: z.literal('MultiLineString'), coordinates: z.array(line).nonempty() }),
  z.object({ type: z.literal('Polygon'), coordinates: polygon }),
  z.object({ type: z.literal('MultiPolygon'), coordinates: z.array(polygon).nonempty() })
]);
const metric = z.object({
  code: z.string(),
  label_pl: z.string(),
  value: z.union([z.number(), z.string(), range]).nullable(),
  unit: z.string().nullable(),
  source_ids: z.array(z.string()).default([])
});

export const BackendReportSchema = z.object({
  parcel: z.object({
    parcel_id: z.string(),
    area_ha: z.number(),
    commune: z.string(),
    county: z.string(),
    voivodeship: z.string(),
    geometry_wgs84: geometry.nullish().catch(null)
  }),
  crop_code: z.string().optional(),
  crop_name_pl: z.string(),
  analysis_date: z.string(),
  summary: z.string(),
  assessment: z.object({
    confidence: ConfidenceSchema.nullable(),
    kbw: z.object({
      verdict: z.enum(['drought', 'no_drought', 'not_applicable', 'not_recommended', 'off_season', 'unavailable']),
      period: period.nullable(),
      soil_category: z.enum(['I', 'II', 'III', 'IV']).nullable(),
      kbw_mm: z.number().nullable(),
      threshold_mm: z.union([z.number(), z.literal('x'), z.literal('-')]).nullable(),
      distance_to_threshold_mm: z.number().nullable()
    }),
    signals: z.array(z.object({
      code: z.string(),
      status: availability,
      summary_pl: z.string(),
      metrics: z.array(metric)
    })),
    vulnerability: z.object({
      summary_pl: z.string(),
      years_assessed: z.array(z.number().int()),
      drought_years: z.array(z.number().int()),
      metrics: z.array(metric)
    }).nullable()
  }),
  causes: z.array(z.object({
    code: z.string(),
    title_pl: z.string(),
    explanation_pl: z.string(),
    evidence: z.array(metric)
  })),
  recommendations: z.array(z.object({
    id: z.string(),
    category: z.enum(['landscape_retention', 'soil_retention', 'agrotechnics', 'irrigation']),
    title_pl: z.string(),
    action_pl: z.string(),
    why_pl: z.string(),
    evidence: z.array(metric),
    reference_ids: z.array(z.string()),
    geometry: geometry.nullish().catch(null)
  })),
  irrigation: z.object({
    why_pl: z.string(),
    suggested_date: z.string().nullable(),
    net_dose_mm: range.nullable()
  }).nullable(),
  data_sources: z.array(z.object({
    source_id: z.string(),
    name: z.string(),
    url: z.string(),
    fetched_at: z.string(),
    live: z.boolean(),
    data_period: z.string().nullable(),
    resolution: z.string().nullable(),
    licence: z.string(),
    attribution_pl: z.string().nullable()
  })),
  limitations_pl: z.array(z.string()),
  references: z.array(z.object({ id: z.string(), title_pl: z.string(), url: z.string() }))
});

export type BackendReport = z.infer<typeof BackendReportSchema>;
export type BackendMetric = z.infer<typeof metric>;
export type BackendRange = z.infer<typeof range>;
export type BackendGeometry = z.infer<typeof geometry>;

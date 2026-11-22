import { useState } from 'react';
import { z } from 'zod';
import type { BackendReport } from '@/types/backendReport';
import { storageGet, storageSet } from '@/utils/storage';
import type { RecommendationSite } from './recommendationGroups';

const outcomeSchema = z.enum(['confirmed', 'different']);
const checksSchema = z.record(outcomeSchema);
type Checks = z.infer<typeof checksSchema>;
export type FieldOutcome = '' | z.infer<typeof outcomeSchema>;

function load(key: string): Checks {
  try {
    const parsed = checksSchema.safeParse(JSON.parse(storageGet(key) ?? '{}'));
    return parsed.success ? parsed.data : {};
  } catch {
    return {};
  }
}

function siteKey(site: RecommendationSite): string {
  // Terrain IDs are assigned in order. Match geometry too to avoid reusing an observation at a different site.
  return JSON.stringify([site.id, site.geometry]);
}

export function useFieldChecks(report: BackendReport) {
  const key = `vedra.fieldChecks:${JSON.stringify([
    report.parcel.parcel_id, report.crop_code ?? report.crop_name_pl, report.analysis_date
  ])}`;
  const [state, setState] = useState(() => ({ key, checks: load(key), storageFailed: false }));
  const checks = state.key === key ? state.checks : load(key);

  function outcome(site: RecommendationSite): FieldOutcome {
    return checks[siteKey(site)] ?? '';
  }

  function record(site: RecommendationSite, value: FieldOutcome) {
    // Read storage before writing so observations from another open tab are preserved.
    const current = state.key === key && state.storageFailed ? checks : load(key);
    const next = { ...current };
    const location = siteKey(site);
    if (value) next[location] = value;
    else delete next[location];
    const encoded = Object.keys(next).length ? JSON.stringify(next) : null;
    storageSet(key, encoded);
    setState({ key, checks: next, storageFailed: storageGet(key) !== encoded });
  }

  return { key, outcome, record, storageFailed: state.key === key && state.storageFailed };
}

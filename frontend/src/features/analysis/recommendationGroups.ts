import { pl } from '@/constants/pl';
import type { BackendGeometry, BackendMetric, BackendReport } from '@/types/backendReport';

type Recommendation = BackendReport['recommendations'][number];

export interface RecommendationSite {
  number: number;
  geometry: BackendGeometry;
  note: string;
  evidence: BackendMetric[];
}

interface Action {
  recommendation: Recommendation;
  instruction: string;
  evidence: BackendMetric[];
  sites: RecommendationSite[];
}

export function groupRecommendations(items: Recommendation[]): Action[] {
  const groups = new Map<string, Action>();
  const outsideSuffix = ` ${pl.backend.outsideSite}`;
  for (const item of items) {
    const outside = item.geometry && item.action_pl.endsWith(outsideSuffix);
    const instruction = outside ? item.action_pl.slice(0, -outsideSuffix.length) : item.action_pl;
    const key = item.geometry
      ? JSON.stringify([item.category, item.title_pl, instruction, item.why_pl, [...item.reference_ids].sort()])
      : item.id;
    let action = groups.get(key);
    if (!action) {
      action = { recommendation: item, instruction, evidence: item.geometry ? [] : item.evidence, sites: [] };
      groups.set(key, action);
    }
    if (item.geometry) {
      action.sites.push({
        number: action.sites.length + 1,
        geometry: item.geometry,
        note: outside ? pl.backend.outsideSite : '',
        evidence: item.evidence
      });
    }
  }

  return [...groups.values()].map((action) => {
    const [first, ...remaining] = action.sites;
    if (!first || !remaining.length) return action;
    const keyOf = (metric: BackendMetric) => JSON.stringify(metric);
    const others = remaining.map((site) => new Set(site.evidence.map(keyOf)));
    const evidence = first.evidence.filter((metric) => others.every((set) => set.has(keyOf(metric))));
    const common = new Set(evidence.map(keyOf));
    return {
      ...action,
      evidence,
      sites: action.sites.map((site) => ({ ...site, evidence: site.evidence.filter((metric) => !common.has(keyOf(metric))) }))
    };
  });
}

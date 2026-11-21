import { queryOptions, useQueries, useQuery } from '@tanstack/react-query';
import { BACKEND_CROP_CODES, CROPS } from '@/constants/crops';
import { pl } from '@/constants/pl';
import { getAnalysisStatus, startAnalysis, USE_MOCK } from '@/services/analysisApi';
import { ApiError } from '@/services/http';
import { mockAnalyze } from '@/services/mockAnalysis';
import { isParcelId } from '@/utils/validation';
import { useAnalysisStore } from '../store';

// Two-second refresh cadence for the 30-second job budget in backend/README.md.
const POLL_INTERVAL_MS = 2_000;

export function useAnalysis({ active = true }: { active?: boolean } = {}) {
  const confirmed = useAnalysisStore((s) => s.confirmed);
  const cropIds = useAnalysisStore((s) => s.cropIds);
  const date = useAnalysisStore((s) => s.date);
  const demoMode = USE_MOCK || !!(confirmed?.isCustom || confirmed?.isDemo || confirmed?.parts);
  const parcelId = confirmed && !demoMode && isParcelId(confirmed.id) ? confirmed.id : null;

  const demo = useQuery({
    queryKey: ['demo-analysis', confirmed, [...cropIds].sort(), date],
    queryFn: ({ signal }) => {
      if (!confirmed) throw new Error(pl.error.unknown);
      return mockAnalyze({
        parcelId: confirmed.id,
        lat: confirmed.center.lat,
        lng: confirmed.center.lng,
        areaHa: confirmed.areaHa,
        cropIds,
        date
      }, signal);
    },
    enabled: active && demoMode && confirmed !== null && cropIds.length > 0,
    staleTime: Infinity,
    retry: false
  });

  const cropGroups = new Map<string, string[]>();
  for (const crop of CROPS) {
    const code = BACKEND_CROP_CODES[crop.id];
    if (!code || !cropIds.includes(crop.id)) continue;
    const names = cropGroups.get(code) ?? [];
    names.push(crop.name);
    cropGroups.set(code, names);
  }
  const crops = parcelId ? Array.from(cropGroups, ([code, names]) => ({ code, names })) : [];

  const submissions = useQueries({
    queries: crops.map(({ code }) => ({
      queryKey: ['analysis-job', parcelId, code, date],
      // A POST may have succeeded when its response is interrupted. Only an explicit retry submits again.
      queryFn: () => startAnalysis(parcelId!, code, date),
      enabled: active,
      staleTime: Infinity,
      retry: false,
      retryOnMount: false,
      refetchOnReconnect: false
    }))
  });

  const statuses = useQueries({
    queries: crops.map(({ code }, index) => {
      const analysisId = submissions[index]?.data;
      return queryOptions({
        queryKey: ['analysis-status', code, analysisId],
        queryFn: ({ signal }) => getAnalysisStatus(analysisId!, signal),
        enabled: active && analysisId !== undefined,
        staleTime: Infinity,
        retry: 1,
        refetchInterval: (query) => {
          const status = query.state.data?.status;
          return !active || query.state.status === 'error' || status === 'done' || status === 'error'
            ? false
            : POLL_INTERVAL_MS;
        }
      });
    })
  });

  const jobs = crops.map((crop, i) => {
    const submission = submissions[i]!;
    const status = statuses[i]!;
    const job = status.data;
    const failedJob = job?.status === 'error';
    const lostJob = status.error instanceof ApiError && status.error.status === 404;
    const error = submission.isFetching || status.isFetching
      ? null
      : submission.error?.message ?? status.error?.message ?? (failedJob ? job.error || pl.error.unknown : null);

    return {
      ...crop,
      analysisId: submission.data,
      report: job?.status === 'done' ? job.report : undefined,
      progress: submission.isFetching ? [] : job?.progress ?? [],
      error,
      retry: () => (failedJob || lostJob || submission.isError ? void submission.refetch() : void status.refetch())
    };
  });

  const selectionError = confirmed && !demoMode && !parcelId ? pl.error.invalidParcel : null;
  return { demo, demoMode, jobs, selectionError };
}

export type AnalysisJob = ReturnType<typeof useAnalysis>['jobs'][number];

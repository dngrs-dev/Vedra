import { queryOptions, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { BACKEND_CROP_CODES, CROPS } from '@/constants/crops';
import { GROUP_CONCURRENCY, GROUP_JOB_LIMIT } from '@/constants/groupAnalysis';
import { pl } from '@/constants/pl';
import { getAnalysisStatus, startAnalysis, USE_MOCK } from '@/services/analysisApi';
import { ApiError } from '@/services/http';
import { mockAnalyze } from '@/services/mockAnalysis';
import { isParcelId } from '@/utils/validation';
import { useAnalysisStore } from '../store';

// Two-second refresh cadence for the 30-second job budget in backend/README.md.
const POLL_INTERVAL_MS = 2_000;

function statusKey(code: string, analysisId: string | undefined) {
  return ['analysis-status', code, analysisId] as const;
}

export function useAnalysis({ active = true }: { active?: boolean } = {}) {
  const client = useQueryClient();
  const confirmed = useAnalysisStore((s) => s.confirmed);
  const cropIds = useAnalysisStore((s) => s.cropIds);
  const date = useAnalysisStore((s) => s.date);
  const demoMode = USE_MOCK || !!(confirmed?.isCustom || confirmed?.isDemo);
  const isGroup = !demoMode && !!confirmed?.parts;
  const identifiers = confirmed && !demoMode ? confirmed.parts?.map(({ id }) => id) ?? [confirmed.id] : [];
  const parcelIds = [...new Map(identifiers.map((id) => [id.toLowerCase(), id])).values()];

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
  const crops = Array.from(cropGroups, ([code, names]) => ({ code, names }));
  const invalidSelection = confirmed && !demoMode && (!parcelIds.length || parcelIds.some((id) => !isParcelId(id)));
  const selectionError = invalidSelection ? pl.error.invalidParcel
    : isGroup && parcelIds.length * crops.length > GROUP_JOB_LIMIT ? pl.batch.tooManyJobs(GROUP_JOB_LIMIT)
    : parcelIds.length && !crops.length ? pl.batch.noSupportedCrops : null;
  const tasks = selectionError ? [] : parcelIds.flatMap((parcelId) => crops.map((crop) => ({
    ...crop, parcelId, key: ['analysis-job', parcelId, crop.code, date] as const
  })));

  // Count already submitted work before admitting new jobs, including after switching report views.
  const known = tasks.map(({ key, code }) => {
    const submission = client.getQueryState<string>(key);
    const status = submission?.data
      ? client.getQueryState<Awaited<ReturnType<typeof getAnalysisStatus>>>(statusKey(code, submission.data))
      : undefined;
    const finished = status?.data?.status === 'done' || status?.data?.status === 'error' || status?.status === 'error';
    return { submission, inFlight: submission?.fetchStatus === 'fetching' || (!!submission?.data && !finished) };
  });
  let available = GROUP_CONCURRENCY - known.filter(({ inFlight }) => inFlight).length;
  const canSubmit = known.map(({ submission, inFlight }) => {
    if (!active) return false;
    if (!isGroup) return true;
    if (inFlight || submission?.data || submission?.status === 'error' || available <= 0) return false;
    available--;
    return true;
  });

  const submissions = useQueries({
    queries: tasks.map(({ code, key, parcelId }, index) => ({
      queryKey: key,
      // A POST may have succeeded when its response is interrupted. Only an explicit retry submits again.
      queryFn: () => startAnalysis(parcelId, code, date),
      enabled: canSubmit[index] ?? false,
      staleTime: Infinity,
      retry: false,
      retryOnMount: false,
      refetchOnReconnect: false
    }))
  });

  const statuses = useQueries({
    queries: tasks.map(({ code, parcelId }, index) => {
      const analysisId = submissions[index]?.data;
      return queryOptions({
        queryKey: analysisId ? statusKey(code, analysisId) : ['analysis-status-pending', parcelId, code],
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

  const jobs = tasks.map(({ code, names, parcelId }, i) => {
    const submission = submissions[i]!;
    const status = statuses[i]!;
    const job = status.data;
    const failedJob = job?.status === 'error';
    const lostJob = status.error instanceof ApiError && status.error.status === 404;
    const error = submission.isFetching || status.isFetching
      ? null
      : submission.error?.message ?? status.error?.message ?? (failedJob ? job.error || pl.error.unknown : null);

    return {
      code,
      names,
      parcelId,
      analysisId: submission.data,
      report: job?.status === 'done' ? job.report : undefined,
      progress: submission.isFetching ? [] : job?.progress ?? [],
      queued: isGroup && !error && (job?.status === 'queued' || (!submission.data && submission.fetchStatus === 'idle')),
      error,
      retry: () => (failedJob || lostJob || submission.isError ? void submission.refetch() : void status.refetch())
    };
  });

  return { demo, demoMode, isGroup, jobs, selectionError };
}

export type AnalysisJob = ReturnType<typeof useAnalysis>['jobs'][number];

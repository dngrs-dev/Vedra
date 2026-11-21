import { useQuery } from '@tanstack/react-query';
import { analyze } from '@/services/analysisApi';
import { useAnalysisStore } from '../store';

/**
 * Запрашивает анализ ТОЛЬКО для подтверждённой делянки (кнопка «Potwierdź działkę»).
 * Результат кешируется по ключу — страница отчёта берёт его из кеша без повторного расчёта.
 */
export function useAnalysis() {
  const confirmed = useAnalysisStore((s) => s.confirmed);
  const cropIds = useAnalysisStore((s) => s.cropIds);
  const date = useAnalysisStore((s) => s.date);

  return useQuery({
    queryKey: ['analysis', confirmed?.id ?? null, [...cropIds].sort().join(','), date],
    queryFn: ({ signal }) => {
      if (!confirmed) throw new Error('No confirmed parcel');
      return analyze(
        {
          parcelId: confirmed.id,
          lat: confirmed.center.lat,
          lng: confirmed.center.lng,
          areaHa: confirmed.areaHa,
          geometry: confirmed.ring,
          isCustomArea: confirmed.isCustom === true,
          parcels: confirmed.isCustom
            ? []
            : (confirmed.parts ?? [{ id: confirmed.id, ring: confirmed.ring }]).map((p) => ({ id: p.id, geometry: p.ring })),
          outline: confirmed.outline,
          cropIds,
          date
        },
        signal
      );
    },
    enabled: confirmed !== null && cropIds.length > 0,
    staleTime: 10 * 60_000,
    retry: 1,
    // при смене культуры/даты на той же делянке показываем прошлый результат приглушённо
    placeholderData: (prev) => (prev && prev.parcelId === confirmed?.id ? prev : undefined)
  });
}

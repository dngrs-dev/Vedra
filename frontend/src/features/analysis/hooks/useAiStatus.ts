import { useQuery } from '@tanstack/react-query';
import { getAiStatus } from '@/services/scenarioApi';

/** Какая usługa AI подключена на бэкенде и уходят ли данные наружу (нужна ли zgoda RODO). */
export function useAiStatus() {
  return useQuery({ queryKey: ['ai-status'], queryFn: ({ signal }) => getAiStatus(signal), staleTime: Infinity, retry: 1 });
}

import { useQuery } from '@tanstack/react-query';
import { loadVoivodeships } from '@/services/regionsApi';

/** Границы województw: загружаются один раз за сессию. */
export function useVoivodeships() {
  return useQuery({
    queryKey: ['voivodeships'],
    queryFn: loadVoivodeships,
    staleTime: Infinity,
    retry: 1
  });
}

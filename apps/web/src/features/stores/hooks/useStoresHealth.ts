import { useQuery } from '@tanstack/react-query';
import { storesService } from '@/services/stores';

export const storesHealthKey = ['stores', 'health'] as const;

/** Saúde das lojas (busca / monitoramento). Leve: um GET a cada 2 min, compartilhado pelo app. */
export function useStoresHealth() {
  return useQuery({
    queryKey: storesHealthKey,
    queryFn: storesService.getHealth,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

import { useQuery } from '@tanstack/react-query';
import { scheduleService } from '@/services/schedule';

export function useNextCheck() {
  return useQuery({
    queryKey: ['schedule', 'next-check'],
    queryFn: scheduleService.getNextCheck,
    staleTime: 5 * 60_000,
    // Quando o horário passa, o card pede o próximo (ver NextCheckCard); isto é só uma rede de segurança.
    refetchInterval: 15 * 60_000,
  });
}

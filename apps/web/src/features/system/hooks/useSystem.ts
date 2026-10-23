import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { systemService } from '@/services/system';

export const systemKeys = {
  update: ['system', 'update'] as const,
  info: ['system', 'info'] as const,
};

/** O backend já guarda a resposta do GitHub por 6 h; aqui basta não repetir a cada tela. */
const UPDATE_STALE_MS = 60 * 60 * 1000;

export function useUpdateCheck() {
  return useQuery({
    queryKey: systemKeys.update,
    queryFn: () => systemService.getUpdate(),
    staleTime: UPDATE_STALE_MS,
    retry: false,
  });
}

/** "Verificar agora" na tela Sobre: ignora o cache do backend. */
export function useForceUpdateCheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => systemService.getUpdate(true),
    onSuccess: (data) => queryClient.setQueryData(systemKeys.update, data),
  });
}

export function useSystemInfo() {
  return useQuery({
    queryKey: systemKeys.info,
    queryFn: systemService.getInfo,
  });
}

export function useOpenFolder() {
  return useMutation({
    mutationFn: (target: 'data' | 'logs') => systemService.openFolder(target),
  });
}

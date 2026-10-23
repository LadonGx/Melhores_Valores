import { useEffect, useRef } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { HistoryRange, ProductStatus, RefreshAllStatus } from '@mv/types';
import { productsService } from '@/services/products';

export const productKeys = {
  all: ['products'] as const,
  historySummary: (id: string, range: HistoryRange) => ['product', id, 'history', 'summary', range] as const,
  historyTable: (id: string, limit: number) => ['product', id, 'history', 'table', limit] as const,
  groupStats: (ids: string[]) => ['products', 'group-stats', [...ids].sort().join(',')] as const,
  promotions: ['products', 'promotions'] as const,
  refreshAll: ['products', 'refresh-all'] as const,
  /** Prefixo de tudo de um produto (histórico, gráfico, tabela). */
  product: (id: string) => ['product', id] as const,
};

export function useProducts() {
  return useQuery({
    queryKey: productKeys.all,
    queryFn: productsService.getAll,
  });
}

export function usePromotions() {
  return useQuery({
    queryKey: productKeys.promotions,
    queryFn: productsService.getPromotions,
  });
}

export function useProductHistorySummary(productId: string, range: HistoryRange = '30d') {
  return useQuery({
    queryKey: productKeys.historySummary(productId, range),
    queryFn: () => productsService.getHistorySummary(productId, range),
    enabled: !!productId,
  });
}

export function useGroupPriceStats(productIds: string[]) {
  return useQuery({
    queryKey: productKeys.groupStats(productIds),
    queryFn: () => productsService.getGroupStats(productIds),
    enabled: productIds.length > 0,
  });
}

export function useProductHistoryTable(productId: string, limit = 20) {
  return useInfiniteQuery({
    queryKey: productKeys.historyTable(productId, limit),
    queryFn: ({ pageParam }) => productsService.getHistoryTable(productId, pageParam, limit),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.page < lastPage.totalPages ? lastPage.page + 1 : undefined),
    enabled: !!productId,
  });
}

export function useAddProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (req: { url: string; name?: string; image_url?: string; price?: number | null; in_stock?: boolean }) =>
      productsService.add(req),
    onSuccess: () => {
      // Produto criado em background (fila de tarefas) — revalida após delay
      setTimeout(() => queryClient.invalidateQueries({ queryKey: productKeys.all }), 5_000);
    },
  });
}

export function useRemoveProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (productId: string) => productsService.remove(productId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export function useRescrapeProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (url: string) => productsService.rescrape(url),
    onSuccess: () => {
      setTimeout(() => queryClient.invalidateQueries({ queryKey: productKeys.all }), 8_000);
    },
  });
}

export function useRefreshPrice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (productId: string) => productsService.refreshPrice(productId),
    onSuccess: (_result, productId) => {
      // O endpoint é síncrono — resultado já está no DB quando voltamos.
      // ['products'] cobre lista, promoções e estatísticas de grupo; ['product', id]
      // cobre o histórico/gráfico abertos no modal de detalhes.
      queryClient.invalidateQueries({ queryKey: productKeys.all });
      queryClient.invalidateQueries({ queryKey: productKeys.product(productId) });
    },
  });
}

export function useUpdateProductName() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ productId, name }: { productId: string; name: string }) =>
      productsService.updateName(productId, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export function useUpdateProductStatus() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ productId, status }: { productId: string; status: ProductStatus }) =>
      productsService.updateStatus(productId, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: productKeys.all }),
  });
}

export const REFRESH_POLL_RUNNING_MS = 1_500;
export const REFRESH_POLL_IDLE_MS = 30_000;

/**
 * Checagem completa ("Atualizar todos" ou a automática de 6 h): inicia e
 * acompanha o progresso. Enquanto roda, consulta a cada 1,5 s e revalida a
 * lista a cada produto concluído; parado, consulta a cada 30 s só para notar
 * quando a checagem automática começar.
 */
export function useRefreshAll(options: { onFinished?: (status: RefreshAllStatus) => void } = {}) {
  const queryClient = useQueryClient();
  const onFinished = useRef(options.onFinished);
  onFinished.current = options.onFinished;

  const status = useQuery({
    queryKey: productKeys.refreshAll,
    queryFn: productsService.getRefreshAllStatus,
    refetchInterval: (query) => (query.state.data?.running ? REFRESH_POLL_RUNNING_MS : REFRESH_POLL_IDLE_MS),
  });

  const running = status.data?.running ?? false;
  const done = status.data?.done ?? 0;
  const wasRunning = useRef(false);

  useEffect(() => {
    if (running && done > 0) {
      // Cada produto concluído já está no banco: a lista vai se atualizando sozinha
      queryClient.invalidateQueries({ queryKey: productKeys.all, exact: true });
    }
  }, [running, done, queryClient]);

  useEffect(() => {
    if (wasRunning.current && !running && status.data) {
      queryClient.invalidateQueries({ queryKey: productKeys.all });
      queryClient.invalidateQueries({ queryKey: ['product'] });
      onFinished.current?.(status.data);
    }
    wasRunning.current = running;
  }, [running, status.data, queryClient]);

  const start = useMutation({
    mutationFn: productsService.startRefreshAll,
    onSuccess: (data) => queryClient.setQueryData(productKeys.refreshAll, data),
  });

  return {
    status: status.data,
    isRunning: running,
    start: start.mutate,
    isStarting: start.isPending,
  };
}
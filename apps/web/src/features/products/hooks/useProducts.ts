import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ProductStatus } from '@mv/types';
import { productsService } from '@/services/products';

export const productKeys = {
  all: ['products'] as const,
  history: (id: string) => ['product', id, 'history'] as const,
  promotions: ['products', 'promotions'] as const,
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

export function useProductHistory(productId: string) {
  return useQuery({
    queryKey: productKeys.history(productId),
    queryFn: () => productsService.getHistory(productId),
    enabled: !!productId,
  });
}

export function useAddProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (req: { url: string; name?: string; image_url?: string; price?: number | null; in_stock?: boolean }) =>
      productsService.add(req),
    onSuccess: () => {
      // Produto criado em background pelo Celery — revalida após delay
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
    onSuccess: () => {
      // O endpoint é síncrono — resultado já está no DB quando voltamos
      queryClient.invalidateQueries({ queryKey: productKeys.all });
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

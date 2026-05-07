import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { productsService } from '@/services/products';

export const productKeys = {
  all: ['products'] as const,
  history: (id: string) => ['product', id, 'history'] as const,
};

export function useProducts() {
  return useQuery({
    queryKey: productKeys.all,
    queryFn: productsService.getAll,
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
      // Aguarda o Celery processar antes de revalidar
      setTimeout(() => queryClient.invalidateQueries({ queryKey: productKeys.all }), 8_000);
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

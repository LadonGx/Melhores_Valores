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
    mutationFn: (url: string) => productsService.add(url),
    onSuccess: () => {
      // Produto criado em background pelo Celery — revalida após delay
      setTimeout(() => queryClient.invalidateQueries({ queryKey: productKeys.all }), 5_000);
    },
  });
}

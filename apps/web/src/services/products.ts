import type { AddProductResponse, Product, ProductWithHistory } from '@mv/types';
import { api } from './api';

export const productsService = {
  getAll: async (): Promise<{ total: number; products: Product[] }> => {
    const { data } = await api.get('/products');
    return data;
  },

  add: async (url: string): Promise<AddProductResponse> => {
    const { data } = await api.post<AddProductResponse>('/monitor/add', { url });
    return data;
  },

  getHistory: async (productId: string): Promise<ProductWithHistory> => {
    const { data } = await api.get<ProductWithHistory>(`/product/${productId}/history`);
    return data;
  },
};

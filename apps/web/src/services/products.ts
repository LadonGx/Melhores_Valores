import type { AddProductResponse, Product, ProductWithHistory, RefreshPriceResponse } from '@mv/types';
import { api } from './api';

export const productsService = {
  getAll: async (): Promise<{ total: number; products: Product[] }> => {
    const { data } = await api.get('/products');
    return data;
  },

  add: async (req: {
    url: string;
    name?: string;
    image_url?: string;
    price?: number | null;
    in_stock?: boolean;
  }): Promise<AddProductResponse> => {
    const { data } = await api.post<AddProductResponse>('/monitor/add', req);
    return data;
  },

  remove: async (productId: string): Promise<void> => {
    await api.delete(`/product/${productId}`);
  },

  getHistory: async (productId: string): Promise<ProductWithHistory> => {
    const { data } = await api.get<ProductWithHistory>(`/product/${productId}/history`);
    return data;
  },

  rescrape: async (url: string): Promise<AddProductResponse> => {
    const { data } = await api.post<AddProductResponse>('/monitor/add', { url });
    return data;
  },

  refreshPrice: async (productId: string): Promise<RefreshPriceResponse> => {
    // Timeout de 60s — Playwright pode demorar até 30s em sites lentos
    const { data } = await api.post<RefreshPriceResponse>(
      `/product/${productId}/refresh`,
      {},
      { timeout: 60_000 },
    );
    return data;
  },

  updateName: async (productId: string, name: string): Promise<void> => {
    await api.patch(`/product/${productId}/name`, { name });
  },
};

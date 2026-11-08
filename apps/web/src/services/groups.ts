import type { ProductGroup } from '@mv/types';
import { api } from './api';

export const groupsService = {
  getAll: async (): Promise<ProductGroup[]> => {
    const { data } = await api.get<{ groups: ProductGroup[] }>('/groups');
    return data.groups;
  },

  create: async (name: string, productIds: string[]): Promise<ProductGroup> => {
    const { data } = await api.post<ProductGroup>('/groups', { name, product_ids: productIds });
    return data;
  },

  remove: async (groupId: string): Promise<void> => {
    await api.delete(`/groups/${groupId}`);
  },

  removeProduct: async (groupId: string, productId: string): Promise<ProductGroup | null> => {
    const { data } = await api.delete<{ group: ProductGroup | null }>(
      `/groups/${groupId}/products/${productId}`,
    );
    return data.group;
  },
};

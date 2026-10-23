import type { ProductGroup } from '@mv/types';
import { api } from './api';

export type GroupUpdateResponse = ProductGroup | { deleted: true; id: string };

export const groupsService = {
  list: async (): Promise<ProductGroup[]> => {
    const { data } = await api.get<{ groups: ProductGroup[] }>('/groups');
    return data.groups;
  },

  create: async (name: string, productIds: string[]): Promise<ProductGroup> => {
    const { data } = await api.post<ProductGroup>('/groups', { name, productIds });
    return data;
  },

  /** Com menos de 2 anúncios o backend desfaz o grupo e responde { deleted: true }. */
  update: async (
    groupId: string,
    changes: { name?: string; productIds?: string[] },
  ): Promise<GroupUpdateResponse> => {
    const { data } = await api.patch<GroupUpdateResponse>(`/groups/${groupId}`, changes);
    return data;
  },

  remove: async (groupId: string): Promise<void> => {
    await api.delete(`/groups/${groupId}`);
  },

  /** Migração única dos grupos que ficavam no localStorage. Idempotente no backend. */
  importLegacy: async (groups: ProductGroup[]): Promise<{ imported: number; skipped: number }> => {
    const { data } = await api.post<{ imported: number; skipped: number }>('/groups/import', { groups });
    return data;
  },
};

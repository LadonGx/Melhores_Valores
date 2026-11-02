import type { StoresHealthResponse } from '@mv/types';
import { api } from './api';

export const storesService = {
  getHealth: async (): Promise<StoresHealthResponse> => {
    const { data } = await api.get<StoresHealthResponse>('/stores/health');
    return data;
  },
};

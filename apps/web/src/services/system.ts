import type { SystemInfo, UpdateInfo } from '@mv/types';
import { api } from './api';

export const systemService = {
  getUpdate: async (force = false): Promise<UpdateInfo> => {
    const { data } = await api.get<UpdateInfo>('/system/update', { params: force ? { force: true } : {} });
    return data;
  },

  getInfo: async (): Promise<SystemInfo> => {
    const { data } = await api.get<SystemInfo>('/system/info');
    return data;
  },

  openFolder: async (target: 'data' | 'logs'): Promise<void> => {
    await api.post('/system/open-folder', { target });
  },
};

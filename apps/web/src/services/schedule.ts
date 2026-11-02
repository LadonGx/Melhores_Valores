import type { NextCheckResponse } from '@mv/types';
import { api } from './api';

export const scheduleService = {
  getNextCheck: async (): Promise<NextCheckResponse> => {
    const { data } = await api.get<NextCheckResponse>('/schedule/next-check');
    return data;
  },
};

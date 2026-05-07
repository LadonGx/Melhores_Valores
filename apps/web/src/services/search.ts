import type { SearchResponse, SearchResultsResponse } from '@mv/types';
import { api } from './api';

export const searchService = {
  start: async (query: string): Promise<SearchResponse> => {
    const { data } = await api.post<SearchResponse>('/search', { query });
    return data;
  },

  getResults: async (searchId: string): Promise<SearchResultsResponse> => {
    const { data } = await api.get<SearchResultsResponse>(`/search/${searchId}`);
    return data;
  },
};

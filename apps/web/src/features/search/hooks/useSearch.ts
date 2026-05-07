import { useMutation, useQuery } from '@tanstack/react-query';
import { searchService } from '@/services/search';

export const searchKeys = {
  results: (id: string) => ['search', id, 'results'] as const,
};

export function useSearchResults(searchId: string) {
  return useQuery({
    queryKey: searchKeys.results(searchId),
    queryFn: () => searchService.getResults(searchId),
    enabled: !!searchId,
    refetchInterval: (query) => {
      const total = query.state.data?.total ?? 0;
      return total > 0 ? false : 3000;
    },
  });
}

export function useStartSearch() {
  return useMutation({
    mutationFn: (query: string) => searchService.start(query),
  });
}

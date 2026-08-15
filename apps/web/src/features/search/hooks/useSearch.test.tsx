import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { SearchResultsResponse, SearchResponse } from '@mv/types';
import { searchKeys, useSearchResults, useStartSearch } from './useSearch';
import { searchService } from '@/services/search';

vi.mock('@/services/search', () => ({
  searchService: {
    start: vi.fn(),
    getResults: vi.fn(),
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const emptyResults: SearchResultsResponse = { search_id: 's1', total: 0, results: [] };
const populatedResults: SearchResultsResponse = {
  search_id: 's1',
  total: 1,
  results: [
    {
      id: 'r1',
      search_id: 's1',
      store: 'amazon',
      title: 'iPhone 15',
      price: 4999,
      currency: 'BRL',
      image_url: null,
      product_url: 'https://amazon.com.br/iphone-15',
      rating: null,
      review_count: null,
    },
  ],
};

describe('searchKeys', () => {
  it('builds the results query key', () => {
    expect(searchKeys.results('s1')).toEqual(['search', 's1', 'results']);
  });
});

describe('useSearchResults', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('stays disabled and never calls getResults when searchId is empty', async () => {
    const { result } = renderHook(() => useSearchResults(''), { wrapper: createWrapper() });

    expect(result.current.fetchStatus).toBe('idle');
    expect(searchService.getResults).not.toHaveBeenCalled();
  });

  it('fetches results for a non-empty searchId', async () => {
    vi.mocked(searchService.getResults).mockResolvedValue(populatedResults);

    const { result } = renderHook(() => useSearchResults('s1'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.data).toEqual(populatedResults));
    expect(searchService.getResults).toHaveBeenCalledWith('s1');
  });

  it('keeps polling every 3s while total is 0, and stops once results arrive', async () => {
    vi.useFakeTimers();
    const getResults = vi.mocked(searchService.getResults);
    getResults.mockResolvedValue(emptyResults);

    const { result } = renderHook(() => useSearchResults('s1'), { wrapper: createWrapper() });

    await vi.waitFor(() => expect(result.current.data).toEqual(emptyResults));
    expect(getResults).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(3000);
    expect(getResults).toHaveBeenCalledTimes(2);

    getResults.mockResolvedValue(populatedResults);
    await vi.advanceTimersByTimeAsync(3000);
    await vi.waitFor(() => expect(result.current.data).toEqual(populatedResults));
    const callsAfterResults = getResults.mock.calls.length;

    await vi.advanceTimersByTimeAsync(3000);
    expect(getResults).toHaveBeenCalledTimes(callsAfterResults);

    vi.useRealTimers();
  });
});

describe('useStartSearch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls searchService.start with the given params and reports pending/success state', async () => {
    let resolveStart!: (value: SearchResponse) => void;
    const startPromise = new Promise<SearchResponse>((resolve) => {
      resolveStart = resolve;
    });
    vi.mocked(searchService.start).mockReturnValue(startPromise);

    const { result } = renderHook(() => useStartSearch(), { wrapper: createWrapper() });

    result.current.mutate({ query: 'iphone 15', min_price: 100, max_price: 5000 });

    await waitFor(() =>
      expect(searchService.start).toHaveBeenCalledWith({ query: 'iphone 15', min_price: 100, max_price: 5000 }),
    );
    await waitFor(() => expect(result.current.isPending).toBe(true));

    resolveStart({ status: 'processing', task_id: 't1', query: 'iphone 15', message: 'ok' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.task_id).toBe('t1');
  });

  it('reports error state when the request fails', async () => {
    vi.mocked(searchService.start).mockRejectedValue(new Error('network error'));

    const { result } = renderHook(() => useStartSearch(), { wrapper: createWrapper() });
    result.current.mutate({ query: 'iphone 15' });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

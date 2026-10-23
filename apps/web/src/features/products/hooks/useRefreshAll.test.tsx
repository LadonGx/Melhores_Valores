import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { RefreshAllStatus } from '@mv/types';
import { productKeys, useRefreshAll } from './useProducts';
import { productsService } from '@/services/products';

vi.mock('@/services/products', () => ({
  productsService: {
    getRefreshAllStatus: vi.fn(),
    startRefreshAll: vi.fn(),
  },
}));

const status = (over: Partial<RefreshAllStatus>): RefreshAllStatus => ({
  running: false, total: 0, done: 0, ok: 0, failed: 0, ...over,
});

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, invalidate, wrapper };
}

describe('useRefreshAll', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reports idle when nothing is running', async () => {
    vi.mocked(productsService.getRefreshAllStatus).mockResolvedValue(status({}));
    const { wrapper } = setup();
    const { result } = renderHook(() => useRefreshAll(), { wrapper });

    await waitFor(() => expect(result.current.status).toBeDefined());
    expect(result.current.isRunning).toBe(false);
  });

  it('start stores the batch returned by the API (no wait for the next poll)', async () => {
    vi.mocked(productsService.getRefreshAllStatus).mockResolvedValue(status({}));
    vi.mocked(productsService.startRefreshAll).mockResolvedValue(
      status({ running: true, total: 3, trigger: 'manual', started: true }),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => useRefreshAll(), { wrapper });
    await waitFor(() => expect(result.current.status).toBeDefined());

    act(() => result.current.start());

    await waitFor(() => expect(result.current.isRunning).toBe(true));
    expect(result.current.status?.total).toBe(3);
  });

  it('calls onFinished and refreshes products/history when the batch ends', async () => {
    const onFinished = vi.fn();
    vi.mocked(productsService.getRefreshAllStatus).mockResolvedValue(
      status({ running: true, total: 2, done: 1, ok: 1 }),
    );
    const { queryClient, invalidate, wrapper } = setup();
    const { result } = renderHook(() => useRefreshAll({ onFinished }), { wrapper });
    await waitFor(() => expect(result.current.isRunning).toBe(true));

    // em andamento: revalida a lista a cada produto concluído
    expect(invalidate).toHaveBeenCalledWith({ queryKey: productKeys.all, exact: true });

    const done = status({ running: false, total: 2, done: 2, ok: 1, failed: 1 });
    act(() => queryClient.setQueryData(productKeys.refreshAll, done));

    await waitFor(() => expect(onFinished).toHaveBeenCalledWith(done));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: productKeys.all });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['product'] });
  });

  it('does not call onFinished when the app opens with an already finished batch', async () => {
    const onFinished = vi.fn();
    vi.mocked(productsService.getRefreshAllStatus).mockResolvedValue(status({ total: 5, done: 5, ok: 5 }));
    const { wrapper } = setup();
    const { result } = renderHook(() => useRefreshAll({ onFinished }), { wrapper });

    await waitFor(() => expect(result.current.status).toBeDefined());
    expect(onFinished).not.toHaveBeenCalled();
  });
});

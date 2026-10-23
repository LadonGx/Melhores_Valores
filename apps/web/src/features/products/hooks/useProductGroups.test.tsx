import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { ProductGroup } from '@mv/types';
import { LEGACY_STORAGE_KEY, useProductGroups } from './useProductGroups';
import { groupsService } from '@/services/groups';

vi.mock('@/services/groups', () => ({
  groupsService: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    importLegacy: vi.fn(),
  },
}));

const group: ProductGroup = { id: 'g1', name: 'Livros', productIds: ['a', 'b', 'c'], createdAt: '2026-09-01T12:00:00Z' };

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('useProductGroups', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(groupsService.list).mockResolvedValue([group]);
  });

  it('loads groups from the backend', async () => {
    const { result } = renderHook(() => useProductGroups(), { wrapper });
    await waitFor(() => expect(result.current.groups).toEqual([group]));
    expect(groupsService.importLegacy).not.toHaveBeenCalled();
  });

  it('migrates groups left in localStorage once and removes the local copy', async () => {
    const legacy = [{ ...group, id: 'antigo' }];
    localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify(legacy));
    vi.mocked(groupsService.importLegacy).mockResolvedValue({ imported: 1, skipped: 0 });

    renderHook(() => useProductGroups(), { wrapper });

    await waitFor(() => expect(groupsService.importLegacy).toHaveBeenCalledWith(legacy));
    await waitFor(() => expect(localStorage.getItem(LEGACY_STORAGE_KEY)).toBeNull());
  });

  it('keeps the local copy when the migration fails, to retry next time', async () => {
    localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify([group]));
    vi.mocked(groupsService.importLegacy).mockRejectedValue(new Error('offline'));

    renderHook(() => useProductGroups(), { wrapper });

    await waitFor(() => expect(groupsService.importLegacy).toHaveBeenCalled());
    expect(localStorage.getItem(LEGACY_STORAGE_KEY)).not.toBeNull();
  });

  it('ignores corrupted localStorage content', async () => {
    localStorage.setItem(LEGACY_STORAGE_KEY, '{nao-e-json');
    const { result } = renderHook(() => useProductGroups(), { wrapper });
    await waitFor(() => expect(result.current.groups).toEqual([group]));
    expect(groupsService.importLegacy).not.toHaveBeenCalled();
  });

  it('createGroup trims the name', async () => {
    vi.mocked(groupsService.create).mockResolvedValue(group);
    const { result } = renderHook(() => useProductGroups(), { wrapper });
    await waitFor(() => expect(result.current.groups).toHaveLength(1));

    act(() => result.current.createGroup('  Novos  ', ['x', 'y']));

    await waitFor(() => expect(groupsService.create).toHaveBeenCalledWith('Novos', ['x', 'y']));
  });

  it('ungroupProduct sends the remaining products', async () => {
    vi.mocked(groupsService.update).mockResolvedValue({ ...group, productIds: ['a', 'c'] });
    const { result } = renderHook(() => useProductGroups(), { wrapper });
    await waitFor(() => expect(result.current.groups).toHaveLength(1));

    act(() => result.current.ungroupProduct('g1', 'b'));

    await waitFor(() => expect(groupsService.update).toHaveBeenCalledWith('g1', { productIds: ['a', 'c'] }));
  });

  it('deleteGroup calls the backend', async () => {
    vi.mocked(groupsService.remove).mockResolvedValue();
    const { result } = renderHook(() => useProductGroups(), { wrapper });
    await waitFor(() => expect(result.current.groups).toHaveLength(1));

    act(() => result.current.deleteGroup('g1'));

    await waitFor(() => expect(groupsService.remove).toHaveBeenCalledWith('g1'));
  });
});

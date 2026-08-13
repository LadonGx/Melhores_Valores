import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDashboardFilter } from './useDashboardFilter';

const STORAGE_KEY = 'mv_dashboard_filter';

describe('useDashboardFilter', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('starts with the default state when nothing is stored', () => {
    const { result } = renderHook(() => useDashboardFilter());

    expect(result.current.sortOption).toBe('default');
    expect(result.current.hiddenIds).toEqual([]);
  });

  it('loads previously persisted state from localStorage', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ sortOption: 'price-asc', hiddenIds: ['p1'] }));

    const { result } = renderHook(() => useDashboardFilter());

    expect(result.current.sortOption).toBe('price-asc');
    expect(result.current.hiddenIds).toEqual(['p1']);
  });

  it('persists setSortOption to localStorage', () => {
    const { result } = renderHook(() => useDashboardFilter());

    act(() => result.current.setSortOption('name-desc'));

    expect(result.current.sortOption).toBe('name-desc');
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).sortOption).toBe('name-desc');
  });

  it('toggleHidden adds and removes ids', () => {
    const { result } = renderHook(() => useDashboardFilter());

    act(() => result.current.toggleHidden('p1'));
    expect(result.current.hiddenIds).toEqual(['p1']);

    act(() => result.current.toggleHidden('p2'));
    expect(result.current.hiddenIds).toEqual(['p1', 'p2']);

    act(() => result.current.toggleHidden('p1'));
    expect(result.current.hiddenIds).toEqual(['p2']);
  });

  it('showAll clears hiddenIds without touching sortOption', () => {
    const { result } = renderHook(() => useDashboardFilter());

    act(() => result.current.setSortOption('price-desc'));
    act(() => result.current.toggleHidden('p1'));
    act(() => result.current.showAll());

    expect(result.current.hiddenIds).toEqual([]);
    expect(result.current.sortOption).toBe('price-desc');
  });

  it('reset restores both sortOption and hiddenIds to defaults', () => {
    const { result } = renderHook(() => useDashboardFilter());

    act(() => result.current.setSortOption('name-asc'));
    act(() => result.current.toggleHidden('p1'));
    act(() => result.current.reset());

    expect(result.current.sortOption).toBe('default');
    expect(result.current.hiddenIds).toEqual([]);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toEqual({ sortOption: 'default', hiddenIds: [] });
  });
});

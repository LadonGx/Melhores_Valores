import { useCallback, useState } from 'react';
import type { SortOption } from './sortRows';

const STORAGE_KEY = 'mv_dashboard_filter';

interface DashboardFilterState {
  sortOption: SortOption;
  hiddenIds: string[];
}

const DEFAULT_STATE: DashboardFilterState = { sortOption: 'default', hiddenIds: [] };

function loadState(): DashboardFilterState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    return { ...DEFAULT_STATE, ...(JSON.parse(raw) as Partial<DashboardFilterState>) };
  } catch {
    return DEFAULT_STATE;
  }
}

function saveState(state: DashboardFilterState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function useDashboardFilter() {
  const [state, setState] = useState<DashboardFilterState>(loadState);

  const persist = useCallback((next: DashboardFilterState) => {
    saveState(next);
    setState(next);
  }, []);

  const setSortOption = useCallback(
    (sortOption: SortOption) => {
      persist({ ...loadState(), sortOption });
    },
    [persist],
  );

  const toggleHidden = useCallback(
    (id: string) => {
      const current = loadState();
      const hiddenIds = current.hiddenIds.includes(id)
        ? current.hiddenIds.filter((hiddenId) => hiddenId !== id)
        : [...current.hiddenIds, id];
      persist({ ...current, hiddenIds });
    },
    [persist],
  );

  const showAll = useCallback(() => {
    persist({ ...loadState(), hiddenIds: [] });
  }, [persist]);

  const reset = useCallback(() => {
    persist(DEFAULT_STATE);
  }, [persist]);

  return {
    sortOption: state.sortOption,
    hiddenIds: state.hiddenIds,
    setSortOption,
    toggleHidden,
    showAll,
    reset,
  };
}

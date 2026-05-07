import { useState, useCallback } from 'react';
import type { ProductGroup } from '@mv/types';

const STORAGE_KEY = 'mv_product_groups';

function loadGroups(): ProductGroup[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ProductGroup[]) : [];
  } catch {
    return [];
  }
}

function saveGroups(groups: ProductGroup[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(groups));
}

export function useProductGroups() {
  const [groups, setGroups] = useState<ProductGroup[]>(loadGroups);

  const persist = useCallback((next: ProductGroup[]) => {
    saveGroups(next);
    setGroups(next);
  }, []);

  const createGroup = useCallback(
    (name: string, productIds: string[]) => {
      const group: ProductGroup = {
        id: crypto.randomUUID(),
        name: name.trim(),
        productIds,
        createdAt: new Date().toISOString(),
      };
      persist([...loadGroups(), group]);
    },
    [persist],
  );

  const deleteGroup = useCallback(
    (groupId: string) => {
      persist(loadGroups().filter((g) => g.id !== groupId));
    },
    [persist],
  );

  const ungroupProduct = useCallback(
    (groupId: string, productId: string) => {
      const current = loadGroups();
      const next = current
        .map((g) =>
          g.id === groupId ? { ...g, productIds: g.productIds.filter((id) => id !== productId) } : g,
        )
        // Remove groups that end up with fewer than 2 products
        .filter((g) => g.productIds.length >= 2);
      persist(next);
    },
    [persist],
  );

  return { groups, createGroup, deleteGroup, ungroupProduct };
}

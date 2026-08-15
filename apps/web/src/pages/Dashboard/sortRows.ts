export type SortOption = 'default' | 'name-asc' | 'name-desc' | 'price-asc' | 'price-desc';

export interface DashboardRow {
  id: string;
  type: 'group' | 'product';
  name: string;
  price: number | null;
}

function byName(a: DashboardRow, b: DashboardRow): number {
  return a.name.localeCompare(b.name, 'pt-BR');
}

function byPriceAsc(a: DashboardRow, b: DashboardRow): number {
  if (a.price == null) return 1;
  if (b.price == null) return -1;
  return a.price - b.price;
}

function byPriceDesc(a: DashboardRow, b: DashboardRow): number {
  if (a.price == null) return 1;
  if (b.price == null) return -1;
  return b.price - a.price;
}

export function sortRows(rows: DashboardRow[], sortOption: SortOption): DashboardRow[] {
  switch (sortOption) {
    case 'name-asc':
      return [...rows].sort(byName);
    case 'name-desc':
      return [...rows].sort((a, b) => byName(b, a));
    case 'price-asc':
      return [...rows].sort(byPriceAsc);
    case 'price-desc':
      return [...rows].sort(byPriceDesc);
    case 'default':
    default:
      return rows;
  }
}

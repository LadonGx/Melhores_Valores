import { describe, it, expect } from 'vitest';
import { sortRows, type DashboardRow } from './sortRows';

const rows: DashboardRow[] = [
  { id: '1', type: 'product', name: 'Banana', price: 30 },
  { id: '2', type: 'group', name: 'Abacaxi', price: 10 },
  { id: '3', type: 'product', name: 'Cereja', price: null },
  { id: '4', type: 'group', name: 'Damasco', price: 20 },
];

describe('sortRows', () => {
  it('keeps the original order for "default"', () => {
    expect(sortRows(rows, 'default').map((r) => r.id)).toEqual(['1', '2', '3', '4']);
  });

  it('sorts by name ascending (pt-BR locale)', () => {
    expect(sortRows(rows, 'name-asc').map((r) => r.name)).toEqual([
      'Abacaxi',
      'Banana',
      'Cereja',
      'Damasco',
    ]);
  });

  it('sorts by name descending', () => {
    expect(sortRows(rows, 'name-desc').map((r) => r.name)).toEqual([
      'Damasco',
      'Cereja',
      'Banana',
      'Abacaxi',
    ]);
  });

  it('sorts by price ascending, pushing null prices to the end', () => {
    expect(sortRows(rows, 'price-asc').map((r) => r.id)).toEqual(['2', '4', '1', '3']);
  });

  it('sorts by price descending, still pushing null prices to the end', () => {
    expect(sortRows(rows, 'price-desc').map((r) => r.id)).toEqual(['1', '4', '2', '3']);
  });

  it('does not mutate the input array', () => {
    const original = [...rows];
    sortRows(rows, 'name-asc');
    expect(rows).toEqual(original);
  });
});

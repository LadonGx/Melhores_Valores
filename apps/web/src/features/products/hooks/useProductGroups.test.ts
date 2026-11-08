import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProductGroup } from '@mv/types';
import { migrateLegacyGroups } from './useProductGroups';
import { groupsService } from '@/services/groups';

vi.mock('@/services/groups', () => ({
  groupsService: { create: vi.fn() },
}));

const KEY = 'mv_product_groups';

const group = (name: string, productIds: string[]): ProductGroup => ({
  id: `local-${name}`,
  name,
  productIds,
  createdAt: '2026-11-01T00:00:00.000Z',
});

describe('migrateLegacyGroups', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(groupsService.create).mockReset();
  });
  afterEach(() => localStorage.clear());

  it('não faz nada quando não há grupos antigos no navegador', async () => {
    expect(await migrateLegacyGroups([])).toBe(false);
    expect(groupsService.create).not.toHaveBeenCalled();
  });

  it('envia os grupos antigos para o servidor e limpa o localStorage', async () => {
    localStorage.setItem(KEY, JSON.stringify([group('Box Agatha', ['p1', 'p2'])]));

    expect(await migrateLegacyGroups([])).toBe(true);
    expect(groupsService.create).toHaveBeenCalledWith('Box Agatha', ['p1', 'p2']);
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it('não duplica um grupo que já existe no servidor (mesmo nome e anúncios)', async () => {
    localStorage.setItem(KEY, JSON.stringify([group('Box Agatha', ['p2', 'p1'])]));

    await migrateLegacyGroups([{ ...group('Box Agatha', ['p1', 'p2']), id: 'server-1' }]);
    expect(groupsService.create).not.toHaveBeenCalled();
  });

  it('ignora grupos inválidos e segue quando o servidor recusa um grupo', async () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([group('Só um', ['p1']), group('Recusado', ['x1', 'x2']), group('Ok', ['p1', 'p2'])]),
    );
    vi.mocked(groupsService.create).mockRejectedValueOnce(new Error('422'));

    await migrateLegacyGroups([]);
    expect(groupsService.create).toHaveBeenCalledTimes(2);
    expect(groupsService.create).toHaveBeenLastCalledWith('Ok', ['p1', 'p2']);
    expect(localStorage.getItem(KEY)).toBeNull();
  });
});

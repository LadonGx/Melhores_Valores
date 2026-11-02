import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { StoreChannelHealth, StoresHealthResponse } from '@mv/types';
import { StoreHealthPanel } from './StoreHealthPanel';

const ok: StoreChannelHealth = {
  status: 'ok', detail: 'funcionando', category: null,
  last_ok_at: '2026-11-01T21:41:00Z', last_fail_at: null,
};
const loginWall: StoreChannelHealth = {
  status: 'blocked', detail: 'exigindo login', category: 'login_wall',
  last_ok_at: null, last_fail_at: '2026-11-01T22:32:00Z',
};

const data: StoresHealthResponse = {
  stores: [
    { store: 'amazon', label: 'Amazon', status: 'ok', channels: { search: ok, monitor: ok } },
    { store: 'mercadolivre', label: 'Mercado Livre', status: 'partial', channels: { search: loginWall, monitor: ok } },
  ],
};

vi.mock('../hooks/useStoresHealth', () => ({
  useStoresHealth: () => ({ data, isError: false }),
}));

describe('StoreHealthPanel', () => {
  it('explica o bloqueio da busca do Mercado Livre sem esconder que o monitoramento funciona', async () => {
    render(<StoreHealthPanel />);
    expect(screen.getByText('Funcionando')).toBeInTheDocument();
    expect(screen.getByText('Busca exigindo login')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /lojas/i }));
    expect(screen.getAllByText('Monitoramento')).toHaveLength(2);
    expect(screen.getByText(/exigindo login · desde/)).toBeInTheDocument();
  });

  it('modo recolhido mostra só as bolinhas, com o resumo acessível', () => {
    render(<StoreHealthPanel compact />);
    expect(screen.queryByRole('button', { name: /lojas/i })).not.toBeInTheDocument();
    expect(screen.getByTitle('Mercado Livre: Busca exigindo login')).toBeInTheDocument();
  });
});

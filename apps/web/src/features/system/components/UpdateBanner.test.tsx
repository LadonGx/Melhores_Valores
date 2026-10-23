import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { UpdateInfo } from '@mv/types';
import { DISMISSED_KEY, UpdateBanner } from './UpdateBanner';
import { systemService } from '@/services/system';

vi.mock('@/services/system', () => ({
  systemService: { getUpdate: vi.fn() },
}));

const info = (over: Partial<UpdateInfo>): UpdateInfo => ({
  current: '0.1.0',
  latest: '0.2.0',
  update_available: true,
  url: 'https://github.com/LadonGx/Melhores_Valores/releases/tag/v0.2.0',
  published_at: null,
  error: null,
  ...over,
});

function renderBanner() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <UpdateBanner />
    </QueryClientProvider>,
  );
}

describe('UpdateBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('shows the new version with a download link that opens outside the app', async () => {
    vi.mocked(systemService.getUpdate).mockResolvedValue(info({}));
    renderBanner();

    expect(await screen.findByRole('status')).toHaveTextContent('Nova versão disponível: 0.2.0 (você tem a 0.1.0)');
    const link = screen.getByRole('link', { name: 'Baixar →' });
    expect(link).toHaveAttribute('href', info({}).url);
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('stays hidden when there is no update', async () => {
    vi.mocked(systemService.getUpdate).mockResolvedValue(info({ update_available: false, latest: '0.1.0' }));
    renderBanner();
    await waitFor(() => expect(systemService.getUpdate).toHaveBeenCalled());
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('dismissing hides it for that version only', async () => {
    vi.mocked(systemService.getUpdate).mockResolvedValue(info({}));
    const { unmount } = renderBanner();

    await userEvent.click(await screen.findByRole('button', { name: 'Dispensar aviso' }));
    expect(screen.queryByRole('status')).toBeNull();
    expect(localStorage.getItem(DISMISSED_KEY)).toBe('0.2.0');
    unmount();

    // saiu outra versão: o aviso volta
    vi.mocked(systemService.getUpdate).mockResolvedValue(info({ latest: '0.3.0' }));
    renderBanner();
    expect(await screen.findByRole('status')).toHaveTextContent('0.3.0');
  });
});

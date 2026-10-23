import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RefreshPriceButton } from './RefreshPriceButton';
import { productKeys } from '@/features/products/hooks/useProducts';
import { productsService } from '@/services/products';

vi.mock('@/services/products', () => ({
  productsService: { refreshPrice: vi.fn() },
}));

function renderButton() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  render(
    <QueryClientProvider client={queryClient}>
      <RefreshPriceButton productId="p1" />
    </QueryClientProvider>,
  );
  return { invalidate };
}

describe('RefreshPriceButton', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the new price and refreshes the modal data', async () => {
    vi.mocked(productsService.refreshPrice).mockResolvedValue({
      status: 'ok', price: 99.9, in_stock: true, name: 'Mouse', source: 'cascata',
    });
    const { invalidate } = renderButton();

    await userEvent.click(screen.getByRole('button', { name: 'Atualizar preço agora' }));

    expect(await screen.findByRole('status')).toHaveTextContent(/Preço atualizado: R\$\s?99,90/);
    expect(productsService.refreshPrice).toHaveBeenCalledWith('p1');
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: productKeys.product('p1') }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: productKeys.all });
  });

  it('shows the backend message when the store blocks the check', async () => {
    vi.mocked(productsService.refreshPrice).mockResolvedValue({
      status: 'error', reason: 'blocked', detail: 'O site bloqueou a verificação de preço.',
    });
    renderButton();

    await userEvent.click(screen.getByRole('button', { name: 'Atualizar preço agora' }));

    expect(await screen.findByRole('status')).toHaveTextContent('O site bloqueou a verificação de preço.');
  });

  it('explains a timeout', async () => {
    vi.mocked(productsService.refreshPrice).mockRejectedValue(new Error('timeout of 60000ms exceeded'));
    renderButton();

    await userEvent.click(screen.getByRole('button', { name: 'Atualizar preço agora' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Tempo esgotado');
  });
});

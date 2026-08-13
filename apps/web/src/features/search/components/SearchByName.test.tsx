import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import type { SearchResultsResponse, SearchResponse, AddProductResponse } from '@mv/types';
import { SearchByName } from './SearchByName';
import { searchService } from '@/services/search';
import { productsService } from '@/services/products';

vi.mock('@/services/search', () => ({
  searchService: {
    start: vi.fn(),
    getResults: vi.fn(),
  },
}));

vi.mock('@/services/products', () => ({
  productsService: {
    add: vi.fn(),
  },
}));

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const queryInputPlaceholder = /iPhone 15 128GB/i;

const startResponse: SearchResponse = {
  status: 'processing',
  task_id: 't1',
  query: 'iphone 15',
  message: 'ok',
};

const emptyResults: SearchResultsResponse = { search_id: 't1', total: 0, results: [] };
const populatedResults: SearchResultsResponse = {
  search_id: 't1',
  total: 2,
  results: [
    {
      id: 'r1',
      search_id: 't1',
      store: 'amazon',
      title: 'iPhone 15 128GB Azul',
      price: 4999,
      currency: 'BRL',
      image_url: null,
      product_url: 'https://amazon.com.br/iphone-15',
      rating: null,
      review_count: null,
    },
    {
      id: 'r2',
      search_id: 't1',
      store: 'mercadolivre',
      title: 'iPhone 15 128GB Preto',
      price: 4799,
      currency: 'BRL',
      image_url: null,
      product_url: 'https://mercadolivre.com.br/iphone-15',
      rating: null,
      review_count: null,
    },
  ],
};

const addResponse: AddProductResponse = {
  message: 'ok',
  task_id: 'p1',
  status: 'queued',
  url: 'https://amazon.com.br/iphone-15',
  store: 'amazon',
};

async function submitQuery(user: ReturnType<typeof userEvent.setup>, query = 'iphone 15') {
  await user.type(screen.getByPlaceholderText(queryInputPlaceholder), query);
  await user.click(screen.getByRole('button', { name: /buscar/i }));
}

describe('SearchByName', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the search form', () => {
    renderWithClient(<SearchByName />);

    expect(screen.getByPlaceholderText(queryInputPlaceholder)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Preço mín.')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Preço máx.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Buscar' })).toBeInTheDocument();
  });

  it('blocks submit when the query is too short', async () => {
    const user = userEvent.setup();
    renderWithClient(<SearchByName />);

    await submitQuery(user, 'a');

    expect(await screen.findByText('Mínimo de 2 caracteres')).toBeInTheDocument();
    expect(searchService.start).not.toHaveBeenCalled();
  });

  it('blocks submit when a price is negative', async () => {
    const user = userEvent.setup();
    renderWithClient(<SearchByName />);

    await user.type(screen.getByPlaceholderText(queryInputPlaceholder), 'iphone 15');
    const minPriceInput = screen.getByPlaceholderText('Preço mín.');
    fireEvent.change(minPriceInput, { target: { valueAsNumber: -10 } });
    // O atributo min="0" do input dispara validação nativa do HTML5 ao clicar no botão,
    // que bloqueia o submit antes do React rodar — disparamos o evento diretamente para
    // exercitar a validação Zod (defesa em profundidade), como faria um navegador mais permissivo.
    fireEvent.submit(minPriceInput.closest('form')!);

    expect(await screen.findByText('Não pode ser negativo')).toBeInTheDocument();
    expect(searchService.start).not.toHaveBeenCalled();
  });

  it('blocks submit when minPrice is greater than maxPrice', async () => {
    const user = userEvent.setup();
    renderWithClient(<SearchByName />);

    await user.type(screen.getByPlaceholderText(queryInputPlaceholder), 'iphone 15');
    fireEvent.change(screen.getByPlaceholderText('Preço mín.'), { target: { value: '500' } });
    fireEvent.change(screen.getByPlaceholderText('Preço máx.'), { target: { value: '100' } });
    await user.click(screen.getByRole('button', { name: /buscar/i }));

    expect(await screen.findByText('Preço mínimo não pode ser maior que o máximo')).toBeInTheDocument();
    expect(searchService.start).not.toHaveBeenCalled();
  });

  it('starts a search, shows the waiting state, then renders results', async () => {
    const user = userEvent.setup();
    let resolveStart!: (value: SearchResponse) => void;
    vi.mocked(searchService.start).mockReturnValue(
      new Promise((resolve) => {
        resolveStart = resolve;
      }),
    );
    vi.mocked(searchService.getResults).mockResolvedValue(populatedResults);

    renderWithClient(<SearchByName />);
    await submitQuery(user);

    expect(searchService.start).toHaveBeenCalledWith({ query: 'iphone 15', min_price: undefined, max_price: undefined });
    expect(screen.getByText(/Buscando em Amazon e Mercado Livre/)).toBeInTheDocument();
    // O Button troca o texto por um spinner enquanto loading=true, então não há nome acessível aqui.
    expect(screen.getByRole('button')).toBeDisabled();

    await act(async () => {
      resolveStart(startResponse);
    });

    expect(await screen.findByText('iPhone 15 128GB Azul')).toBeInTheDocument();
    expect(screen.getByText('iPhone 15 128GB Preto')).toBeInTheDocument();
    expect(screen.getByText('Amazon')).toBeInTheDocument();
    expect(screen.getByText('Mercado Livre')).toBeInTheDocument();
    expect(screen.getByText(/4\.999,00/)).toBeInTheDocument();
    expect(screen.queryByText(/Buscando em Amazon e Mercado Livre/)).not.toBeInTheDocument();
  });

  it('shows the empty state once the safety timeout elapses without results', async () => {
    vi.useFakeTimers();
    vi.mocked(searchService.start).mockResolvedValue(startResponse);
    vi.mocked(searchService.getResults).mockResolvedValue(emptyResults);

    renderWithClient(<SearchByName />);
    fireEvent.change(screen.getByPlaceholderText(queryInputPlaceholder), { target: { value: 'iphone 15' } });
    fireEvent.submit(screen.getByRole('button', { name: /buscar/i }).closest('form')!);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText(/Buscando em Amazon e Mercado Livre/)).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(screen.getByText('Nenhum resultado encontrado. Tente um termo diferente.')).toBeInTheDocument();

    vi.useRealTimers();
  });

  it('marks a product as monitored after a successful add, without affecting other rows', async () => {
    const user = userEvent.setup();
    vi.mocked(searchService.start).mockResolvedValue(startResponse);
    vi.mocked(searchService.getResults).mockResolvedValue(populatedResults);
    let resolveAdd!: (value: AddProductResponse) => void;
    vi.mocked(productsService.add).mockReturnValue(
      new Promise((resolve) => {
        resolveAdd = resolve;
      }),
    );

    renderWithClient(<SearchByName />);
    await submitQuery(user);
    await screen.findByText('iPhone 15 128GB Azul');

    const monitorButtons = screen.getAllByRole('button', { name: /monitorar/i });
    await user.click(monitorButtons[0]);

    expect(productsService.add).toHaveBeenCalledWith({
      url: 'https://amazon.com.br/iphone-15',
      name: 'iPhone 15 128GB Azul',
      image_url: undefined,
      price: 4999,
      in_stock: true,
    });
    expect(monitorButtons[0]).toBeDisabled();
    expect(monitorButtons[1]).not.toBeDisabled();

    await act(async () => {
      resolveAdd(addResponse);
    });

    expect(await screen.findByText('✓ Adicionado')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /monitorar/i })).not.toBeDisabled();
  });

  it('shows an error toast when adding a product fails, and the toast can be closed', async () => {
    const user = userEvent.setup();
    vi.mocked(searchService.start).mockResolvedValue(startResponse);
    vi.mocked(searchService.getResults).mockResolvedValue(populatedResults);
    vi.mocked(productsService.add).mockRejectedValue(new Error('boom'));

    renderWithClient(<SearchByName />);
    await submitQuery(user);
    await screen.findByText('iPhone 15 128GB Azul');

    const [firstMonitorButton] = screen.getAllByRole('button', { name: /monitorar/i });
    await user.click(firstMonitorButton);

    expect(await screen.findByText('Erro ao adicionar produto. Tente novamente.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /monitorar/i })[0]).not.toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Fechar' }));
    expect(screen.queryByText('Erro ao adicionar produto. Tente novamente.')).not.toBeInTheDocument();
  });
});

import { useCallback, useEffect, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Table, type Column } from '@/components/Table';
import { Toast } from '@/components/Toast';
import { useAddProduct } from '@/features/products/hooks/useProducts';
import { useSearchResults, useStartSearch } from '@/features/search/hooks/useSearch';
import type { SearchResult } from '@mv/types';
import { formatCurrency, formatStore } from '@mv/utils';
import styles from './SearchByName.module.css';

const schema = z.object({ query: z.string().min(2, 'Mínimo de 2 caracteres') });
type FormValues = z.infer<typeof schema>;

// Tempo máximo aguardando o Celery processar (scrapers com Playwright podem ser lentos)
const SEARCH_TIMEOUT_MS = 60_000;

export function SearchByName() {
  const [searchId, setSearchId] = useState('');
  // isSearchActive permanece true desde o submit até resultados chegarem ou timeout
  const [isSearchActive, setIsSearchActive] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();
  // Rastrea quais product_urls já foram enviados para monitoramento nesta sessão
  const [monitoredUrls, setMonitoredUrls] = useState<Set<string>>(new Set());
  const [addingUrls, setAddingUrls] = useState<Set<string>>(new Set());
  const [errorToast, setErrorToast] = useState<string | null>(null);

  const { mutate: startSearch, isPending: isStarting } = useStartSearch();
  const { data: results, isFetching } = useSearchResults(searchId);
  const { mutate: addProduct } = useAddProduct();

  const closeErrorToast = useCallback(() => setErrorToast(null), []);

  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(schema),
  });

  // Quando resultados chegam, encerra o estado de busca ativa
  useEffect(() => {
    if (isSearchActive && (results?.total ?? 0) > 0) {
      setIsSearchActive(false);
      clearTimeout(timeoutRef.current);
    }
  }, [results?.total, isSearchActive]);

  // Cleanup do timeout ao desmontar
  useEffect(() => () => clearTimeout(timeoutRef.current), []);

  const onSubmit = ({ query }: FormValues) => {
    clearTimeout(timeoutRef.current);
    setSearchId('');
    setIsSearchActive(true);

    // Timeout de segurança: após SEARCH_TIMEOUT_MS para de mostrar "buscando"
    timeoutRef.current = setTimeout(() => setIsSearchActive(false), SEARCH_TIMEOUT_MS);

    startSearch(query, {
      onSuccess: (data) => setSearchId(data.task_id),
      onError: () => {
        setIsSearchActive(false);
        clearTimeout(timeoutRef.current);
      },
    });
  };

  const hasResults = (results?.total ?? 0) > 0;
  // "buscando" enquanto aguarda Celery (isSearchActive) ou durante refetches parciais (isFetching)
  const isWaiting = isSearchActive || (!!searchId && isFetching && !hasResults);
  // "nenhum resultado" só após busca terminar de verdade (timeout ou resultados vazios confirmados)
  const showEmpty = !isWaiting && !!searchId && results !== undefined && !hasResults;

  const columns: Column<SearchResult>[] = [
    {
      key: 'store',
      header: 'Loja',
      width: '110px',
      render: (r) => <span className={styles.badge}>{formatStore(r.store)}</span>,
    },
    {
      key: 'title',
      header: 'Produto',
      render: (r) => (
        <a href={r.product_url} target="_blank" rel="noreferrer" className={styles.title}>
          {r.title}
        </a>
      ),
    },
    {
      key: 'price',
      header: 'Preço',
      width: '120px',
      render: (r) => <strong>{r.price ? formatCurrency(r.price) : '—'}</strong>,
    },
    {
      key: 'action',
      header: '',
      width: '110px',
      render: (r) => {
        const isMonitored = monitoredUrls.has(r.product_url);
        const isCurrentlyAdding = addingUrls.has(r.product_url);
        return (
          <Button
            size="sm"
            variant={isMonitored ? 'ghost' : 'secondary'}
            disabled={isMonitored || isCurrentlyAdding}
            loading={isCurrentlyAdding}
            onClick={() => {
              setAddingUrls((prev) => new Set(prev).add(r.product_url));
              addProduct(
                {
                  url: r.product_url,
                  name: r.title,
                  image_url: r.image_url ?? undefined,
                  price: r.price ?? undefined,
                  in_stock: true,
                },
                {
                  onSuccess: () => {
                    setMonitoredUrls((prev) => new Set(prev).add(r.product_url));
                    setAddingUrls((prev) => { const s = new Set(prev); s.delete(r.product_url); return s; });
                  },
                  onError: () => {
                    setAddingUrls((prev) => { const s = new Set(prev); s.delete(r.product_url); return s; });
                    setErrorToast('Erro ao adicionar produto. Tente novamente.');
                  },
                },
              );
            }}
          >
            {isMonitored ? '✓ Adicionado' : 'Monitorar'}
          </Button>
        );
      },
    },
  ];

  return (
    <div className={styles.wrapper}>
      <form onSubmit={handleSubmit(onSubmit)} className={styles.form}>
        <Input
          placeholder="ex: iPhone 15 128GB, Samsung Galaxy S24..."
          error={errors.query?.message}
          {...register('query')}
        />
        <Button type="submit" loading={isStarting || isWaiting}>
          {isWaiting ? 'Buscando...' : 'Buscar'}
        </Button>
      </form>

      {isWaiting && (
        <div className={styles.status}>
          <span className={styles.spinner} />
          <span>Buscando em Amazon e Mercado Livre... Pode levar até 30s.</span>
        </div>
      )}

      {showEmpty && (
        <p className={styles.empty}>Nenhum resultado encontrado. Tente um termo diferente.</p>
      )}

      {hasResults && (
        <Table
          columns={columns}
          data={results!.results}
          keyExtractor={(r) => r.id}
          emptyMessage="Nenhum resultado encontrado."
        />
      )}

      {errorToast && (
        <Toast message={errorToast} type="error" onClose={closeErrorToast} />
      )}
    </div>
  );
}

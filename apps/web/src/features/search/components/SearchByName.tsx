import { useCallback, useEffect, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { Input } from '@/components/Input';
import { Toast } from '@/components/Toast';
import { useAddProduct } from '@/features/products/hooks/useProducts';
import { useSearchResults, useStartSearch } from '@/features/search/hooks/useSearch';
import { formatCurrency, formatStore } from '@mv/utils';
import styles from './SearchByName.module.css';

const BLOCK_CATEGORY_LABELS: Record<string, string> = {
  login_wall: 'temporariamente exigindo login para acessar a busca',
  captcha: 'temporariamente exigindo verificação anti-robô (captcha)',
  rate_limited: 'limitando as requisições no momento',
  challenge_js: 'com uma verificação de segurança ativa',
  access_denied: 'recusando o acesso no momento',
};

function describeStoreBlock(category: string): string {
  return BLOCK_CATEGORY_LABELS[category] ?? 'indisponível no momento';
}

const optionalPrice = z.preprocess(
  (v) => (v === '' || v === undefined ? undefined : Number(v)),
  z.number().nonnegative('Não pode ser negativo').optional(),
);

const schema = z
  .object({
    query: z.string().min(2, 'Mínimo de 2 caracteres'),
    minPrice: optionalPrice,
    maxPrice: optionalPrice,
  })
  .refine(
    (data) => data.minPrice === undefined || data.maxPrice === undefined || data.minPrice <= data.maxPrice,
    { message: 'Preço mínimo não pode ser maior que o máximo', path: ['maxPrice'] },
  );
type FormValues = z.infer<typeof schema>;

// Tempo máximo aguardando o Celery processar (scrapers com Playwright podem ser lentos)
const SEARCH_TIMEOUT_MS = 60_000;

// Quantidade de linhas-esqueleto mostradas enquanto a busca não responde
const SKELETON_ROWS = [0, 1, 2, 3, 4, 5];

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

  const onSubmit = ({ query, minPrice, maxPrice }: FormValues) => {
    clearTimeout(timeoutRef.current);
    setSearchId('');
    setIsSearchActive(true);

    // Timeout de segurança: após SEARCH_TIMEOUT_MS para de mostrar "buscando"
    timeoutRef.current = setTimeout(() => setIsSearchActive(false), SEARCH_TIMEOUT_MS);

    startSearch({ query, min_price: minPrice, max_price: maxPrice }, {
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

  // Índice do primeiro resultado com preço — recebe o selo "Menor preço"
  const firstPricedIndex = hasResults ? results!.results.findIndex((r) => r.price != null) : -1;

  return (
    <div className={styles.wrapper}>
      <form onSubmit={handleSubmit(onSubmit)} className={styles.form}>
        <Input
          placeholder="ex: iPhone 15 128GB, Samsung Galaxy S24..."
          error={errors.query?.message}
          {...register('query')}
        />
        <Input
          type="number"
          inputMode="decimal"
          step="0.01"
          min="0"
          placeholder="Preço mín."
          error={errors.minPrice?.message}
          {...register('minPrice')}
        />
        <Input
          type="number"
          inputMode="decimal"
          step="0.01"
          min="0"
          placeholder="Preço máx."
          error={errors.maxPrice?.message}
          {...register('maxPrice')}
        />
        <Button type="submit" className={styles.submitButton} loading={isStarting || isWaiting}>
          {isWaiting ? 'Buscando...' : 'Buscar'}
        </Button>
      </form>

      {isWaiting && (
        <div className={styles.status}>
          <span className={styles.spinner} />
          <span>Buscando em Amazon e Mercado Livre... Pode levar até 30s.</span>
        </div>
      )}

      {isWaiting && (
        // Esqueleto com a mesma geometria do painel real — evita salto de layout
        // quando os resultados chegam. Sem <button> (o teste exige um único botão
        // durante o loading); tudo aria-hidden.
        <div className={`${styles.panel} ${styles.skeletonPanel}`} aria-hidden="true">
          <div className={styles.panelHeader}>
            <span className={`${styles.skeletonBar} ${styles.skeletonHeaderBar}`} />
          </div>
          {SKELETON_ROWS.map((i) => (
            <div key={i} className={styles.row}>
              <span className={styles.skeletonPill} />
              <div className={styles.thumbPlaceholder} />
              <div className={styles.skeletonLines}>
                <span className={`${styles.skeletonBar} ${styles.skeletonLineWide}`} />
                <span className={`${styles.skeletonBar} ${styles.skeletonLineShort}`} />
              </div>
              <div className={styles.meta}>
                <span className={styles.skeletonPrice} />
              </div>
              <span className={styles.skeletonButton} />
            </div>
          ))}
        </div>
      )}

      {results?.store_warnings && Object.entries(results.store_warnings).map(([store, category]) => (
        <div key={store} className={styles.warning}>
          <Icon name="alert" size={16} className={styles.warningIcon} />
          <span>
            {formatStore(store)} está {describeStoreBlock(category)} — mostrando resultados de outras lojas.
          </span>
        </div>
      ))}

      {showEmpty && (
        <p className={styles.empty}>Nenhum resultado encontrado. Tente um termo diferente.</p>
      )}

      {hasResults && (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span className={styles.panelTitle}>
              {results!.total} resultado{results!.total === 1 ? '' : 's'}
            </span>
          </div>
          {results!.results.map((r, index) => {
            const isMonitored = monitoredUrls.has(r.product_url);
            const isCurrentlyAdding = addingUrls.has(r.product_url);
            return (
              <div key={r.id} className={styles.row}>
                <span className={styles.badge}>{formatStore(r.store)}</span>
                {r.image_url ? (
                  <img
                    src={r.image_url}
                    alt=""
                    className={styles.thumb}
                    width={44}
                    height={56}
                    loading="lazy"
                    decoding="async"
                  />
                ) : (
                  <div className={styles.thumbPlaceholder} aria-hidden="true" />
                )}
                <a href={r.product_url} target="_blank" rel="noreferrer" className={styles.title}>
                  {r.title}
                </a>
                <div className={styles.meta}>
                  <span className={`${r.price ? styles.price : styles.noPrice} tabular`}>
                    {r.price ? formatCurrency(r.price) : 'Sem preço'}
                  </span>
                  {index === firstPricedIndex && (
                    <span className={styles.bestBadge}>Menor preço</span>
                  )}
                </div>
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
              </div>
            );
          })}
        </div>
      )}

      {errorToast && (
        <Toast message={errorToast} type="error" onClose={closeErrorToast} />
      )}
    </div>
  );
}

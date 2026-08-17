import { useState } from 'react';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { Tooltip } from '@/components/Tooltip';
import {
  useGroupHistorySummary,
  useProductHistorySummary,
  useProductHistoryTable,
} from '@/features/products/hooks/useProducts';
import { PriceHistoryChart } from './PriceHistoryChart';
import { StockWarningBanner } from './StockWarningBanner';
import type { HistoryRange, Product, ProductGroup } from '@mv/types';
import { formatCurrency, formatDate, formatStore } from '@mv/utils';
import styles from './ProductDetailModal.module.css';

function fmtPrice(value: number | null | undefined, loading?: boolean): string {
  if (loading) return '…';
  return value != null ? formatCurrency(value) : '—';
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

// ─── Stat cards row (shared) ───────────────────────────────────────────────────

interface StatCardItem {
  label: string;
  value: string;
  highlight?: boolean;
  sub?: string;
}

function StatCardsRow({ items }: { items: StatCardItem[] }) {
  return (
    <div className={styles.statsRow}>
      {items.map((item) => (
        <div
          key={item.label}
          className={[styles.statCard, item.highlight ? styles.highlight : ''].join(' ')}
        >
          <span className={styles.statLabel}>{item.label}</span>
          <span className={styles.statValue}>{item.value}</span>
          {item.sub && <span className={styles.statSub}>{item.sub}</span>}
        </div>
      ))}
    </div>
  );
}

// ─── History table (shared, paginated) ─────────────────────────────────────────

function HistoryTable({ productId }: { productId: string }) {
  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useProductHistoryTable(productId);
  const entries = data?.pages.flatMap((page) => page.entries) ?? [];

  if (isLoading) return <p className={styles.loading}>Carregando histórico...</p>;
  if (entries.length === 0)
    return <p className={styles.empty}>Nenhum histórico registrado.</p>;

  return (
    <>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Data da verificação</th>
            <th>Preço</th>
            <th>Em estoque</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td className={styles.date}>{formatDate(entry.scrapedAt)}</td>
              <td className={styles.price}>
                {entry.price != null ? formatCurrency(entry.price) : '—'}
              </td>
              <td>
                <span className={entry.inStock ? styles.inStock : styles.outOfStock}>
                  {entry.inStock ? 'Sim' : 'Não'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasNextPage && (
        <div className={styles.loadMoreRow}>
          <Button
            variant="ghost"
            size="sm"
            loading={isFetchingNextPage}
            onClick={() => fetchNextPage()}
          >
            Carregar mais
          </Button>
        </div>
      )}
    </>
  );
}

// ─── Single product modal content ─────────────────────────────────────────────

function SingleProductContent({ product }: { product: Product }) {
  const [range, setRange] = useState<HistoryRange>('30d');
  const { data, isLoading } = useProductHistorySummary(product.id, range);

  return (
    <div className={styles.body}>
      <StockWarningBanner product={product} />
      <div className={styles.accordionMeta}>
        <span className={styles.storeBadge}>{formatStore(product.store)}</span>
        {product.last_checked && (
          <span className={styles.date}>Verificado em {formatDate(product.last_checked)}</span>
        )}
        <a href={product.url} target="_blank" rel="noreferrer" className={styles.productLink}>
          Ver anúncio →
        </a>
      </div>
      <StatCardsRow
        items={[
          { label: 'Preço atual', value: fmtPrice(data?.stats.current_price, isLoading) },
          {
            label: 'Menor preço histórico',
            value: fmtPrice(data?.stats.lowest_price, isLoading),
            highlight: true,
          },
          { label: 'Preço médio', value: fmtPrice(data?.stats.average_price, isLoading) },
          { label: 'Mediana', value: fmtPrice(data?.stats.median_price, isLoading) },
        ]}
      />

      <div className={styles.section}>
        <span className={styles.sectionTitle}>Tendência de preço</span>
        <PriceHistoryChart
          points={data?.chart.points ?? []}
          range={range}
          onRangeChange={setRange}
          loading={isLoading}
        />
      </div>

      <div className={styles.section}>
        <span className={styles.sectionTitle}>Registros</span>
        <HistoryTable productId={product.id} />
      </div>
    </div>
  );
}

// ─── Per-listing accordion item (each has its own hook call) ──────────────────

function ListingAccordion({
  product,
  isCheapest,
  onUngroup,
}: {
  product: Product;
  isCheapest: boolean;
  onUngroup: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [range, setRange] = useState<HistoryRange>('30d');
  const { data: histData } = useProductHistorySummary(product.id, range);

  return (
    <div className={styles.accordionItem}>
      <div className={styles.accordionHeader} onClick={() => setOpen((v) => !v)}>
        <span className={styles.storeBadge}>{formatStore(product.store)}</span>
        <span className={styles.accordionName}>{product.name ?? product.url}</span>
        {(product.in_stock === false || product.status === 'paused') && (
          <Tooltip
            content={
              product.status === 'paused'
                ? 'Monitoramento pausado pelo usuário. O histórico continua disponível.'
                : 'Este anúncio pode estar fora de estoque ou ter sido removido.'
            }
          >
            <span className={styles.warningIcon} onClick={(e) => e.stopPropagation()}>
              {product.status === 'paused' ? '⏸' : '⚠'}
            </span>
          </Tooltip>
        )}
        {product.in_stock === false && (
          <span className={styles.unavailableBadge}>Indisponível</span>
        )}
        <span
          className={[
            styles.price,
            isCheapest ? styles.priceLowest : '',
            product.in_stock === false ? styles.priceUnavailable : '',
          ].join(' ')}
        >
          {product.current_price != null ? formatCurrency(product.current_price) : '—'}
        </span>
        {histData?.stats.lowest_price != null && (
          <span className={styles.accordionLowest}>
            mín: {formatCurrency(histData.stats.lowest_price)}
          </span>
        )}
        <span
          className={[
            styles.accordionChevron,
            open ? styles.accordionChevronOpen : '',
          ].join(' ')}
        >
          ▾
        </span>
      </div>
      {open && (
        <div className={styles.accordionBody}>
          <StockWarningBanner product={product} />
          <div className={styles.accordionMeta}>
            {product.last_checked && (
              <span className={styles.date}>
                Verificado em {formatDate(product.last_checked)}
              </span>
            )}
            <a href={product.url} target="_blank" rel="noreferrer" className={styles.productLink}>
              Ver anúncio →
            </a>
          </div>
          <PriceHistoryChart
            points={histData?.chart.points ?? []}
            range={range}
            onRangeChange={setRange}
          />
          <HistoryTable productId={product.id} />
          <div className={styles.ungroupBtn}>
            <Button variant="ghost" size="sm" onClick={onUngroup}>
              Remover do grupo
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Group modal content ──────────────────────────────────────────────────────

function GroupContent({
  group,
  products,
  onDeleteGroup,
  onUngroupProduct,
}: {
  group: ProductGroup;
  products: Product[];
  onDeleteGroup: () => void;
  onUngroupProduct: (productId: string) => void;
}) {
  const groupProducts = group.productIds
    .map((id) => products.find((p) => p.id === id))
    .filter(Boolean) as Product[];

  // Sort by current price ASC (null prices last)
  const sorted = [...groupProducts].sort((a, b) => {
    if (a.current_price == null) return 1;
    if (b.current_price == null) return -1;
    return a.current_price - b.current_price;
  });

  const cheapest = sorted.find((p) => p.current_price != null);

  const historyQueries = useGroupHistorySummary(groupProducts.map((p) => p.id));

  const historyLoading = historyQueries.some((q) => q.isLoading);
  const perListingLowest = historyQueries
    .map((q) => q.data?.stats.lowest_price)
    .filter((p): p is number => p != null);
  const perListingMedian = historyQueries
    .map((q) => q.data?.stats.median_price)
    .filter((p): p is number => p != null);

  const lowestHistorical = perListingLowest.length > 0 ? Math.min(...perListingLowest) : null;
  const medianPrice = median(perListingMedian);

  return (
    <div className={styles.body}>
      {/* Stat cards */}
      <StatCardsRow
        items={[
          {
            label: 'Menor preço hoje',
            value: cheapest?.current_price != null ? formatCurrency(cheapest.current_price) : '—',
            highlight: true,
            sub: cheapest ? formatStore(cheapest.store) : undefined,
          },
          { label: 'Menor preço histórico', value: fmtPrice(lowestHistorical, historyLoading) },
          { label: 'Mediana de preços', value: fmtPrice(medianPrice, historyLoading) },
        ]}
      />

      {/* Per-listing accordion — each ListingAccordion calls useProductHistorySummary internally */}
      <div className={styles.section}>
        <span className={styles.sectionTitle}>Anúncios e histórico</span>
        <div className={styles.accordion}>
          {sorted.map((p) => (
            <ListingAccordion
              key={p.id}
              product={p}
              isCheapest={p.id === cheapest?.id}
              onUngroup={() => onUngroupProduct(p.id)}
            />
          ))}
        </div>
      </div>

      {/* Delete group */}
      <div className={styles.groupActions}>
        <Button variant="ghost" size="sm" onClick={onDeleteGroup}>
          Desfazer grupo
        </Button>
      </div>
    </div>
  );
}

// ─── Public component ─────────────────────────────────────────────────────────

interface Props {
  isOpen: boolean;
  onClose: () => void;
  product?: Product;
  group?: ProductGroup;
  allProducts: Product[];
  onDeleteGroup?: (groupId: string) => void;
  onUngroupProduct?: (groupId: string, productId: string) => void;
}

export function ProductDetailModal({
  isOpen,
  onClose,
  product,
  group,
  allProducts,
  onDeleteGroup,
  onUngroupProduct,
}: Props) {
  const title = group
    ? group.name
    : (product?.name ?? product?.url ?? 'Produto');

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="lg">
      {group ? (
        <GroupContent
          group={group}
          products={allProducts}
          onDeleteGroup={() => { onDeleteGroup?.(group.id); onClose(); }}
          onUngroupProduct={(productId) => onUngroupProduct?.(group.id, productId)}
        />
      ) : product ? (
        <SingleProductContent product={product} />
      ) : null}
    </Modal>
  );
}

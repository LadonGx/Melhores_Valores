import { useState } from 'react';
import { Button } from '@/components/Button';
import { Modal } from '@/components/Modal';
import { useProductHistory } from '@/features/products/hooks/useProducts';
import type { PriceHistoryEntry, Product, ProductGroup } from '@mv/types';
import { formatCurrency, formatDate, formatStore } from '@mv/utils';
import styles from './ProductDetailModal.module.css';

// ─── History table (shared) ───────────────────────────────────────────────────

function HistoryContent({ productId }: { productId: string }) {
  const { data, isLoading } = useProductHistory(productId);

  if (isLoading) return <p className={styles.loading}>Carregando histórico...</p>;
  if (!data || data.history.length === 0)
    return <p className={styles.empty}>Nenhum histórico registrado.</p>;

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Data da verificação</th>
          <th>Preço</th>
          <th>Em estoque</th>
        </tr>
      </thead>
      <tbody>
        {(data.history as PriceHistoryEntry[]).map((entry) => (
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
  );
}

// ─── Single product modal content ─────────────────────────────────────────────

function SingleProductContent({ product }: { product: Product }) {
  const { data, isLoading } = useProductHistory(product.id);

  return (
    <div className={styles.body}>
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Preço atual</span>
          <span className={styles.statValue}>
            {isLoading ? '…' : data?.current_price != null ? formatCurrency(data.current_price) : '—'}
          </span>
        </div>
        <div className={`${styles.statCard} ${styles.highlight}`}>
          <span className={styles.statLabel}>Menor preço histórico</span>
          <span className={styles.statValue}>
            {isLoading ? '…' : data?.lowest_price != null ? formatCurrency(data.lowest_price) : '—'}
          </span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Preço médio</span>
          <span className={styles.statValue}>
            {isLoading ? '…' : data?.average_price != null ? formatCurrency(data.average_price) : '—'}
          </span>
        </div>
      </div>

      <div className={styles.section}>
        <span className={styles.sectionTitle}>Histórico de preços</span>
        <HistoryContent productId={product.id} />
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
  const { data: histData } = useProductHistory(product.id);

  return (
    <div className={styles.accordionItem}>
      <div className={styles.accordionHeader} onClick={() => setOpen((v) => !v)}>
        <span className={styles.storeBadge}>{formatStore(product.store)}</span>
        <span className={styles.accordionName}>{product.name ?? product.url}</span>
        <span className={[styles.price, isCheapest ? styles.priceLowest : ''].join(' ')}>
          {product.current_price != null ? formatCurrency(product.current_price) : '—'}
        </span>
        {histData?.lowest_price != null && (
          <span className={styles.accordionLowest}>
            mín: {formatCurrency(histData.lowest_price)}
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
          <div className={styles.accordionMeta}>
            <span>
              <strong>Em estoque:</strong>{' '}
              {product.in_stock === false
                ? <span className={styles.outOfStock}>Não</span>
                : <span className={styles.inStock}>Sim</span>}
            </span>
            {product.last_checked && (
              <span className={styles.date}>
                Verificado em {formatDate(product.last_checked)}
              </span>
            )}
            <a href={product.url} target="_blank" rel="noreferrer" className={styles.productLink}>
              Ver anúncio →
            </a>
          </div>
          <HistoryContent productId={product.id} />
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

  return (
    <div className={styles.body}>
      {/* Stat cards */}
      <div className={styles.statsRow}>
        <div className={`${styles.statCard} ${styles.highlight}`}>
          <span className={styles.statLabel}>Menor preço hoje</span>
          <span className={styles.statValue}>
            {cheapest?.current_price != null ? formatCurrency(cheapest.current_price) : '—'}
          </span>
          {cheapest && (
            <span className={styles.statSub}>{formatStore(cheapest.store)}</span>
          )}
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>Anúncios no grupo</span>
          <span className={styles.statValue}>{groupProducts.length}</span>
        </div>
      </div>

      {/* Per-listing accordion — each ListingAccordion calls useProductHistory internally */}
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

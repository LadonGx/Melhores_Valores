import { useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Tooltip } from '@/components/Tooltip';
import { ProductDetailModal } from '@/features/products/components/ProductDetailModal';
import { useProductGroups } from '@/features/products/hooks/useProductGroups';
import { useProducts } from '@/features/products/hooks/useProducts';
import type { Product, ProductGroup } from '@mv/types';
import { formatCurrency, formatDate, formatStore } from '@mv/utils';
import styles from './Dashboard.module.css';

// ─── Group row ────────────────────────────────────────────────────────────────

function GroupRow({
  group,
  products,
  onOpen,
  groupingMode,
}: {
  group: ProductGroup;
  products: Product[];
  onOpen: () => void;
  groupingMode: boolean;
}) {
  const groupProducts = group.productIds
    .map((id) => products.find((p) => p.id === id))
    .filter(Boolean) as Product[];

  const sorted = [...groupProducts].sort((a, b) => {
    if (a.current_price == null) return 1;
    if (b.current_price == null) return -1;
    return a.current_price - b.current_price;
  });
  const cheapest = sorted.find((p) => p.current_price != null);
  const thumb = groupProducts.find((p) => p.image_url)?.image_url;
  const affected = groupProducts.filter((p) => p.in_stock === false);

  return (
    <div
      className={[styles.productRow, groupingMode ? styles.rowDisabled : ''].join(' ')}
      onClick={groupingMode ? undefined : onOpen}
      style={groupingMode ? undefined : { cursor: 'pointer' }}
    >
      <div className={styles.productRowMain}>
        {thumb ? (
          <img src={thumb} alt="" className={styles.productThumb} loading="lazy" />
        ) : (
          <div className={styles.productThumbPlaceholder} />
        )}

        <div className={styles.productInfo}>
          <div className={styles.productNameRow}>
            <span className={styles.productName}>{group.name}</span>
            {affected.length > 0 && (
              <Tooltip
                content={`${affected.length} anúncio${affected.length > 1 ? 's' : ''} deste grupo (${affected
                  .map((p) => formatStore(p.store))
                  .join(', ')}) pode${affected.length > 1 ? 'm' : ''} estar fora de estoque ou ter sido removido${affected.length > 1 ? 's' : ''}.`}
              >
                <span className={styles.warningIcon} onClick={(e) => e.stopPropagation()}>
                  ⚠
                </span>
              </Tooltip>
            )}
          </div>
          <div className={styles.storeBadges}>
            {groupProducts.map((p) => (
              <span key={p.id} className={styles.storeBadge}>
                {formatStore(p.store)}
              </span>
            ))}
            <span className={styles.listingCount}>{groupProducts.length} anúncios</span>
          </div>
        </div>

        <div className={styles.productMeta}>
          {cheapest?.current_price != null && (
            <span className={styles.lowestBadge}>
              {formatCurrency(cheapest.current_price)} · {formatStore(cheapest.store)}
            </span>
          )}
          <span className={styles.detailHint}>Ver detalhes →</span>
        </div>
      </div>
    </div>
  );
}

// ─── Individual product row ───────────────────────────────────────────────────

function ProductRow({
  product,
  onOpen,
  groupingMode,
  selected,
  onToggleSelect,
}: {
  product: Product;
  onOpen: () => void;
  groupingMode: boolean;
  selected: boolean;
  onToggleSelect: () => void;
}) {
  const handleClick = () => {
    if (groupingMode) {
      onToggleSelect();
    } else {
      onOpen();
    }
  };

  const isPaused = product.status === 'paused';

  return (
    <div
      className={[
        styles.productRow,
        groupingMode ? styles.rowSelectable : '',
        selected ? styles.rowSelected : '',
        isPaused ? styles.rowPaused : '',
      ].join(' ')}
      onClick={handleClick}
      style={{ cursor: 'pointer' }}
    >
      <div className={styles.productRowMain}>
        {groupingMode && (
          <input
            type="checkbox"
            className={styles.checkbox}
            checked={selected}
            onChange={onToggleSelect}
            onClick={(e) => e.stopPropagation()}
          />
        )}
        {product.image_url && (
          <img src={product.image_url} alt="" className={styles.productThumb} loading="lazy" />
        )}
        <span className={styles.storeBadge}>{formatStore(product.store)}</span>
        <div className={styles.productInfo}>
          <div className={styles.productNameRow}>
            <span className={styles.productName}>{product.name ?? product.url}</span>
            {(product.in_stock === false || isPaused) && (
              <Tooltip
                content={
                  isPaused
                    ? 'Monitoramento pausado pelo usuário. O histórico continua disponível.'
                    : 'Este anúncio pode estar fora de estoque ou ter sido removido.'
                }
              >
                <span className={styles.warningIcon} onClick={(e) => e.stopPropagation()}>
                  {isPaused ? '⏸' : '⚠'}
                </span>
              </Tooltip>
            )}
          </div>
          {product.last_checked && (
            <span className={styles.lastChecked}>
              Verificado em {formatDate(product.last_checked)}
              {isPaused ? ' · Pausado' : ''}
            </span>
          )}
        </div>

        <div className={styles.productMeta}>
          {product.in_stock === false && (
            <span className={styles.unavailableBadge}>Indisponível</span>
          )}
          <span
            className={[
              styles.currentPrice,
              product.in_stock === false ? styles.currentPriceUnavailable : '',
            ].join(' ')}
          >
            {product.current_price != null ? formatCurrency(product.current_price) : '—'}
          </span>
          {!groupingMode && <span className={styles.detailHint}>Ver →</span>}
        </div>
      </div>
    </div>
  );
}

// ─── Dashboard page ───────────────────────────────────────────────────────────

type ModalTarget =
  | { type: 'product'; id: string }
  | { type: 'group'; id: string }
  | null;

export function Dashboard() {
  const { data, isLoading } = useProducts();
  const products = data?.products ?? [];
  const { groups, createGroup, deleteGroup, ungroupProduct } = useProductGroups();

  const [groupingMode, setGroupingMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [pendingGroupName, setPendingGroupName] = useState('');
  const [showNameInput, setShowNameInput] = useState(false);
  const [modalTarget, setModalTarget] = useState<ModalTarget>(null);

  // Products that don't belong to any group
  const groupedProductIds = new Set(groups.flatMap((g) => g.productIds));
  const ungroupedProducts = products.filter((p) => !groupedProductIds.has(p.id));

  // Stats
  const stores = new Set(products.map((p) => p.store)).size;
  const pricesWithValue = products.filter((p) => p.current_price != null);
  const lowestToday =
    pricesWithValue.length > 0
      ? Math.min(...pricesWithValue.map((p) => p.current_price!))
      : null;

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const exitGroupingMode = () => {
    setGroupingMode(false);
    setSelectedIds(new Set());
    setShowNameInput(false);
    setPendingGroupName('');
  };

  const handleCreateGroup = () => {
    if (pendingGroupName.trim() && selectedIds.size >= 2) {
      createGroup(pendingGroupName.trim(), [...selectedIds]);
      exitGroupingMode();
    }
  };

  // Modal targets
  const modalGroup =
    modalTarget?.type === 'group' ? groups.find((g) => g.id === modalTarget.id) : undefined;
  const modalProduct =
    modalTarget?.type === 'product' ? products.find((p) => p.id === modalTarget.id) : undefined;

  return (
    <div className={styles.page}>
      {/* ── Stats ── */}
      <div className={styles.stats}>
        <Card>
          <div className={styles.stat}>
            <span className={styles.statValue}>{isLoading ? '—' : (data?.total ?? 0)}</span>
            <span className={styles.statLabel}>Anúncios monitorados</span>
          </div>
        </Card>
        {groups.length > 0 && (
          <Card>
            <div className={styles.stat}>
              <span className={styles.statValue}>{groups.length}</span>
              <span className={styles.statLabel}>Grupos criados</span>
            </div>
          </Card>
        )}
        <Card>
          <div className={styles.stat}>
            <span className={styles.statValue}>{isLoading ? '—' : stores}</span>
            <span className={styles.statLabel}>Lojas ativas</span>
          </div>
        </Card>
        <Card>
          <div className={styles.stat}>
            <span className={styles.statValue}>
              {isLoading ? '—' : lowestToday != null ? formatCurrency(lowestToday) : '—'}
            </span>
            <span className={styles.statLabel}>Menor preço hoje</span>
          </div>
        </Card>
      </div>

      {/* ── Product list ── */}
      <Card
        title="Produtos monitorados"
        action={
          !isLoading && products.length > 1 && (
            groupingMode ? null : (
              <Button variant="secondary" size="sm" onClick={() => setGroupingMode(true)}>
                Agrupar anúncios
              </Button>
            )
          )
        }
      >
        {/* Grouping toolbar */}
        {groupingMode && (
          <div className={styles.toolbar}>
            <span className={styles.toolbarInfo}>
              {selectedIds.size} selecionado{selectedIds.size !== 1 ? 's' : ''}
            </span>

            {showNameInput ? (
              <div className={styles.nameInputRow}>
                <input
                  className={styles.nameInput}
                  placeholder="Nome do grupo..."
                  value={pendingGroupName}
                  onChange={(e) => setPendingGroupName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreateGroup(); }}
                  autoFocus
                />
                <Button
                  size="sm"
                  disabled={pendingGroupName.trim().length === 0}
                  onClick={handleCreateGroup}
                >
                  Confirmar
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setShowNameInput(false)}>
                  Voltar
                </Button>
              </div>
            ) : (
              <div className={styles.toolbarActions}>
                <Button
                  size="sm"
                  disabled={selectedIds.size < 2}
                  onClick={() => setShowNameInput(true)}
                >
                  Criar grupo
                </Button>
                <Button size="sm" variant="ghost" onClick={exitGroupingMode}>
                  Cancelar
                </Button>
              </div>
            )}
          </div>
        )}

        {isLoading ? (
          <p className={styles.empty}>Carregando...</p>
        ) : products.length === 0 ? (
          <p className={styles.empty}>
            Nenhum produto monitorado.{' '}
            <a href="/products">Adicione seu primeiro produto.</a>
          </p>
        ) : (
          <div className={styles.productList}>
            {groups.map((g) => (
              <GroupRow
                key={g.id}
                group={g}
                products={products}
                groupingMode={groupingMode}
                onOpen={() => setModalTarget({ type: 'group', id: g.id })}
              />
            ))}
            {ungroupedProducts.map((p) => (
              <ProductRow
                key={p.id}
                product={p}
                groupingMode={groupingMode}
                selected={selectedIds.has(p.id)}
                onToggleSelect={() => toggleSelect(p.id)}
                onOpen={() => setModalTarget({ type: 'product', id: p.id })}
              />
            ))}
          </div>
        )}
      </Card>

      {/* ── Detail modal ── */}
      <ProductDetailModal
        isOpen={modalTarget !== null}
        onClose={() => setModalTarget(null)}
        product={modalProduct}
        group={modalGroup}
        allProducts={products}
        onDeleteGroup={deleteGroup}
        onUngroupProduct={ungroupProduct}
      />
    </div>
  );
}

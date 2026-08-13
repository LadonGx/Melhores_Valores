import { useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { ConfirmModal } from '@/components/ConfirmModal';
import { Toast } from '@/components/Toast';
import { Tooltip } from '@/components/Tooltip';
import { ProductDetailModal } from '@/features/products/components/ProductDetailModal';
import { PromotionsModal } from '@/features/products/components/PromotionsModal';
import { useProductGroups } from '@/features/products/hooks/useProductGroups';
import { usePromotions, useProducts, useRemoveProduct } from '@/features/products/hooks/useProducts';
import type { Product, ProductGroup } from '@mv/types';
import { formatCurrency, formatDate, formatStore } from '@mv/utils';
import { FilterMenu } from './FilterMenu';
import { sortRows, type DashboardRow } from './sortRows';
import { useDashboardFilter } from './useDashboardFilter';
import styles from './Dashboard.module.css';

// ─── Group row ────────────────────────────────────────────────────────────────

function GroupRow({
  group,
  products,
  onOpen,
  selected,
  onToggleSelect,
}: {
  group: ProductGroup;
  products: Product[];
  onOpen: () => void;
  selected: boolean;
  onToggleSelect: () => void;
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
      className={[styles.productRow, selected ? styles.rowSelected : ''].join(' ')}
      onClick={onOpen}
      style={{ cursor: 'pointer' }}
    >
      <div className={styles.productRowMain}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
        />
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
  selected,
  onToggleSelect,
}: {
  product: Product;
  onOpen: () => void;
  selected: boolean;
  onToggleSelect: () => void;
}) {
  const isPaused = product.status === 'paused';

  return (
    <div
      className={[
        styles.productRow,
        selected ? styles.rowSelected : '',
        isPaused ? styles.rowPaused : '',
      ].join(' ')}
      onClick={onOpen}
      style={{ cursor: 'pointer' }}
    >
      <div className={styles.productRowMain}>
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
        />
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
          <span className={styles.detailHint}>Ver →</span>
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

function getGroupCheapestPrice(group: ProductGroup, products: Product[]): number | null {
  const prices = group.productIds
    .map((id) => products.find((p) => p.id === id)?.current_price)
    .filter((price): price is number => price != null);
  return prices.length > 0 ? Math.min(...prices) : null;
}

export function Dashboard() {
  const { data, isLoading } = useProducts();
  const products = data?.products ?? [];
  const { groups, createGroup, deleteGroup, ungroupProduct } = useProductGroups();
  const { mutateAsync: removeProduct, isPending: isDeleting } = useRemoveProduct();
  const { sortOption, hiddenIds, setSortOption, toggleHidden, showAll, reset: resetFilter } =
    useDashboardFilter();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [pendingGroupName, setPendingGroupName] = useState('');
  const [showNameInput, setShowNameInput] = useState(false);
  const [modalTarget, setModalTarget] = useState<ModalTarget>(null);
  const [promotionsOpen, setPromotionsOpen] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);

  const { data: promotionsData, isLoading: promotionsLoading } = usePromotions();
  const promotions = promotionsData?.promotions ?? [];

  // Products that don't belong to any group
  const groupedProductIds = new Set(groups.flatMap((g) => g.productIds));
  const ungroupedProducts = products.filter((p) => !groupedProductIds.has(p.id));

  const selectedGroups = groups.filter((g) => selectedIds.has(g.id));
  const selectedProducts = ungroupedProducts.filter((p) => selectedIds.has(p.id));
  const totalProductsToDelete =
    selectedProducts.length + selectedGroups.reduce((sum, g) => sum + g.productIds.length, 0);

  // Lista unificada de grupos + avulsos, para ordenação e filtro de visibilidade em conjunto
  const allRows: DashboardRow[] = [
    ...groups.map((g) => ({
      id: g.id,
      type: 'group' as const,
      name: g.name,
      price: getGroupCheapestPrice(g, products),
    })),
    ...ungroupedProducts.map((p) => ({
      id: p.id,
      type: 'product' as const,
      name: p.name ?? p.url,
      price: p.current_price ?? null,
    })),
  ];
  const visibleRows = sortRows(
    allRows.filter((row) => !hiddenIds.includes(row.id)),
    sortOption,
  );

  const allRowIds = visibleRows.map((row) => row.id);
  const allSelected = allRowIds.length > 0 && selectedIds.size === allRowIds.length;

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds(allSelected ? new Set() : new Set(allRowIds));
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
    setShowNameInput(false);
    setPendingGroupName('');
  };

  const handleCreateGroup = () => {
    if (pendingGroupName.trim() && selectedProducts.length >= 2) {
      createGroup(pendingGroupName.trim(), selectedProducts.map((p) => p.id));
      clearSelection();
    }
  };

  const handleConfirmDelete = async () => {
    try {
      const productIdsToDelete = [
        ...selectedProducts.map((p) => p.id),
        ...selectedGroups.flatMap((g) => g.productIds),
      ];
      await Promise.all(productIdsToDelete.map((id) => removeProduct(id)));
      selectedGroups.forEach((g) => deleteGroup(g.id));
      setToast({ message: 'Excluído com sucesso.', type: 'success' });
      clearSelection();
    } catch {
      setToast({ message: 'Erro ao excluir. Tente novamente.', type: 'error' });
    } finally {
      setConfirmDeleteOpen(false);
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
        <Card
          className={promotions.length > 1 ? styles.statClickable : undefined}
          onClick={promotions.length > 1 ? () => setPromotionsOpen(true) : undefined}
        >
          <div className={styles.stat}>
            {promotionsLoading ? (
              <>
                <span className={styles.statValue}>—</span>
                <span className={styles.statLabel}>Promoção hoje</span>
              </>
            ) : promotions.length === 0 ? (
              <>
                <span className={styles.statValue}>—</span>
                <span className={styles.statLabel}>Nenhuma promoção hoje</span>
              </>
            ) : promotions.length === 1 ? (
              <>
                <span className={styles.statValue}>
                  {formatCurrency(promotions[0].current_price)}
                </span>
                <span className={styles.statLabel}>
                  {promotions[0].name ?? promotions[0].url}
                </span>
              </>
            ) : (
              <>
                <span className={styles.statValue}>{promotions.length}</span>
                <span className={styles.statLabel}>produtos em promoção</span>
              </>
            )}
          </div>
        </Card>
      </div>

      {/* ── Product list ── */}
      <Card
        title="Produtos monitorados"
        action={
          <FilterMenu
            rows={allRows}
            sortOption={sortOption}
            hiddenIds={hiddenIds}
            onSortChange={setSortOption}
            onToggleHidden={toggleHidden}
            onShowAll={showAll}
            onReset={resetFilter}
          />
        }
      >
        {/* Selection toolbar */}
        {selectedIds.size > 0 && (
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
                <Button size="sm" variant="ghost" onClick={toggleSelectAll}>
                  {allSelected ? 'Desmarcar todos' : 'Selecionar todos'}
                </Button>
                <Button
                  size="sm"
                  disabled={selectedGroups.length > 0 || selectedProducts.length < 2}
                  title={selectedGroups.length > 0 ? 'Desmarque os grupos para criar um novo grupo' : undefined}
                  onClick={() => setShowNameInput(true)}
                >
                  Agrupar anúncios
                </Button>
                <Button size="sm" variant="danger" onClick={() => setConfirmDeleteOpen(true)}>
                  Excluir
                </Button>
                <Button size="sm" variant="ghost" onClick={clearSelection}>
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
        ) : visibleRows.length === 0 ? (
          <p className={styles.empty}>Nenhum produto corresponde ao filtro atual.</p>
        ) : (
          <div className={styles.productList}>
            {visibleRows.map((row) => {
              if (row.type === 'group') {
                const g = groups.find((group) => group.id === row.id);
                if (!g) return null;
                return (
                  <GroupRow
                    key={g.id}
                    group={g}
                    products={products}
                    selected={selectedIds.has(g.id)}
                    onToggleSelect={() => toggleSelect(g.id)}
                    onOpen={() => setModalTarget({ type: 'group', id: g.id })}
                  />
                );
              }
              const p = ungroupedProducts.find((product) => product.id === row.id);
              if (!p) return null;
              return (
                <ProductRow
                  key={p.id}
                  product={p}
                  selected={selectedIds.has(p.id)}
                  onToggleSelect={() => toggleSelect(p.id)}
                  onOpen={() => setModalTarget({ type: 'product', id: p.id })}
                />
              );
            })}
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

      {/* ── Promotions modal ── */}
      <PromotionsModal
        isOpen={promotionsOpen}
        onClose={() => setPromotionsOpen(false)}
        promotions={promotions}
      />

      {/* ── Delete confirmation modal ── */}
      <ConfirmModal
        isOpen={confirmDeleteOpen}
        onClose={() => setConfirmDeleteOpen(false)}
        onConfirm={handleConfirmDelete}
        isLoading={isDeleting}
        title="Excluir selecionados"
        message={
          selectedGroups.length > 0
            ? `Tem certeza que deseja excluir ${totalProductsToDelete} produto(s), incluindo ${selectedGroups.length} grupo(s)? Essa ação não pode ser desfeita.`
            : `Tem certeza que deseja excluir ${totalProductsToDelete} produto(s) selecionado(s)? Essa ação não pode ser desfeita.`
        }
      />

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
}

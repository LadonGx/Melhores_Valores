import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { ConfirmModal } from '@/components/ConfirmModal';
import { EmptyState } from '@/components/EmptyState';
import { Icon } from '@/components/Icon';
import { Modal } from '@/components/Modal';
import { PageHeader } from '@/components/PageHeader';
import { SelectionBar } from '@/components/SelectionBar';
import { Table, type Column } from '@/components/Table';
import { Toast } from '@/components/Toast';
import { AddProductForm } from '@/features/products/components/AddProductForm';
import { describeLastCheck } from '@/features/products/formatLastChecked';
import {
  useProducts,
  useRefreshPrice,
  useRemoveProduct,
  useUpdateProductName,
} from '@/features/products/hooks/useProducts';
import { SearchByName } from '@/features/search/components/SearchByName';
import type { Product } from '@mv/types';
import { formatCurrency, formatDate, formatStore } from '@mv/utils';
import styles from './Products.module.css';

type ModalType = 'url' | 'search' | null;

/** Domínio + caminho da URL, para a linha secundária (muted) sob o nome do produto. */
function formatUrlPath(url: string): string {
  try {
    const u = new URL(url);
    return `${u.hostname}${u.pathname}`.replace(/\/$/, '');
  } catch {
    return url;
  }
}

// ─── Inline name editor ───────────────────────────────────────────────────────

function NameCell({ product }: { product: Product }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(product.name ?? '');
  const inputRef = useRef<HTMLInputElement>(null);
  const { mutate: updateName, isPending } = useUpdateProductName();

  const hasGarbageName = !product.name || product.name.trim().length < 3;

  const startEdit = () => {
    setValue(product.name ?? '');
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const confirm = () => {
    const trimmed = value.trim();
    if (trimmed.length >= 3 && trimmed !== product.name) {
      updateName({ productId: product.id, name: trimmed });
    }
    setEditing(false);
  };

  const cancel = () => {
    setValue(product.name ?? '');
    setEditing(false);
  };

  if (editing) {
    return (
      <div className={[styles.nameCol, styles.nameEditRow].join(' ')}>
        <input
          ref={inputRef}
          className={styles.nameInput}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') confirm();
            if (e.key === 'Escape') cancel();
          }}
          disabled={isPending}
        />
        <Button size="sm" onClick={confirm} disabled={isPending || value.trim().length < 3} loading={isPending}>
          OK
        </Button>
        <Button size="sm" variant="ghost" onClick={cancel} disabled={isPending}>
          ✕
        </Button>
      </div>
    );
  }

  return (
    <div className={styles.nameCol}>
      <div className={styles.nameRow}>
        <span className={[styles.productName, hasGarbageName ? styles.noName : ''].join(' ')}>
          {product.name ?? <em>Sem nome</em>}
        </span>
        <button className={styles.editNameBtn} onClick={startEdit} title="Editar nome">
          ✎
        </button>
      </div>
      <a href={product.url} target="_blank" rel="noreferrer" className={styles.productUrl} title={product.url}>
        {formatUrlPath(product.url)}
      </a>
    </div>
  );
}

// ─── Products page ────────────────────────────────────────────────────────────

export function Products() {
  const [modal, setModal] = useState<ModalType>(null);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  // Abre o modal de URL quando chega de /products?adicionar=url (ex.: EmptyState do Dashboard).
  // Lê o parâmetro uma única vez e o remove para não reabrir o modal em navegações futuras.
  useEffect(() => {
    if (searchParams.get('adicionar') === 'url') {
      setModal('url');
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete('adicionar');
          return next;
        },
        { replace: true },
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Per-product loading: tracks which product IDs are currently being refreshed
  const [refreshingIds, setRefreshingIds] = useState<Set<string>>(new Set());

  const { data, isLoading, isError, refetch } = useProducts();
  const { mutateAsync: removeProduct, isPending: isRemoving } = useRemoveProduct();
  const { mutate: refreshPrice } = useRefreshPrice();
  const closeToast = useCallback(() => setToast(null), []);

  const products = data?.products ?? [];

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

  const allSelected = products.length > 0 && selectedIds.size === products.length;
  const toggleSelectAll = () => {
    setSelectedIds(allSelected ? new Set() : new Set(products.map((p) => p.id)));
  };

  const handleConfirmDelete = async () => {
    try {
      await Promise.all([...selectedIds].map((id) => removeProduct(id)));
      setToast({ message: 'Produtos removidos com sucesso.', type: 'success' });
      setSelectedIds(new Set());
    } catch {
      setToast({ message: 'Erro ao remover produtos. Tente novamente.', type: 'error' });
    } finally {
      setConfirmDeleteOpen(false);
    }
  };

  const handleRefresh = (product: Product) => {
    setRefreshingIds((prev) => new Set(prev).add(product.id));

    refreshPrice(product.id, {
      onSuccess: (result) => {
        setRefreshingIds((prev) => {
          const next = new Set(prev);
          next.delete(product.id);
          return next;
        });

        if (result.status === 'ok') {
          const priceStr = result.price != null ? formatCurrency(result.price) : '—';
          const stockStr = result.in_stock === false ? ' · Sem estoque' : '';
          setToast({
            message: `Preço atualizado: ${priceStr}${stockStr}`,
            type: 'success',
          });
        } else {
          // Specific error messages based on what went wrong
          setToast({ message: result.detail, type: 'error' });
        }
      },
      onError: (err) => {
        setRefreshingIds((prev) => {
          const next = new Set(prev);
          next.delete(product.id);
          return next;
        });
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.toLowerCase().includes('timeout')) {
          setToast({
            message: 'Tempo esgotado ao buscar preço. O site pode estar lento. Tente novamente.',
            type: 'error',
          });
        } else {
          setToast({ message: `Erro ao atualizar preço: ${msg}`, type: 'error' });
        }
      },
    });
  };

  const columns: Column<Product>[] = [
    {
      key: 'select',
      header: (
        <input
          type="checkbox"
          aria-label="Selecionar todos"
          className={styles.checkbox}
          checked={allSelected}
          onChange={toggleSelectAll}
        />
      ),
      width: '36px',
      render: (r) => (
        <input
          type="checkbox"
          aria-label={`Selecionar ${r.name ?? 'produto'}`}
          className={styles.checkbox}
          checked={selectedIds.has(r.id)}
          onChange={() => toggleSelect(r.id)}
        />
      ),
    },
    {
      key: 'name',
      header: 'Produto',
      render: (r) => (
        <div className={styles.productCell}>
          {r.image_url ? (
            <img
              src={r.image_url}
              alt=""
              className={styles.thumb}
              loading="lazy"
              decoding="async"
              width={44}
              height={56}
            />
          ) : (
            <div className={styles.thumbPlaceholder} />
          )}
          <NameCell product={r} />
        </div>
      ),
    },
    {
      key: 'store',
      header: 'Loja',
      width: '120px',
      render: (r) => <span className={styles.storeBadge}>{formatStore(r.store)}</span>,
    },
    {
      key: 'current_price',
      header: 'Preço atual',
      width: '130px',
      render: (r) => (
        <div>
          <div className={styles.price}>
            {r.current_price != null ? formatCurrency(r.current_price) : <span className={styles.noPrice}>—</span>}
          </div>
          {r.in_stock === false && <span className={styles.outOfStock}>Sem estoque</span>}
        </div>
      ),
    },
    {
      key: 'last_checked',
      header: 'Última verificação',
      width: '180px',
      render: (r) => {
        const display = describeLastCheck(r);
        if (display.kind === 'none') {
          return <span className={styles.dateNone}>Ainda não verificado</span>;
        }
        if (display.kind === 'failed') {
          return (
            <span
              className={[styles.date, styles.dateFailed].join(' ')}
              title={
                display.checkedAt
                  ? `Última verificação bem-sucedida: ${formatDate(display.checkedAt)}`
                  : 'Nunca verificado com sucesso'
              }
            >
              <Icon name="alert" size={12} />
              {display.text}
            </span>
          );
        }
        return (
          <span
            className={[styles.date, display.stale ? styles.dateStale : ''].join(' ')}
            title={
              display.stale
                ? 'Sem verificação há mais de 12 h'
                : `Verificado em ${formatDate(display.checkedAt)}`
            }
          >
            {display.stale && <Icon name="alert" size={12} />}
            {display.noOffer ? `${display.when} · sem oferta principal` : display.when}
          </span>
        );
      },
    },
    {
      key: 'actions',
      header: '',
      width: '160px',
      render: (r) => {
        const isRefreshing = refreshingIds.has(r.id);
        return (
          <div className={styles.rowActions}>
            <Button
              variant="secondary"
              size="sm"
              loading={isRefreshing}
              disabled={isRefreshing}
              title="Buscar preço atualizado agora"
              onClick={() => handleRefresh(r)}
            >
              {isRefreshing ? 'Buscando…' : 'Atualizar preço'}
            </Button>
          </div>
        );
      },
    },
  ];

  const total = data?.total ?? products.length;

  return (
    <div className={styles.page}>
      <PageHeader
        title="Produtos monitorados"
        subtitle={`${total} anúncio${total === 1 ? '' : 's'} · Amazon e Mercado Livre`}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setModal('search')}>
              Buscar por nome
            </Button>
            <Button size="sm" onClick={() => setModal('url')}>
              + Adicionar URL
            </Button>
          </>
        }
      />

      <Card>
        {isError ? (
          <div className={styles.errorState}>
            <p>Erro ao carregar produtos. Verifique se a API está rodando.</p>
            <Button variant="ghost" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
          </div>
        ) : !isLoading && products.length === 0 ? (
          <EmptyState
            title="Nenhum produto monitorado ainda"
            description="Busque pelo nome ou cole o link de um anúncio da Amazon ou do Mercado Livre — a gente avisa quando o preço cair."
            actions={
              <>
                <Button variant="secondary" onClick={() => setModal('search')}>
                  Buscar por nome
                </Button>
                <Button onClick={() => setModal('url')}>+ Adicionar URL</Button>
              </>
            }
          />
        ) : (
          <Table
            columns={columns}
            data={products}
            keyExtractor={(p) => p.id}
            loading={isLoading}
            emptyMessage="Nenhum produto monitorado. Adicione uma URL ou busque por nome."
            isRowSelected={(r) => selectedIds.has(r.id)}
          />
        )}
      </Card>

      <Modal isOpen={modal === 'url'} onClose={() => setModal(null)} title="Adicionar produto por URL">
        <AddProductForm onSuccess={() => setModal(null)} />
      </Modal>

      <Modal isOpen={modal === 'search'} onClose={() => setModal(null)} title="Buscar produto por nome" size="lg">
        <SearchByName />
      </Modal>

      {toast && <Toast message={toast.message} type={toast.type} onClose={closeToast} />}

      <ConfirmModal
        isOpen={confirmDeleteOpen}
        onClose={() => setConfirmDeleteOpen(false)}
        onConfirm={handleConfirmDelete}
        isLoading={isRemoving}
        title="Excluir produtos"
        message={`Tem certeza que deseja excluir ${selectedIds.size} produto(s) selecionado(s) do monitoramento? Essa ação não pode ser desfeita.`}
        confirmLabel="Excluir"
      />

      <SelectionBar count={selectedIds.size} onClear={() => setSelectedIds(new Set())}>
        <Button variant="dangerOutline" size="sm" onClick={() => setConfirmDeleteOpen(true)}>
          <Icon name="trash" size={14} />
          Excluir
        </Button>
      </SelectionBar>
    </div>
  );
}

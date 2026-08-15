import { useCallback, useRef, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { ConfirmModal } from '@/components/ConfirmModal';
import { Modal } from '@/components/Modal';
import { Table, type Column } from '@/components/Table';
import { Toast } from '@/components/Toast';
import { AddProductForm } from '@/features/products/components/AddProductForm';
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
      <div className={styles.nameEditRow}>
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
    <div>
      <div className={styles.nameRow}>
        <span className={[styles.productName, hasGarbageName ? styles.noName : ''].join(' ')}>
          {product.name ?? <em>Sem nome</em>}
        </span>
        <button className={styles.editNameBtn} onClick={startEdit} title="Editar nome">
          ✎
        </button>
      </div>
      <a href={product.url} target="_blank" rel="noreferrer" className={styles.productUrl}>
        {product.url}
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
      header: '',
      width: '36px',
      render: (r) => (
        <input
          type="checkbox"
          className={styles.checkbox}
          checked={selectedIds.has(r.id)}
          onChange={() => toggleSelect(r.id)}
        />
      ),
    },
    {
      key: 'store',
      header: 'Loja',
      width: '120px',
      render: (r) => <span className={styles.storeBadge}>{formatStore(r.store)}</span>,
    },
    {
      key: 'name',
      header: 'Produto',
      render: (r) => <NameCell product={r} />,
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
      key: 'created_at',
      header: 'Adicionado em',
      width: '150px',
      render: (r) => <span className={styles.date}>{r.created_at ? formatDate(r.created_at) : '—'}</span>,
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
              variant="ghost"
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

  return (
    <div className={styles.page}>
      <Card
        title={`Produtos monitorados${data ? ` (${data.total})` : ''}`}
        action={
          <div className={styles.actions}>
            <Button variant="secondary" size="sm" onClick={() => setModal('search')}>
              Buscar por nome
            </Button>
            <Button size="sm" onClick={() => setModal('url')}>
              + Adicionar URL
            </Button>
          </div>
        }
      >
        {selectedIds.size > 0 && (
          <div className={styles.toolbar}>
            <span className={styles.toolbarInfo}>
              {selectedIds.size} selecionado{selectedIds.size !== 1 ? 's' : ''}
            </span>
            <div className={styles.toolbarActions}>
              <Button size="sm" variant="ghost" onClick={toggleSelectAll}>
                {allSelected ? 'Desmarcar todos' : 'Selecionar todos'}
              </Button>
              <Button size="sm" variant="danger" onClick={() => setConfirmDeleteOpen(true)}>
                Excluir
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
                Cancelar
              </Button>
            </div>
          </div>
        )}

        {isError ? (
          <div className={styles.errorState}>
            <p>Erro ao carregar produtos. Verifique se a API está rodando.</p>
            <Button variant="ghost" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
          </div>
        ) : (
          <Table
            columns={columns}
            data={products}
            keyExtractor={(p) => p.id}
            loading={isLoading}
            emptyMessage="Nenhum produto monitorado. Adicione uma URL ou busque por nome."
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
    </div>
  );
}

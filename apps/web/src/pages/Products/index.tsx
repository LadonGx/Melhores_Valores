import { useCallback, useRef, useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Modal } from '@/components/Modal';
import { Table, type Column } from '@/components/Table';
import { Toast } from '@/components/Toast';
import { AddProductForm } from '@/features/products/components/AddProductForm';
import {
  useProducts,
  useRemoveProduct,
  useRescrapeProduct,
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
  const { data, isLoading, isError, refetch } = useProducts();
  const { mutate: removeProduct, isPending: isRemoving } = useRemoveProduct();
  const { mutate: rescrape, isPending: isRescrapePending } = useRescrapeProduct();
  const closeToast = useCallback(() => setToast(null), []);

  const products = data?.products ?? [];

  const columns: Column<Product>[] = [
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
      width: '140px',
      render: (r) => (
        <div className={styles.rowActions}>
          <Button
            variant="ghost"
            size="sm"
            disabled={isRescrapePending}
            title="Re-verificar preço e nome agora"
            onClick={() => {
              rescrape(r.url, {
                onSuccess: () => setToast({ message: 'Verificação agendada. Dados atualizarão em instantes.', type: 'success' }),
                onError: () => setToast({ message: 'Erro ao agendar verificação.', type: 'error' }),
              });
            }}
          >
            Atualizar
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={isRemoving}
            onClick={() => {
              if (confirm(`Remover "${r.name ?? r.url}" do monitoramento?`)) {
                removeProduct(r.id, {
                  onSuccess: () => setToast({ message: 'Produto removido com sucesso.', type: 'success' }),
                  onError: () => setToast({ message: 'Erro ao remover produto. Tente novamente.', type: 'error' }),
                });
              }
            }}
          >
            Remover
          </Button>
        </div>
      ),
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
    </div>
  );
}

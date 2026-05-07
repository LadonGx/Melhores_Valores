import { useState } from 'react';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Modal } from '@/components/Modal';
import { Table, type Column } from '@/components/Table';
import { AddProductForm } from '@/features/products/components/AddProductForm';
import { useProducts } from '@/features/products/hooks/useProducts';
import { SearchByName } from '@/features/search/components/SearchByName';
import type { Product } from '@mv/types';
import { formatDate, formatStore } from '@mv/utils';
import styles from './Products.module.css';

type ModalType = 'url' | 'search' | null;

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
    render: (r) => (
      <div>
        <div className={styles.productName}>{r.name ?? '—'}</div>
        <a href={r.url} target="_blank" rel="noreferrer" className={styles.productUrl}>
          {r.url}
        </a>
      </div>
    ),
  },
  {
    key: 'created_at',
    header: 'Adicionado em',
    width: '150px',
    render: (r) => <span className={styles.date}>{r.created_at ? formatDate(r.created_at) : '—'}</span>,
  },
];

export function Products() {
  const [modal, setModal] = useState<ModalType>(null);
  const { data, isLoading, isError, refetch } = useProducts();

  const products = data?.products ?? [];

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
    </div>
  );
}

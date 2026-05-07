import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { Input } from '@/components/Input';
import { Table, type Column } from '@/components/Table';
import { useProductHistory } from '@/features/products/hooks/useProducts';
import type { PriceHistoryEntry } from '@mv/types';
import { formatCurrency, formatDate } from '@mv/utils';
import styles from './History.module.css';

const schema = z.object({ productId: z.string().min(1, 'ID obrigatório') });
type FormValues = z.infer<typeof schema>;

const columns: Column<PriceHistoryEntry>[] = [
  {
    key: 'price',
    header: 'Preço',
    width: '140px',
    render: (row) => <strong>{row.price != null ? formatCurrency(row.price) : '—'}</strong>,
  },
  {
    key: 'inStock',
    header: 'Em estoque',
    width: '110px',
    render: (row) => (row.inStock ? 'Sim' : 'Não'),
  },
  {
    key: 'date',
    header: 'Data da coleta',
    render: (row) => formatDate(row.scrapedAt),
  },
];

export function History() {
  const [productId, setProductId] = useState('');
  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(schema),
  });

  const { data, isLoading, isError } = useProductHistory(productId);

  return (
    <div className={styles.page}>
      <Card title="Buscar histórico de produto">
        <form
          onSubmit={handleSubmit((v) => setProductId(v.productId))}
          className={styles.form}
        >
          <Input
            label="ID do Produto"
            placeholder="ex: clx123abc..."
            error={errors.productId?.message}
            {...register('productId')}
          />
          <Button type="submit">Buscar</Button>
        </form>
      </Card>

      {productId && (
        <Card
          title={data ? `${data.product.name ?? data.product.url}` : 'Produto'}
          action={
            data && (
              <div className={styles.priceStats}>
                <span>Atual: <strong>{data.current_price ? formatCurrency(data.current_price) : '—'}</strong></span>
                <span>Mínimo: <strong>{data.lowest_price ? formatCurrency(data.lowest_price) : '—'}</strong></span>
                <span>Média: <strong>{data.average_price ? formatCurrency(data.average_price) : '—'}</strong></span>
              </div>
            )
          }
        >
          {isError ? (
            <p className={styles.error}>Produto não encontrado.</p>
          ) : (
            <Table
              columns={columns}
              data={data?.history ?? []}
              keyExtractor={(h) => h.id}
              loading={isLoading}
              emptyMessage="Nenhum histórico de preços disponível."
            />
          )}
        </Card>
      )}
    </div>
  );
}

import { Card } from '@/components/Card';
import { useProducts } from '@/features/products/hooks/useProducts';
import { formatDate, formatStore } from '@mv/utils';
import styles from './Dashboard.module.css';

export function Dashboard() {
  const { data, isLoading } = useProducts();
  const products = data?.products ?? [];
  const stores = new Set(products.map((p) => p.store)).size;

  return (
    <div className={styles.page}>
      <div className={styles.stats}>
        <Card>
          <div className={styles.stat}>
            <span className={styles.statValue}>{isLoading ? '—' : data?.total ?? 0}</span>
            <span className={styles.statLabel}>Produtos monitorados</span>
          </div>
        </Card>
        <Card>
          <div className={styles.stat}>
            <span className={styles.statValue}>{isLoading ? '—' : stores}</span>
            <span className={styles.statLabel}>Lojas ativas</span>
          </div>
        </Card>
      </div>

      <Card title="Produtos recentes">
        {isLoading ? (
          <p className={styles.empty}>Carregando...</p>
        ) : products.length === 0 ? (
          <p className={styles.empty}>
            Nenhum produto monitorado.{' '}
            <a href="/products">Adicione seu primeiro produto.</a>
          </p>
        ) : (
          <ul className={styles.list}>
            {products.slice(0, 10).map((p) => (
              <li key={p.id} className={styles.listItem}>
                <span className={styles.store}>{formatStore(p.store)}</span>
                <span className={styles.name}>{p.name ?? p.url}</span>
                <span className={styles.date}>{p.created_at ? formatDate(p.created_at) : ''}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

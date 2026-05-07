import { Card } from '@/components/Card';
import { SearchByName } from '@/features/search/components/SearchByName';
import styles from './Search.module.css';

export function Search() {
  return (
    <div className={styles.page}>
      <Card title="Buscar produto por nome">
        <p className={styles.hint}>
          Digite o nome do produto para buscar nas lojas Amazon e Mercado Livre.
          Os resultados são ordenados pelo menor preço. Clique em{' '}
          <strong>Monitorar</strong> para acompanhar o histórico de preço de um item.
        </p>
        <SearchByName />
      </Card>
    </div>
  );
}

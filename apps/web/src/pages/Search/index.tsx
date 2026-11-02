import { PageHeader } from '@/components/PageHeader';
import { SearchByName } from '@/features/search/components/SearchByName';
import styles from './Search.module.css';

export function Search() {
  return (
    <div className={styles.page}>
      <PageHeader
        title="Buscar produto"
        subtitle={
          <>
            Digite o nome do produto para buscar nas lojas Amazon e Mercado Livre. Os resultados são
            ordenados pelo menor preço. Clique em <strong>Monitorar</strong> para acompanhar o
            histórico de preço de um item.
          </>
        }
      />
      <SearchByName />
    </div>
  );
}

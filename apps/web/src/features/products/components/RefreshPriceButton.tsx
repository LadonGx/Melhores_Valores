import { useState } from 'react';
import { Button } from '@/components/Button';
import { useRefreshPrice } from '@/features/products/hooks/useProducts';
import {
  describeRefreshError,
  describeRefreshResult,
  type RefreshFeedback,
} from '@/features/products/refreshMessages';
import styles from './RefreshPriceButton.module.css';

/**
 * "Atualizar preço agora" dentro dos detalhes do item. A checagem automática só
 * roda com o app aberto, então o usuário dispara quando quiser; o resultado
 * aparece ao lado do botão e o gráfico/estatísticas do modal são revalidados.
 */
export function RefreshPriceButton({ productId }: { productId: string }) {
  const { mutate, isPending } = useRefreshPrice();
  const [feedback, setFeedback] = useState<RefreshFeedback | null>(null);

  const handleClick = () => {
    setFeedback(null);
    mutate(productId, {
      onSuccess: (result) => setFeedback(describeRefreshResult(result)),
      onError: (err) => setFeedback(describeRefreshError(err)),
    });
  };

  return (
    <div className={styles.wrap}>
      <Button
        variant="secondary"
        size="sm"
        loading={isPending}
        title="Buscar o preço atual na loja agora"
        onClick={handleClick}
      >
        {isPending ? 'Buscando preço…' : 'Atualizar preço agora'}
      </Button>
      {feedback && (
        <span
          role="status"
          className={feedback.type === 'success' ? styles.success : styles.error}
        >
          {feedback.message}
        </span>
      )}
    </div>
  );
}

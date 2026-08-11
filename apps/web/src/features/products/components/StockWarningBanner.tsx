import { useState } from 'react';
import { Button } from '@/components/Button';
import { useUpdateProductStatus } from '@/features/products/hooks/useProducts';
import type { Product } from '@mv/types';
import { formatDate } from '@mv/utils';
import styles from './StockWarningBanner.module.css';

interface StockWarningBannerProps {
  product: Product;
}

export function StockWarningBanner({ product }: StockWarningBannerProps) {
  const { mutate: updateStatus, isPending } = useUpdateProductStatus();
  const [dismissed, setDismissed] = useState(false);
  const isPaused = product.status === 'paused';
  const autoFlagged = product.in_stock === false;

  // Sem sinal automático de indisponibilidade: ainda assim deixa uma opção manual,
  // já que sites com bloqueio anti-bot (ex: verificação da conta no Mercado Livre)
  // impedem a checagem automática de confirmar que o anúncio saiu do ar/estoque.
  if (!isPaused && (!autoFlagged || dismissed)) {
    return (
      <div className={styles.manualHint}>
        <button
          type="button"
          className={styles.manualHintLink}
          disabled={isPending}
          onClick={() => updateStatus({ productId: product.id, status: 'paused' })}
        >
          Este anúncio saiu de estoque ou não existe mais? Pausar monitoramento
        </button>
      </div>
    );
  }

  if (isPaused) {
    return (
      <div className={`${styles.banner} ${styles.paused}`}>
        <span className={styles.icon}>⏸</span>
        <div className={styles.text}>
          <strong>Monitoramento pausado.</strong> O histórico de preços deste anúncio continua
          disponível e nada foi apagado.
        </div>
        <Button
          variant="secondary"
          size="sm"
          disabled={isPending}
          onClick={() => updateStatus({ productId: product.id, status: 'active' })}
        >
          Reativar monitoramento
        </Button>
      </div>
    );
  }

  return (
    <div className={`${styles.banner} ${styles.warning}`}>
      <span className={styles.icon}>⚠</span>
      <div className={styles.text}>
        <strong>Este anúncio pode estar fora de estoque ou ter sido removido.</strong>{' '}
        {product.last_checked
          ? `Última verificação em ${formatDate(product.last_checked)}.`
          : null}{' '}
        O histórico de preços continua preservado — ele pode voltar a ficar disponível no futuro.
      </div>
      <div className={styles.actions}>
        <Button variant="ghost" size="sm" disabled={isPending} onClick={() => setDismissed(true)}>
          Manter mesmo assim
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={isPending}
          onClick={() => updateStatus({ productId: product.id, status: 'paused' })}
        >
          Pausar monitoramento
        </Button>
      </div>
    </div>
  );
}

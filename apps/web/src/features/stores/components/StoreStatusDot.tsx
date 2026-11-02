import type { StoreHealthStatus } from '@mv/types';
import styles from './StoreStatusDot.module.css';

export const STORE_STATUS_LABEL: Record<StoreHealthStatus, string> = {
  ok: 'Funcionando',
  partial: 'Parcial',
  blocked: 'Bloqueada',
  error: 'Com falhas',
  unknown: 'Sem dados recentes',
};

/** Bolinha de status da loja: verde ok · âmbar parcial · vermelho bloqueada/falhas · cinza sem dados. */
export function StoreStatusDot({ status, size = 8 }: { status: StoreHealthStatus; size?: number }) {
  return (
    <span
      className={`${styles.dot} ${styles[status]}`}
      style={{ width: size, height: size }}
      aria-hidden="true"
    />
  );
}

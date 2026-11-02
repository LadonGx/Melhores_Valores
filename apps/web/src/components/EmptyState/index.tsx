import type { ReactNode } from 'react';
import { LogoMark } from '@/components/Logo';
import styles from './EmptyState.module.css';

interface EmptyStateProps {
  /** Ícone acima do título. Padrão: símbolo da marca. Passe `null` para omitir (estado compacto). */
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

/** Estado vazio calmo e genérico: símbolo da marca, título, descrição e ações em linha. */
export function EmptyState({ icon, title, description, actions }: EmptyStateProps) {
  return (
    <div className={styles.wrapper}>
      {icon !== null && (
        <div className={styles.icon}>{icon ?? <LogoMark variant="app" size={44} />}</div>
      )}
      <h3 className={styles.title}>{title}</h3>
      {description && <p className={styles.description}>{description}</p>}
      {actions && <div className={styles.actions}>{actions}</div>}
    </div>
  );
}

import type { ReactNode } from 'react';
import { Icon } from '@/components/Icon';
import styles from './SelectionBar.module.css';

interface SelectionBarProps {
  /** Quantidade de itens selecionados. Com 0 a barra não é renderizada. */
  count: number;
  /** Ações (Buttons). Use size="sm"; para excluir, variant="dangerOutline". */
  children: ReactNode;
  /** Limpa a seleção (botão ×). */
  onClear: () => void;
}

/**
 * Barra flutuante de ações em lote (padrão "Seleção · Barra flutuante").
 * Fica presa ao rodapé da área de conteúdo (position: sticky) enquanto houver seleção.
 */
export function SelectionBar({ count, children, onClear }: SelectionBarProps) {
  if (count === 0) return null;

  return (
    <div className={styles.dock}>
      <div className={styles.bar} role="toolbar" aria-label="Ações para os itens selecionados">
        <span className={styles.count} aria-live="polite">
          {count} selecionado{count === 1 ? '' : 's'}
        </span>
        <span className={styles.divider} aria-hidden="true" />
        <div className={styles.actions}>{children}</div>
        <button type="button" className={styles.clear} onClick={onClear} aria-label="Limpar seleção" title="Limpar seleção">
          <Icon name="x" size={15} />
        </button>
      </div>
    </div>
  );
}

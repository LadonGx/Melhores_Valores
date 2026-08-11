import type { ReactNode } from 'react';
import styles from './Tooltip.module.css';

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
}

export function Tooltip({ content, children }: TooltipProps) {
  return (
    <span className={styles.wrapper} tabIndex={0}>
      {children}
      <span className={styles.bubble} role="tooltip">
        {content}
      </span>
    </span>
  );
}

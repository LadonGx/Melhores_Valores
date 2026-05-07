import type { HTMLAttributes, ReactNode } from 'react';
import styles from './Card.module.css';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  action?: ReactNode;
}

export function Card({ title, action, children, className, ...props }: CardProps) {
  return (
    <div className={[styles.card, className].filter(Boolean).join(' ')} {...props}>
      {(title || action) && (
        <div className={styles.header}>
          {title && <h2 className={styles.title}>{title}</h2>}
          {action && <div className={styles.action}>{action}</div>}
        </div>
      )}
      <div className={styles.body}>{children}</div>
    </div>
  );
}

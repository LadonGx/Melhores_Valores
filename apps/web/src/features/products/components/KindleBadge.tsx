import type { Product } from '@mv/types';
import { kindleBadge } from '../format';
import styles from './KindleBadge.module.css';

interface KindleBadgeProps {
  product: Product;
  /** Classe extra quando o módulo local do selo não for o ideal (CSS Modules). */
  className?: string;
}

/** Selo discreto "Kindle"; só aparece para anúncios eBook Kindle (físico/desconhecido: nada). */
export function KindleBadge({ product, className }: KindleBadgeProps) {
  const label = kindleBadge(product);
  if (!label) return null;
  return (
    <span
      className={className ? [styles.kindleBadge, className].join(' ') : styles.kindleBadge}
      title="Anúncio do eBook Kindle — os preços não são comparáveis com a edição física"
    >
      {label}
    </span>
  );
}

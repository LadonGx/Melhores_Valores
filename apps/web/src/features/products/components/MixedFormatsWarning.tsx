import { Icon } from '@/components/Icon';
import type { Product } from '@mv/types';
import { MIXED_FORMATS_WARNING, hasMixedFormats } from '../format';
import styles from './MixedFormatsWarning.module.css';

interface MixedFormatsWarningProps {
  /** Anúncios em jogo (do grupo + os selecionados, no fluxo de adicionar ao grupo). */
  products: Product[];
}

/**
 * Aviso claro e NÃO bloqueante: a seleção/grupo mistura eBook Kindle e edição física.
 * Some sozinho quando os formatos são compatíveis (desconhecido não conta).
 */
export function MixedFormatsWarning({ products }: MixedFormatsWarningProps) {
  if (!hasMixedFormats(products)) return null;
  return (
    <span className={styles.warning} role="note">
      <Icon name="alert" size={13} />
      {MIXED_FORMATS_WARNING}
    </span>
  );
}

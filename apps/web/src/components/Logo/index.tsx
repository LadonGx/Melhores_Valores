import styles from './Logo.module.css';

/**
 * Logo "Etiqueta": etiqueta de preço com uma linha em queda até o melhor valor (ponto verde).
 * SVG inline — sem imagem nem fonte extra para baixar.
 */

// Corpo da etiqueta + furo (fill-rule evenodd recorta o furo)
const TAG_PATH =
  'M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42Z' +
  'M9 7.5a1.5 1.5 0 1 1-3 0a1.5 1.5 0 1 1 3 0Z';

const DROP_LINE = '6.6 10.6 9.6 13.6 11.4 11.9 14.6 15.1';

interface LogoMarkProps {
  size?: number;
  /** "plain": etiqueta lilás. "app": quadrado da marca com etiqueta branca (ícone de app). */
  variant?: 'plain' | 'app';
  className?: string;
}

export function LogoMark({ size = 32, variant = 'plain', className }: LogoMarkProps) {
  if (variant === 'app') {
    return (
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className={className}>
        <rect width="32" height="32" rx="8" fill="var(--color-primary)" />
        <g transform="translate(4 4)">
          <path d={TAG_PATH} fill="#fff" fillRule="evenodd" />
          <polyline points={DROP_LINE} fill="none" stroke="var(--color-primary)" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="15.3" cy="15.8" r="2.1" fill="var(--color-accent)" />
        </g>
      </svg>
    );
  }

  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" className={className}>
      <path d={TAG_PATH} fill="var(--color-primary-soft)" fillRule="evenodd" />
      <polyline points={DROP_LINE} fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="15.3" cy="15.8" r="2.2" fill="var(--color-accent)" stroke="var(--color-sidebar)" strokeWidth="0.9" />
    </svg>
  );
}

interface LogoProps {
  /** Esconde o nome e mostra só o símbolo (sidebar recolhida). */
  compact?: boolean;
  size?: number;
}

export function Logo({ compact = false, size = 32 }: LogoProps) {
  return (
    <span className={styles.logo} aria-label="Melhores Valores">
      <LogoMark size={size} />
      {!compact && (
        <span className={styles.wordmark} aria-hidden="true">
          <span className={styles.first}>Melhores</span>
          <span className={styles.second}>Valores</span>
        </span>
      )}
    </span>
  );
}

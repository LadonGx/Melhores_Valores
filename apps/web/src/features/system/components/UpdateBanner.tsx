import { useState } from 'react';
import { useUpdateCheck } from '@/features/system/hooks/useSystem';
import styles from './UpdateBanner.module.css';

/** Última versão cujo aviso o usuário fechou (o aviso volta quando sair outra). */
export const DISMISSED_KEY = 'mv_update_dismissed';

function readDismissed(): string | null {
  try {
    return localStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

/**
 * Faixa no topo quando há versão nova nos Releases do GitHub. O link abre no
 * navegador padrão (a janela do app repassa links target="_blank" para ele).
 */
export function UpdateBanner() {
  const { data } = useUpdateCheck();
  const [dismissed, setDismissed] = useState(readDismissed);

  if (!data?.update_available || !data.latest || dismissed === data.latest) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISSED_KEY, data.latest ?? '');
    } catch {
      // sem armazenamento: o aviso só some até a próxima abertura
    }
    setDismissed(data.latest);
  };

  return (
    <div className={styles.banner} role="status">
      <span>
        Nova versão disponível: <strong>{data.latest}</strong> (você tem a {data.current}).
      </span>
      <a href={data.url} target="_blank" rel="noreferrer" className={styles.link}>
        Baixar →
      </a>
      <button type="button" className={styles.close} onClick={dismiss} aria-label="Dispensar aviso">
        ×
      </button>
    </div>
  );
}

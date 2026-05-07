import { useEffect } from 'react';
import styles from './Toast.module.css';

interface ToastProps {
  message: string;
  type?: 'success' | 'error';
  onClose: () => void;
  duration?: number;
}

export function Toast({ message, type = 'success', onClose, duration = 4000 }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(onClose, duration);
    return () => clearTimeout(timer);
  }, [onClose, duration]);

  return (
    <div className={[styles.toast, styles[type]].join(' ')}>
      <span className={styles.icon}>{type === 'success' ? '✓' : '✕'}</span>
      <span>{message}</span>
      <button className={styles.close} onClick={onClose} aria-label="Fechar">×</button>
    </div>
  );
}

import { useLocation } from 'react-router-dom';
import { useAppStore } from '@/store/app.store';
import styles from './Header.module.css';

const ROUTE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/products': 'Produtos',
  '/search': 'Buscar produto',
};

export function Header() {
  const { pathname } = useLocation();
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const title = ROUTE_TITLES[pathname] ?? 'Melhores Valores';

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <button className={styles.menuBtn} onClick={toggleSidebar} aria-label="Toggle sidebar">
          <span />
          <span />
          <span />
        </button>
        <h1 className={styles.title}>{title}</h1>
      </div>
    </header>
  );
}

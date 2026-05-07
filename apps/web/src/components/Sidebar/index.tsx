import { NavLink } from 'react-router-dom';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/products', label: 'Produtos', end: false },
  { to: '/search', label: 'Buscar produto', end: false },
  { to: '/history', label: 'Histórico', end: false },
  { to: '/settings', label: 'Configurações', end: false },
];

export function Sidebar() {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <div className={styles.logo}>MV</div>
        <span className={styles.brandName}>Melhores Valores</span>
      </div>

      <nav className={styles.nav}>
        {NAV_ITEMS.map(({ to, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `${styles.item} ${isActive ? styles.active : ''}`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className={styles.footer}>
        <div className={styles.apiStatus}>
          <span className={styles.statusDot} />
          <span>API conectada</span>
        </div>
      </div>
    </aside>
  );
}

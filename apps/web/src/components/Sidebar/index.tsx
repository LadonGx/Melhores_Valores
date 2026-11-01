import { NavLink } from 'react-router-dom';
import { Icon, type IconName } from '@/components/Icon';
import { Logo } from '@/components/Logo';
import { useAppStore } from '@/store/app.store';
import styles from './Sidebar.module.css';

const NAV_ITEMS: { to: string; label: string; end: boolean; icon: IconName }[] = [
  { to: '/', label: 'Dashboard', end: true, icon: 'dashboard' },
  { to: '/products', label: 'Produtos', end: false, icon: 'list' },
  { to: '/search', label: 'Buscar produto', end: false, icon: 'search' },
];

export function Sidebar() {
  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const collapsed = !sidebarOpen;

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`}>
      <div className={styles.brand}>
        <NavLink to="/" className={styles.brandLink} title="Melhores Valores">
          <Logo compact={collapsed} />
        </NavLink>
        <button
          type="button"
          className={styles.toggle}
          onClick={toggleSidebar}
          aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
          aria-expanded={!collapsed}
          title={collapsed ? 'Expandir menu' : 'Recolher menu'}
        >
          <Icon name="panel" size={16} />
        </button>
      </div>

      <nav className={styles.nav} aria-label="Navegação principal">
        {NAV_ITEMS.map(({ to, label, end, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={collapsed ? label : undefined}
            className={({ isActive }) => `${styles.item} ${isActive ? styles.active : ''}`}
          >
            <Icon name={icon} size={17} className={styles.itemIcon} />
            <span className={styles.label}>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className={styles.footer}>
        <span className={styles.stores}>Amazon · Mercado Livre</span>
      </div>
    </aside>
  );
}

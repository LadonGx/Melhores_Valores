import { Outlet } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';
import styles from './DashboardLayout.module.css';

export function DashboardLayout() {
  return (
    <div className={styles.layout}>
      <Sidebar />
      <main className={styles.content}>
        <div className={styles.inner}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}

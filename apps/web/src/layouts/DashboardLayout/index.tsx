import { Outlet } from 'react-router-dom';
import { Header } from '@/components/Header';
import { Sidebar } from '@/components/Sidebar';
import { useAppStore } from '@/store/app.store';
import styles from './DashboardLayout.module.css';

export function DashboardLayout() {
  const sidebarOpen = useAppStore((s) => s.sidebarOpen);

  return (
    <div className={styles.layout}>
      {sidebarOpen && <Sidebar />}
      <div className={styles.main}>
        <Header />
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

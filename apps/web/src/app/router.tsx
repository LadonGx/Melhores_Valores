import { createBrowserRouter } from 'react-router-dom';
import { DashboardLayout } from '@/layouts/DashboardLayout';
import { Dashboard } from '@/pages/Dashboard';
import { History } from '@/pages/History';
import { Products } from '@/pages/Products';
import { Search } from '@/pages/Search';
import { Settings } from '@/pages/Settings';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'products', element: <Products /> },
      { path: 'search', element: <Search /> },
      { path: 'history', element: <History /> },
      { path: 'settings', element: <Settings /> },
    ],
  },
]);

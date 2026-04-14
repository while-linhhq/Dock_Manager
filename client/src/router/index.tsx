import React from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { MainLayout } from '../layouts/MainLayout';
import { AuthLayout } from '../layouts/AuthLayout';
import { PATHS } from './paths';
import { HomePage } from '../pages/HomePage';
import { LoginPage } from '../pages/LoginPage';
import { OrdersPage } from '../pages/OrdersPage';
import { RevenuePage } from '../pages/RevenuePage';
import { VesselsPage } from '../pages/VesselsPage';
import { PortPage } from '../pages/PortPage';
import { StatisticsPage } from '../pages/StatisticsPage';
import { BackupPage } from '../pages/BackupPage';
import { UsersPage } from '../pages/UsersPage';
import { ProfilePage } from '../pages/ProfilePage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { useAuthStore } from '../features/auth/store/authStore';
import { hasMenuAccess, type MenuKey } from '../utils/rbac';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  if (!isAuthenticated) return <Navigate to={PATHS.LOGIN} replace />;
  return <>{children}</>;
};

const PublicRoute = ({ children }: { children: React.ReactNode }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  if (isAuthenticated) return <Navigate to={PATHS.HOME} replace />;
  return <>{children}</>;
};

const RequireMenuAccess = ({
  menu,
  children,
}: {
  menu: MenuKey;
  children: React.ReactNode;
}) => {
  const user = useAuthStore((state) => state.user);
  const isLoading = useAuthStore((state) => state.isLoading);
  const authBootstrapped = useAuthStore((state) => state.authBootstrapped);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to={PATHS.LOGIN} replace />;
  }

  if (!user) {
    if (isLoading || !authBootstrapped) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 py-24 text-gray-500 dark:text-gray-400">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500" aria-hidden />
          <p className="text-xs font-mono uppercase tracking-widest">Đang tải phiên đăng nhập…</p>
        </div>
      );
    }
    return <Navigate to={PATHS.LOGIN} replace />;
  }

  if (!hasMenuAccess(user, menu)) {
    return <Navigate to={PATHS.HOME} replace />;
  }
  return <>{children}</>;
};

const router = createBrowserRouter([
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <MainLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <HomePage /> },
      { path: PATHS.ORDERS, element: <RequireMenuAccess menu="orders"><OrdersPage /></RequireMenuAccess> },
      { path: PATHS.REVENUE, element: <RequireMenuAccess menu="revenue"><RevenuePage /></RequireMenuAccess> },
      { path: PATHS.VESSELS, element: <RequireMenuAccess menu="vessels"><VesselsPage /></RequireMenuAccess> },
      { path: PATHS.PORT, element: <RequireMenuAccess menu="port"><PortPage /></RequireMenuAccess> },
      { path: PATHS.STATS, element: <RequireMenuAccess menu="stats"><StatisticsPage /></RequireMenuAccess> },
      { path: PATHS.BACKUP, element: <RequireMenuAccess menu="backup"><BackupPage /></RequireMenuAccess> },
      { path: PATHS.USERS, element: <RequireMenuAccess menu="users"><UsersPage /></RequireMenuAccess> },
      { path: PATHS.PROFILE, element: <RequireMenuAccess menu="profile"><ProfilePage /></RequireMenuAccess> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  {
    path: '/',
    element: (
      <PublicRoute>
        <AuthLayout />
      </PublicRoute>
    ),
    children: [
      { path: PATHS.LOGIN, element: <LoginPage /> },
    ],
  },
  {
    path: '*',
    element: <Navigate to={PATHS.HOME} replace />,
  },
]);

export const AppRouter: React.FC = () => {
  return <RouterProvider router={router} />;
};

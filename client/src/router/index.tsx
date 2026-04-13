import React from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
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
  if (!user) {
    return <>{children}</>;
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
    element: (
      <div className="min-h-screen bg-[#0a0a0b] flex items-center justify-center text-red-500 font-mono font-bold uppercase tracking-[0.5em]">
        404 - System Error
      </div>
    ),
  },
]);

export const AppRouter: React.FC = () => {
  return <RouterProvider router={router} />;
};

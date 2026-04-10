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
import { useAuthStore } from '../features/auth/store/authStore';

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

const Placeholder = ({ title }: { title: string }) => (
  <div className="p-8 text-white font-bold uppercase tracking-widest">
    {title} Module
  </div>
);

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
      { path: PATHS.ORDERS, element: <OrdersPage /> },
      { path: PATHS.REVENUE, element: <RevenuePage /> },
      { path: PATHS.VESSELS, element: <VesselsPage /> },
      { path: PATHS.PORT, element: <PortPage /> },
      { path: PATHS.STATS, element: <StatisticsPage /> },
      { path: PATHS.BACKUP, element: <BackupPage /> },
      { path: PATHS.USERS, element: <UsersPage /> },
      { path: PATHS.PROFILE, element: <Placeholder title="User Profile" /> },
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

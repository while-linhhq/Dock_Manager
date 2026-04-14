import React, { useEffect } from 'react';
import { AppRouter } from './router';
import { useAuthStore } from './features/auth/store/authStore';
import './index.css';

const AuthSessionSync: React.FC = () => {
  const checkAuth = useAuthStore((s) => s.checkAuth);
  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);
  return null;
};

const App: React.FC = () => {
  return (
    <React.StrictMode>
      <AuthSessionSync />
      <AppRouter />
    </React.StrictMode>
  );
};

export default App;

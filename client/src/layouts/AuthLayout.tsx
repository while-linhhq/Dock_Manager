import React from 'react';
import { Outlet } from 'react-router-dom';

export const AuthLayout: React.FC = () => {
  return (
    <div className="min-h-dvh flex items-center justify-center bg-gray-50 dark:bg-[#0a0a0b] py-8 sm:py-12 px-3 sm:px-6 lg:px-8 pt-[env(safe-area-inset-top)] pb-[max(2rem,env(safe-area-inset-bottom))]">
      <div className="max-w-md w-full space-y-6 sm:space-y-8 bg-white dark:bg-[#121214] dark:border dark:border-white/10 p-6 sm:p-8 rounded-xl shadow-lg">
        <Outlet />
      </div>
    </div>
  );
};

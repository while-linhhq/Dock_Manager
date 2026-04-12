import React from 'react';
import { Ship } from 'lucide-react';

export const LoginBranding: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center space-y-2">
      <div className="p-3 bg-blue-600 rounded-lg shadow-lg shadow-blue-500/50">
        <Ship className="w-10 h-10 text-white" />
      </div>
      <h1 className="text-2xl font-bold tracking-tighter text-gray-900 dark:text-white uppercase">
        Bason Port OS
      </h1>
      <p className="text-sm text-gray-500 font-mono uppercase text-center">
        YÊU CẦU TRUY CẬP HỆ THỐNG
      </p>
    </div>
  );
};

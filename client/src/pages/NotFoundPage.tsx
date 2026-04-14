import React from 'react';
import { Link } from 'react-router-dom';
import { PATHS } from '../router/paths';
import { cn } from '../utils/cn';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center py-16 sm:py-24 text-center space-y-4 px-4">
      <p className="text-[10px] font-mono uppercase tracking-[0.35em] text-gray-500">404</p>
      <h1 className={cn('text-lg sm:text-xl font-bold uppercase tracking-tight', 'text-gray-900 dark:text-white')}>
        Không tìm thấy trang
      </h1>
      <p className="text-sm text-gray-600 dark:text-gray-400 max-w-md">
        Đường dẫn không khớp menu. Dùng thanh bên để chọn mục khác hoặc về trang chủ.
      </p>
      <Link
        to={PATHS.HOME}
        className="inline-flex items-center px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider bg-blue-600 text-white hover:bg-blue-700"
      >
        Về bảng điều khiển
      </Link>
    </div>
  );
};

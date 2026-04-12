import React from 'react';
import { Loader2, AlertCircle } from 'lucide-react';
import { Button } from '../../../components/Button/Button';

export type LoginCredentialsFormProps = {
  email: string;
  password: string;
  isLoading: boolean;
  error: string | null;
  onEmailChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
};

export const LoginCredentialsForm: React.FC<LoginCredentialsFormProps> = ({
  email,
  password,
  isLoading,
  error,
  onEmailChange,
  onPasswordChange,
  onSubmit,
}) => {
  return (
    <>
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center space-x-3 text-red-500 text-sm animate-in fade-in slide-in-from-top-2">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1">
          <label className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest ml-1">
            Mã Nhân Viên / Email
          </label>
          <input
            type="text"
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
            disabled={isLoading}
            className="w-full px-4 py-3 bg-gray-50 dark:bg-white/5 border-2 border-gray-200 dark:border-white/10 rounded-lg focus:border-blue-600 focus:ring-0 transition-all font-mono text-sm dark:text-white disabled:opacity-50"
            placeholder="operator@bason.port"
            required
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest ml-1">
            Mã Bảo Mật
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => onPasswordChange(e.target.value)}
            disabled={isLoading}
            className="w-full px-4 py-3 bg-gray-50 dark:bg-white/5 border-2 border-gray-200 dark:border-white/10 rounded-lg focus:border-blue-600 focus:ring-0 transition-all font-mono text-sm dark:text-white disabled:opacity-50"
            placeholder="••••••••"
            required
          />
        </div>

        <Button
          type="submit"
          disabled={isLoading}
          className="w-full py-4 bg-blue-600 hover:bg-blue-700 text-white font-bold uppercase tracking-widest shadow-lg shadow-blue-500/30 transition-all active:scale-[0.98] disabled:opacity-50"
        >
          {isLoading ? (
            <div className="flex items-center space-x-2">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>Đang Xác Thực...</span>
            </div>
          ) : (
            'Khởi Tạo Phiên Làm Việc'
          )}
        </Button>
      </form>

      <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-between items-center text-[10px] font-mono text-gray-400 uppercase tracking-tighter">
        <span>Theo Dõi Tàu v1.0</span>
        <span className="flex items-center">
          <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1 animate-pulse" />
          Hệ Thống Đang Hoạt Động
        </span>
      </div>
    </>
  );
};

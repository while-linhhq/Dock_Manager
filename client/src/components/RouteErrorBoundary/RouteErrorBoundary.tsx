import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { PATHS } from '../../router/paths';
import { cn } from '../../utils/cn';

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
  error: Error | null;
};

/**
 * Bắt lỗi render trong vùng Outlet — giữ sidebar/header (MainLayout).
 * Parent nên đặt key={location.pathname} để đổi route là reset trạng thái lỗi.
 */
export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Outlet render error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError && this.state.error) {
      const msg = this.state.error.message || 'Unknown error';
      return (
        <div
          className={cn(
            'rounded-2xl border p-6 sm:p-8 max-w-2xl mx-auto space-y-4',
            'border-red-500/25 bg-red-500/5 dark:bg-red-500/10',
          )}
          role="alert"
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-red-600 dark:text-red-400">
            Lỗi hiển thị trang
          </p>
          <p className="text-sm text-gray-700 dark:text-gray-300">
            Có lỗi không mong muốn khi render nội dung. Menu bên trái vẫn dùng được để chuyển trang.
          </p>
          <pre
            className={cn(
              'text-xs font-mono p-3 rounded-lg overflow-x-auto',
              'bg-gray-100 dark:bg-black/40 text-red-700 dark:text-red-300',
            )}
          >
            {msg}
          </pre>
          <div className="flex flex-wrap gap-3 pt-2">
            <button
              type="button"
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider bg-gray-200 dark:bg-white/10 hover:bg-gray-300 dark:hover:bg-white/15"
            >
              Thử lại
            </button>
            <Link
              to={PATHS.HOME}
              className="inline-flex items-center px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider bg-blue-600 text-white hover:bg-blue-700"
            >
              Về trang chủ
            </Link>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider border border-gray-300 dark:border-white/15"
            >
              Tải lại trang
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

import React, { useEffect, useState } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { PATHS } from '../router/paths';
import { useAuthStore } from '../features/auth/store/authStore';
import { useThemeStore } from '../store/themeStore';
import { 
  LayoutDashboard, 
  ClipboardList, 
  Wallet, 
  Anchor, 
  Settings, 
  BarChart3, 
  Database, 
  LogOut,
  Ship,
  User,
  Sun,
  Moon,
  Menu,
  X,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../utils/cn';
import { formatTimeVN } from '../utils/date-time';
import { getAccessibleMenus, type MenuKey } from '../utils/rbac';

const navItems: Array<{ key: MenuKey; path: string; label: string; icon: LucideIcon }> = [
  { key: 'dashboard', path: PATHS.HOME, label: 'Bảng Điều Khiển', icon: LayoutDashboard },
  { key: 'orders', path: PATHS.ORDERS, label: 'Quản Lý Đơn Hàng', icon: ClipboardList },
  { key: 'revenue', path: PATHS.REVENUE, label: 'Quản Lý Thu Nhập', icon: Wallet },
  { key: 'vessels', path: PATHS.VESSELS, label: 'Mã Tàu', icon: Ship },
  { key: 'port', path: PATHS.PORT, label: 'Quản Lý Cảng', icon: Anchor },
  { key: 'stats', path: PATHS.STATS, label: 'Thống Kê', icon: BarChart3 },
  { key: 'backup', path: PATHS.BACKUP, label: 'Sao Lưu / Lịch Sử', icon: Database },
  { key: 'users', path: PATHS.USERS, label: 'Quản Lý User', icon: User },
];

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { isDarkMode, toggleTheme } = useThemeStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [systemClock, setSystemClock] = useState<Date>(() => new Date());
  const accessibleMenus = getAccessibleMenus(user);
  const visibleNavItems = navItems.filter((item) => accessibleMenus.includes(item.key));

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  useEffect(() => {
    const onResize = () => {
      if (typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches) {
        setSidebarOpen(false);
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSidebarOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) {
      return;
    }
    const mq = window.matchMedia('(min-width: 1024px)');
    if (mq.matches) {
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [sidebarOpen]);

  useEffect(() => {
    const tick = () => setSystemClock(new Date());
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  const handleLogout = () => {
    logout();
    navigate(PATHS.LOGIN);
  };

  return (
    <div
      className={cn(
        'flex min-h-dvh w-full max-w-[100vw] overflow-x-hidden font-sans selection:bg-blue-500/30 transition-colors duration-300 antialiased pt-[env(safe-area-inset-top)]',
        isDarkMode ? 'bg-[#0a0a0b] text-gray-200' : 'bg-gray-50 text-gray-800',
      )}
    >
      {sidebarOpen && (
        <button
          type="button"
          aria-label="Đóng menu điều hướng"
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[1px] lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[min(18rem,calc(100vw-2.5rem))] max-w-[85vw] flex-col border-r shadow-2xl transition-transform duration-200 ease-out lg:static lg:z-0 lg:w-64 lg:max-w-none lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
          isDarkMode ? 'bg-[#121214] border-white/5' : 'bg-white border-gray-200',
        )}
      >
        <div className={cn(
          'p-4 sm:p-5 lg:p-6 flex items-center justify-between gap-2 border-b transition-colors duration-300',
          isDarkMode ? "border-white/5" : "border-gray-100"
        )}>
          <div className="flex min-w-0 items-center space-x-3">
            <div className="p-2 bg-blue-600 rounded-lg">
              <Ship className="w-5 h-5 sm:w-6 sm:h-6 text-white" />
            </div>
            <span className={cn(
              'font-bold tracking-tighter uppercase text-base sm:text-lg truncate',
              isDarkMode ? "text-white" : "text-gray-900"
            )}>Bason OS</span>
          </div>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className={cn(
              'lg:hidden shrink-0 rounded-lg p-2 transition-colors',
              isDarkMode
                ? 'text-gray-400 hover:bg-white/10 hover:text-white'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900',
            )}
            aria-label="Đóng menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto overscroll-y-contain py-4 sm:py-6 px-3 sm:px-4 space-y-1">
          {visibleNavItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  'flex items-center space-x-3 px-3 sm:px-4 py-2.5 sm:py-3 rounded-lg transition-all duration-200 group min-h-[44px]',
                  isActive 
                    ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20" 
                    : isDarkMode 
                      ? "hover:bg-white/5 text-gray-400 hover:text-white"
                      : "hover:bg-gray-100 text-gray-500 hover:text-gray-900"
                )}
              >
                <Icon className={cn("w-5 h-5", isActive ? "text-white" : "text-gray-500 group-hover:text-blue-400")} />
                <span className="text-xs sm:text-sm font-bold uppercase tracking-wider leading-tight">
                  {item.label}
                </span>
              </Link>
            );
          })}
        </nav>

        <div className={cn(
          'p-3 sm:p-4 border-t space-y-3 sm:space-y-4 transition-colors duration-300 pb-[max(0.75rem,env(safe-area-inset-bottom))]',
          isDarkMode ? "border-white/5" : "border-gray-100"
        )}>
          <div className={cn(
            "flex items-center space-x-3 px-4 py-3 rounded-xl border transition-colors duration-300",
            isDarkMode ? "bg-white/5 border-white/5" : "bg-gray-50 border-gray-100"
          )}>
            <div className="w-8 h-8 rounded-full bg-linear-to-tr from-blue-600 to-cyan-400 flex items-center justify-center">
              <User className="w-4 h-4 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className={cn("text-xs font-bold truncate uppercase", isDarkMode ? "text-white" : "text-gray-900")}>
                {user?.full_name || 'Nhân Viên'}
              </p>
              <p className="text-[10px] text-gray-500 truncate font-mono uppercase">
                {user?.role == null
                  ? 'Quản Trị'
                  : typeof user.role === 'string'
                    ? user.role
                    : (user.role.name ?? user.role.role_name ?? 'Quản Trị')}
              </p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center space-x-2 px-4 py-3 min-h-[44px] text-red-400 hover:bg-red-500/10 rounded-lg transition-all font-bold uppercase text-xs tracking-widest border border-transparent hover:border-red-500/20"
          >
            <LogOut className="w-4 h-4" />
            <span>Đăng Xuất</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {/* Header */}
        <header className={cn(
          'min-h-14 sm:min-h-16 border-b flex flex-wrap items-center justify-between gap-2 gap-y-3 px-4 sm:px-6 lg:px-8 py-2 sm:py-0 shadow-sm transition-colors duration-300',
          isDarkMode ? "bg-[#121214] border-white/5" : "bg-white border-gray-200"
        )}>
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-4">
            <button
              type="button"
              className={cn(
                'lg:hidden shrink-0 rounded-lg p-2.5 -ml-1 transition-colors',
                isDarkMode ? 'text-gray-300 hover:bg-white/10' : 'text-gray-700 hover:bg-gray-100',
              )}
              onClick={() => setSidebarOpen(true)}
              aria-expanded={sidebarOpen}
              aria-label="Mở menu điều hướng"
            >
              <Menu className="h-5 w-5" />
            </button>
            <h2 className={cn('min-w-0 truncate text-xs sm:text-sm font-bold uppercase tracking-[0.15em] sm:tracking-[0.2em]', isDarkMode ? "text-white" : "text-gray-900")}>
              {navItems.find(i => i.path === location.pathname)?.label || 'Hệ Thống'}
            </h2>
            <div className={cn('hidden sm:block h-4 w-px shrink-0', isDarkMode ? "bg-white/10" : "bg-gray-200")} />
            <div className="hidden md:flex items-center space-x-2 min-w-0">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span className="text-[10px] font-mono text-green-500 uppercase tracking-tighter truncate">
                AI Core: Đang Hoạt Động
              </span>
            </div>
          </div>
          
          <div className="flex shrink-0 items-center gap-3 sm:gap-4">
            <button 
              onClick={toggleTheme}
              className={cn(
                'p-2 rounded-lg transition-all flex items-center gap-2 border min-h-[44px] min-w-[44px] sm:min-w-0 justify-center',
                isDarkMode 
                  ? "bg-white/5 border-white/10 text-yellow-400 hover:bg-white/10" 
                  : "bg-gray-100 border-gray-200 text-gray-600 hover:bg-gray-200"
              )}
            >
              {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              <span className="hidden sm:inline text-[10px] font-bold uppercase tracking-widest">
                {isDarkMode ? 'Sáng' : 'Tối'}
              </span>
            </button>

            <div className="text-right hidden md:block">
              <p className="text-[10px] font-mono text-gray-500 uppercase">Giờ Hệ Thống</p>
              <p className={cn("text-xs font-mono tracking-widest", isDarkMode ? "text-white" : "text-gray-900")}>
                {formatTimeVN(systemClock)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => navigate(PATHS.PROFILE)}
              className={cn(
                'p-2 rounded-lg transition-all min-h-[44px] min-w-[44px] flex items-center justify-center',
                isDarkMode ? 'hover:bg-white/5 text-gray-500 hover:text-white' : 'hover:bg-gray-100 text-gray-500 hover:text-gray-800',
              )}
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Content Area */}
        <div className={cn(
          'flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-4 sm:p-6 lg:p-8 relative transition-colors duration-300 pb-[max(1rem,env(safe-area-inset-bottom))]',
          isDarkMode ? "bg-[#0a0a0b]" : "bg-gray-50"
        )}>
          {/* Background Grid Pattern */}
          <div className={cn(
            "absolute inset-0 opacity-[0.03] pointer-events-none",
              isDarkMode ? "bg-[url('https://grainy-gradients.vercel.app/noise.svg')]" : "bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] bg-size-[16px_16px]"
          )} />
          <div className="relative z-10 mx-auto w-full max-w-[1600px]">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
};

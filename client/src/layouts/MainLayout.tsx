import React, { useEffect } from 'react';
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
  Moon
} from 'lucide-react';
import { cn } from '../utils/cn';

const navItems = [
  { path: PATHS.HOME, label: 'Bảng Điều Khiển', icon: LayoutDashboard },
  { path: '/orders', label: 'Quản Lý Đơn Hàng', icon: ClipboardList },
  { path: '/revenue', label: 'Quản Lý Thu Nhập', icon: Wallet },
  { path: '/vessels', label: 'Mã Tàu', icon: Ship },
  { path: '/port', label: 'Quản Lý Cảng', icon: Anchor },
  { path: '/stats', label: 'Thống Kê', icon: BarChart3 },
  { path: '/backup', label: 'Sao Lưu / Lịch Sử', icon: Database },
];

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { isDarkMode, toggleTheme } = useThemeStore();

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  const handleLogout = () => {
    logout();
    navigate(PATHS.LOGIN);
  };

  return (
    <div className={cn(
      "flex h-screen font-sans selection:bg-blue-500/30 transition-colors duration-300 antialiased",
      isDarkMode ? "bg-[#0a0a0b] text-gray-200" : "bg-gray-50 text-gray-800"
    )}>
      {/* Sidebar */}
      <aside className={cn(
        "w-64 border-r flex flex-col shadow-2xl transition-colors duration-300",
        isDarkMode ? "bg-[#121214] border-white/5" : "bg-white border-gray-200"
      )}>
        <div className={cn(
          "p-6 flex items-center space-x-3 border-b transition-colors duration-300",
          isDarkMode ? "border-white/5" : "border-gray-100"
        )}>
          <div className="p-2 bg-blue-600 rounded-lg">
            <Ship className="w-6 h-6 text-white" />
          </div>
          <span className={cn(
            "font-bold tracking-tighter uppercase text-lg",
            isDarkMode ? "text-white" : "text-gray-900"
          )}>Bason OS</span>
        </div>

        <nav className="flex-1 overflow-y-auto py-6 px-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  "flex items-center space-x-3 px-4 py-3 rounded-lg transition-all duration-200 group",
                  isActive 
                    ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20" 
                    : isDarkMode 
                      ? "hover:bg-white/5 text-gray-400 hover:text-white"
                      : "hover:bg-gray-100 text-gray-500 hover:text-gray-900"
                )}
              >
                <Icon className={cn("w-5 h-5", isActive ? "text-white" : "text-gray-500 group-hover:text-blue-400")} />
                <span className="text-sm font-bold uppercase tracking-wider">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className={cn(
          "p-4 border-t space-y-4 transition-colors duration-300",
          isDarkMode ? "border-white/5" : "border-gray-100"
        )}>
          <div className={cn(
            "flex items-center space-x-3 px-4 py-3 rounded-xl border transition-colors duration-300",
            isDarkMode ? "bg-white/5 border-white/5" : "bg-gray-50 border-gray-100"
          )}>
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-600 to-cyan-400 flex items-center justify-center">
              <User className="w-4 h-4 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className={cn("text-xs font-bold truncate uppercase", isDarkMode ? "text-white" : "text-gray-900")}>
                {user?.name || 'Nhân Viên'}
              </p>
              <p className="text-[10px] text-gray-500 truncate font-mono uppercase">{user?.role || 'Quản Trị'}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center space-x-2 px-4 py-3 text-red-400 hover:bg-red-500/10 rounded-lg transition-all font-bold uppercase text-xs tracking-widest border border-transparent hover:border-red-500/20"
          >
            <LogOut className="w-4 h-4" />
            <span>Đăng Xuất</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className={cn(
          "h-16 border-b flex items-center justify-between px-8 shadow-sm transition-colors duration-300",
          isDarkMode ? "bg-[#121214] border-white/5" : "bg-white border-gray-200"
        )}>
          <div className="flex items-center space-x-4">
            <h2 className={cn("text-sm font-bold uppercase tracking-[0.2em]", isDarkMode ? "text-white" : "text-gray-900")}>
              {navItems.find(i => i.path === location.pathname)?.label || 'Hệ Thống'}
            </h2>
            <div className={cn("h-4 w-px", isDarkMode ? "bg-white/10" : "bg-gray-200")} />
            <div className="flex items-center space-x-2">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              <span className="text-[10px] font-mono text-green-500 uppercase tracking-tighter">AI Core: Đang Hoạt Động</span>
            </div>
          </div>
          
          <div className="flex items-center space-x-6">
            <button 
              onClick={toggleTheme}
              className={cn(
                "p-2 rounded-lg transition-all flex items-center space-x-2 border",
                isDarkMode 
                  ? "bg-white/5 border-white/10 text-yellow-400 hover:bg-white/10" 
                  : "bg-gray-100 border-gray-200 text-gray-600 hover:bg-gray-200"
              )}
            >
              {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
              <span className="text-[10px] font-bold uppercase tracking-widest">
                {isDarkMode ? 'Sáng' : 'Tối'}
              </span>
            </button>

            <div className="text-right hidden sm:block">
              <p className="text-[10px] font-mono text-gray-500 uppercase">Giờ Hệ Thống</p>
              <p className={cn("text-xs font-mono tracking-widest", isDarkMode ? "text-white" : "text-gray-900")}>
                {new Date().toLocaleTimeString([], { hour12: false })}
              </p>
            </div>
            <button className="p-2 hover:bg-white/5 rounded-lg transition-all text-gray-500 hover:text-white">
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* Content Area */}
        <div className={cn(
          "flex-1 overflow-y-auto p-8 relative transition-colors duration-300",
          isDarkMode ? "bg-[#0a0a0b]" : "bg-gray-50"
        )}>
          {/* Background Grid Pattern */}
          <div className={cn(
            "absolute inset-0 opacity-[0.03] pointer-events-none",
            isDarkMode ? "bg-[url('https://grainy-gradients.vercel.app/noise.svg')]" : "bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px]"
          )} />
          <div className="relative z-10">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
};

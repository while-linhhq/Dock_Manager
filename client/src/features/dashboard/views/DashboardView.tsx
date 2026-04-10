import React, { useEffect } from 'react';
import { 
  Activity, 
  Ship, 
  AlertTriangle, 
  Clock, 
  TrendingUp, 
  Anchor,
  Camera,
  Loader2
} from 'lucide-react';
import { cn } from '../../../utils/cn';
import { getDetectionDisplayTimeIso, getDetectionShipLabel } from '../../../utils/detection-display';
import { useDashboardStore } from '../store/dashboardStore';

const StatCard = ({ label, value, icon: Icon, trend, color, isLoading }: any) => (
  <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl hover:border-blue-500/30 transition-all group">
    <div className="flex justify-between items-start mb-4">
      <div className={cn("p-3 rounded-xl", color)}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      {trend !== undefined && (
        <span className={cn(
          "text-[10px] font-bold px-2 py-1 rounded-full uppercase tracking-tighter",
          trend > 0 ? "bg-green-500/10 text-green-500" : "bg-red-500/10 text-red-500"
        )}>
          {trend > 0 ? '+' : ''}{trend}%
        </span>
      )}
    </div>
    <p className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] mb-1">{label}</p>
    {isLoading ? (
      <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
    ) : (
      <h3 className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight">{value}</h3>
    )}
  </div>
);

export const DashboardView: React.FC = () => {
  const { stats, recentDetections, pipelineStatus, isLoading, fetchDashboardData, refreshPipelineStatus } = useDashboardStore();

  useEffect(() => {
    fetchDashboardData();
    const handlePipelineChanged = () => {
      refreshPipelineStatus();
    };
    window.addEventListener('pipeline-status-changed', handlePipelineChanged);
    return () => window.removeEventListener('pipeline-status-changed', handlePipelineChanged);
  }, [fetchDashboardData, refreshPipelineStatus]);

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      {/* Hero Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard 
          label="Tàu Đang Hoạt Động" 
          value={stats?.total_vessels || 0} 
          icon={Ship} 
          color="bg-blue-600 shadow-lg shadow-blue-600/20" 
          isLoading={isLoading}
        />
        <StatCard 
          label="Doanh Thu Ước Tính" 
          value={`${(stats?.total_revenue || 0).toLocaleString('vi-VN')} ₫`} 
          icon={TrendingUp} 
          color="bg-emerald-600 shadow-lg shadow-emerald-600/20" 
          isLoading={isLoading}
        />
        <StatCard 
          label="Đơn Hàng Chờ" 
          value={stats?.pending_orders || 0} 
          icon={Activity} 
          color="bg-amber-600 shadow-lg shadow-amber-600/20" 
          isLoading={isLoading}
        />
        <StatCard 
          label="Camera Hoạt Động" 
          value={stats?.active_cameras || 0} 
          icon={Camera} 
          color="bg-gray-700 shadow-lg shadow-gray-700/20" 
          isLoading={isLoading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Live Monitoring Section */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-gray-200 dark:border-white/5 flex items-center justify-between bg-gray-50 dark:bg-white/[0.02]">
              <div className="flex items-center space-x-2">
                <Camera className="w-4 h-4 text-blue-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-gray-900 dark:text-white">AI Feed Trực Tiếp - Hệ Thống</span>
              </div>
              <div className="flex items-center space-x-3">
                <span className="flex items-center space-x-1">
                  <span className={cn(
                    "w-1.5 h-1.5 rounded-full animate-pulse",
                    pipelineStatus?.is_running ? "bg-red-500" : "bg-gray-500"
                  )} />
                  <span className={cn(
                    "text-[10px] font-mono uppercase",
                    pipelineStatus?.is_running ? "text-red-500" : "text-gray-500"
                  )}>
                    {pipelineStatus?.is_running ? 'Đang Ghi Hình' : 'Dừng'}
                  </span>
                </span>
                <div className="h-3 w-px bg-gray-200 dark:bg-white/10" />
                <span className="text-[10px] font-mono text-gray-500 uppercase">
                  Cache: {pipelineStatus?.ocr_cache_size || 0}
                </span>
              </div>
            </div>
            <div className="aspect-video bg-black relative flex items-center justify-center group cursor-crosshair">
              <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-blue-500/20 via-transparent to-transparent" />
              <Ship className="w-20 h-20 text-white/5 group-hover:text-blue-500/10 transition-colors duration-500" />
              
              {pipelineStatus?.is_running && (
                <div className="absolute top-1/4 left-1/4 w-1/2 h-1/2 border-2 border-blue-500/50 rounded-sm">
                  <div className="absolute -top-6 left-0 bg-blue-500 text-white text-[10px] font-bold px-2 py-0.5 uppercase tracking-tighter rounded-t-sm">
                    Đang quét...
                  </div>
                </div>
              )}

              <div className="absolute bottom-4 right-4 flex space-x-2">
                <div className="px-2 py-1 bg-black/60 backdrop-blur-md border border-white/10 rounded text-[9px] font-mono text-white uppercase tracking-tighter">
                  Hệ thống: {pipelineStatus?.is_running ? 'ONLINE' : 'OFFLINE'}
                </div>
              </div>
            </div>
          </div>

          {/* Recent Activity Table */}
          <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl">
            <div className="p-6 border-b border-gray-200 dark:border-white/5">
              <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">Nhận Diện Tàu Gần Đây</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-[10px] font-bold text-gray-500 uppercase tracking-widest border-b border-gray-200 dark:border-white/5">
                    <th className="px-6 py-4">Thời Gian</th>
                    <th className="px-6 py-4">Mã Tàu</th>
                    <th className="px-6 py-4">Độ Tin Cậy</th>
                    <th className="px-6 py-4">Trạng Thái</th>
                    <th className="px-6 py-4 text-right">Thao Tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-white/5">
                  {recentDetections.length > 0 ? (
                    recentDetections.map((row, i) => (
                      <tr key={row.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors group">
                        <td className="px-6 py-4 text-xs font-mono text-gray-400">
                          {(() => {
                            const iso = getDetectionDisplayTimeIso(row);
                            return iso
                              ? new Date(iso).toLocaleTimeString([], { hour12: false })
                              : '—';
                          })()}
                        </td>
                        <td className="px-6 py-4 text-xs font-bold text-gray-900 dark:text-white">
                          {getDetectionShipLabel(row)}
                        </td>
                        <td className="px-6 py-4 text-xs font-mono text-blue-500">
                          {(((row.confidence ?? 0) as number) * 100).toFixed(1)}%
                        </td>
                        <td className={cn(
                          "px-6 py-4 text-[10px] font-bold uppercase tracking-tighter",
                          row.is_accepted === true ? "text-emerald-500" : "text-amber-500"
                        )}>
                          {row.is_accepted === true ? 'Đã Xác Nhận' : 'Chờ Duyệt'}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button className="text-[10px] font-bold text-blue-600 hover:text-blue-500 uppercase tracking-widest transition-colors">
                            Chi Tiết
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="px-6 py-8 text-center text-gray-500 text-xs uppercase tracking-widest">
                        {isLoading ? 'Đang tải dữ liệu...' : 'Không có dữ liệu nhận diện'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Sidebar Info */}
        <div className="space-y-6">
          <div className="bg-blue-600 rounded-2xl p-6 shadow-2xl shadow-blue-600/20 relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:scale-110 transition-transform duration-500">
              <Anchor className="w-24 h-24 text-white" />
            </div>
            <div className="relative z-10">
              <h4 className="text-white font-bold uppercase tracking-widest text-xs mb-4">Công Suất Cảng</h4>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-[10px] font-bold text-blue-100 uppercase mb-1">
                    <span>Sử Dụng Cầu Cảng</span>
                    <span>72%</span>
                  </div>
                  <div className="h-1.5 w-full bg-blue-800 rounded-full overflow-hidden">
                    <div className="h-full bg-white w-[72%] rounded-full shadow-[0_0_10px_rgba(255,255,255,0.5)]" />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-[10px] font-bold text-blue-100 uppercase mb-1">
                    <span>Bãi Chứa Container</span>
                    <span>45%</span>
                  </div>
                  <div className="h-1.5 w-full bg-blue-800 rounded-full overflow-hidden">
                    <div className="h-full bg-white w-[45%] rounded-full opacity-60" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl p-6 shadow-xl">
            <h4 className="text-gray-900 dark:text-white font-bold uppercase tracking-widest text-xs mb-4 flex items-center">
              <Clock className="w-4 h-4 mr-2 text-blue-500" />
              Dữ Liệu Hệ Thống
            </h4>
            <div className="space-y-4 text-[10px] font-mono uppercase text-gray-500">
              <div className="flex justify-between">
                <span>Detections Today</span>
                <span className="text-blue-500 font-bold">{stats?.detections_today || 0}</span>
              </div>
              <div className="flex justify-between">
                <span>Unpaid Invoices</span>
                <span className="text-amber-500 font-bold">{stats?.unpaid_invoices_count || 0}</span>
              </div>
              <div className="flex justify-between">
                <span>OCR Cache</span>
                <span className="text-emerald-500 font-bold">{pipelineStatus?.ocr_cache_size || 0}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

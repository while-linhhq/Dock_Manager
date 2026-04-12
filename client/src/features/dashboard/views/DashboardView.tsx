import React, { useEffect } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  ClipboardList,
  Coins,
  Loader2,
  ScanSearch,
  Sparkles,
} from 'lucide-react';
import { cn } from '../../../utils/cn';
import { useDashboardStore } from '../store/dashboardStore';
import { DashboardAiFeedPanel } from '../components/DashboardAiFeedPanel';
import { DashboardPeriodToggle } from '../components/DashboardPeriodToggle';
import { DashboardRecentDetectionsSidebar } from '../components/DashboardRecentDetectionsSidebar';
import { DashboardRevenueSidebarCharts } from '../components/DashboardRevenueSidebarCharts';
import type { DashboardPeriod } from '../../../types/api.types';

const PERIOD_SUB: Record<DashboardPeriod, string> = {
  day: 'Kỳ: hôm nay',
  month: 'Kỳ: tháng này',
  year: 'Kỳ: năm nay',
};

function moneyVi(n: number | string | null | undefined): string {
  return `${Number(n ?? 0).toLocaleString('vi-VN')} ₫`;
}

type StatCardProps = {
  label: string;
  value: React.ReactNode;
  icon: LucideIcon;
  color: string;
  isLoading?: boolean;
  subtitle?: string;
  trend?: number;
};

const StatCard = ({ label, value, icon: Icon, trend, color, isLoading, subtitle }: StatCardProps) => (
  <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl hover:border-blue-500/30 transition-all group">
    <div className="flex justify-between items-start mb-4">
      <div className={cn('p-3 rounded-xl', color)}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      {trend !== undefined && (
        <span
          className={cn(
            'text-[10px] font-bold px-2 py-1 rounded-full uppercase tracking-tighter',
            trend > 0 ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500',
          )}
        >
          {trend > 0 ? '+' : ''}
          {trend}%
        </span>
      )}
    </div>
    <p className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] mb-1">{label}</p>
    {subtitle ? (
      <p className="text-[9px] font-mono text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
        {subtitle}
      </p>
    ) : null}
    {isLoading ? (
      <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
    ) : (
      <h3 className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight">{value}</h3>
    )}
  </div>
);

export const DashboardView: React.FC = () => {
  const {
    stats,
    summary,
    summaryPeriod,
    recentDetections,
    pipelineStatus,
    isLoading,
    summaryLoading,
    fetchDashboardData,
    fetchSummary,
    setSummaryPeriod,
    refreshPipelineStatus,
  } = useDashboardStore();

  const cardsLoading = isLoading || summaryLoading;

  useEffect(() => {
    fetchDashboardData();
    const handlePipelineChanged = () => {
      refreshPipelineStatus();
    };
    window.addEventListener('pipeline-status-changed', handlePipelineChanged);
    return () => window.removeEventListener('pipeline-status-changed', handlePipelineChanged);
  }, [fetchDashboardData, refreshPipelineStatus]);

  const periodSubtitle = PERIOD_SUB[summaryPeriod];

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400">
          Thống kê nhanh &amp; top tàu theo kỳ (múi giờ VN)
        </p>
        <DashboardPeriodToggle
          value={summaryPeriod}
          onChange={(p) => {
            setSummaryPeriod(p);
            void fetchSummary(p);
          }}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Tàu / mã nhận diện (distinct)"
          subtitle={periodSubtitle}
          value={summary?.distinct_ships_detected ?? 0}
          icon={ScanSearch}
          color="bg-blue-600 shadow-lg shadow-blue-600/20"
          isLoading={cardsLoading}
        />
        <StatCard
          label="Phí vãn lai (theo giờ)"
          subtitle={periodSubtitle}
          value={moneyVi(summary?.transient_fee_revenue)}
          icon={Coins}
          color="bg-emerald-600 shadow-lg shadow-emerald-600/20"
          isLoading={cardsLoading}
        />
        <StatCard
          label="Hóa đơn tự động (AI)"
          subtitle={periodSubtitle}
          value={summary?.auto_invoices_created ?? 0}
          icon={Sparkles}
          color="bg-violet-600 shadow-lg shadow-violet-600/20"
          isLoading={cardsLoading}
        />
        <StatCard
          label="Đơn hàng chờ"
          subtitle="Trạng thái hiện tại (không theo kỳ)"
          value={stats?.pending_orders ?? 0}
          icon={ClipboardList}
          color="bg-amber-600 shadow-lg shadow-amber-600/20"
          isLoading={isLoading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <DashboardAiFeedPanel
            pipelineStatus={pipelineStatus}
            detections={recentDetections}
            stats={stats}
            summary={summary}
            summaryPeriod={summaryPeriod}
            isLoading={isLoading}
            onRefreshAnalytics={() => void fetchDashboardData()}
          />
        </div>

        <div className="space-y-6">
          <DashboardRevenueSidebarCharts summary={summary} isLoading={summaryLoading} />
          <DashboardRecentDetectionsSidebar
            detections={recentDetections}
            isLoading={isLoading}
          />
        </div>
      </div>
    </div>
  );
};

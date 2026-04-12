import React, { useEffect, useMemo, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  ClipboardList,
  Coins,
  Loader2,
  ScanSearch,
  Sparkles,
} from 'lucide-react';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import { getDetectionDisplayTimeIso, getDetectionShipLabel } from '../../../utils/detection-display';
import { useDashboardStore } from '../store/dashboardStore';
import { DashboardAiFeedPanel } from '../components/DashboardAiFeedPanel';
import { DashboardPeriodToggle } from '../components/DashboardPeriodToggle';
import { DashboardRevenueSidebarCharts } from '../components/DashboardRevenueSidebarCharts';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
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
  const [dashDetQ, setDashDetQ] = useState('');
  const [dashDetAccepted, setDashDetAccepted] = useState<'all' | 'yes' | 'no'>('all');
  const [dashDetFrom, setDashDetFrom] = useState('');
  const [dashDetTo, setDashDetTo] = useState('');

  const cardsLoading = isLoading || summaryLoading;

  useEffect(() => {
    fetchDashboardData();
    const handlePipelineChanged = () => {
      refreshPipelineStatus();
    };
    window.addEventListener('pipeline-status-changed', handlePipelineChanged);
    return () => window.removeEventListener('pipeline-status-changed', handlePipelineChanged);
  }, [fetchDashboardData, refreshPipelineStatus]);

  const filteredRecentDetections = useMemo(() => {
    return recentDetections.filter((row) => {
      const label = getDetectionShipLabel(row);
      const iso = getDetectionDisplayTimeIso(row);
      if (
        !matchesAnyField(
          dashDetQ,
          label,
          row.track_id,
          String(row.vessel_id ?? ''),
          row.vessel?.ship_id,
        )
      ) {
        return false;
      }
      if (dashDetAccepted === 'yes' && row.is_accepted !== true) {
        return false;
      }
      if (dashDetAccepted === 'no' && row.is_accepted === true) {
        return false;
      }
      if (!isoInLocalDateRange(iso ?? row.created_at, dashDetFrom, dashDetTo)) {
        return false;
      }
      return true;
    });
  }, [recentDetections, dashDetQ, dashDetAccepted, dashDetFrom, dashDetTo]);

  const dashDetFilterCount =
    (dashDetQ.trim() ? 1 : 0) +
    (dashDetAccepted !== 'all' ? 1 : 0) +
    (dashDetFrom ? 1 : 0) +
    (dashDetTo ? 1 : 0);

  const resetDashDetFilters = () => {
    setDashDetQ('');
    setDashDetAccepted('all');
    setDashDetFrom('');
    setDashDetTo('');
  };

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

          <div className="space-y-4">
            <TableFilterPanel
              title="Bộ lọc nhận diện gần đây"
              onReset={resetDashDetFilters}
              activeCount={dashDetFilterCount}
            >
              <FilterField label="Từ khóa (mã tàu / track)">
                <input
                  type="text"
                  value={dashDetQ}
                  onChange={(e) => setDashDetQ(e.target.value)}
                  placeholder="Lọc trên dữ liệu đã tải..."
                  className={filterControlClass}
                />
              </FilterField>
              <FilterField label="Trạng thái duyệt">
                <select
                  value={dashDetAccepted}
                  onChange={(e) =>
                    setDashDetAccepted(e.target.value as 'all' | 'yes' | 'no')
                  }
                  className={filterControlClass}
                >
                  <option value="all">Tất cả</option>
                  <option value="yes">Đã xác nhận</option>
                  <option value="no">Chờ duyệt</option>
                </select>
              </FilterField>
              <FilterField label="Từ ngày">
                <input
                  type="date"
                  value={dashDetFrom}
                  onChange={(e) => setDashDetFrom(e.target.value)}
                  className={filterControlClass}
                />
              </FilterField>
              <FilterField label="Đến ngày">
                <input
                  type="date"
                  value={dashDetTo}
                  onChange={(e) => setDashDetTo(e.target.value)}
                  className={filterControlClass}
                />
              </FilterField>
            </TableFilterPanel>

            <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl">
              <div className="p-6 border-b border-gray-200 dark:border-white/5 flex flex-wrap justify-between gap-2">
                <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
                  Nhận Diện Tàu Gần Đây
                </h3>
                <span className="text-xs sm:text-sm font-mono text-gray-500 dark:text-gray-400 uppercase">
                  {filteredRecentDetections.length}/{recentDetections.length} dòng
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className={dt.headRow}>
                      <th className={dt.pad}>Thời Gian</th>
                      <th className={dt.pad}>Mã Tàu</th>
                      <th className={dt.pad}>Độ Tin Cậy</th>
                      <th className={dt.pad}>Trạng Thái</th>
                      <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-white/5">
                    {filteredRecentDetections.length > 0 ? (
                      filteredRecentDetections.map((row) => (
                        <tr
                          key={row.id}
                          className="hover:bg-gray-50 dark:hover:bg-white/2 transition-colors group"
                        >
                          <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                            {(() => {
                              const iso = getDetectionDisplayTimeIso(row);
                              return iso
                                ? new Date(iso).toLocaleTimeString([], { hour12: false })
                                : '—';
                            })()}
                          </td>
                          <td className={cn(dt.pad, dt.body, 'font-bold')}>
                            {getDetectionShipLabel(row)}
                          </td>
                          <td className={cn(dt.pad, dt.mono, 'text-blue-600 dark:text-blue-400')}>
                            {(((row.confidence ?? 0) as number) * 100).toFixed(1)}%
                          </td>
                          <td
                            className={cn(
                              dt.pad,
                              'text-sm font-bold uppercase tracking-tight',
                              row.is_accepted === true
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-amber-600 dark:text-amber-400',
                            )}
                          >
                            {row.is_accepted === true ? 'Đã Xác Nhận' : 'Chờ Duyệt'}
                          </td>
                          <td className={cn(dt.pad, 'text-right')}>
                            <button
                              type="button"
                              className={cn(
                                dt.action,
                                'text-blue-600 hover:text-blue-500 dark:text-blue-400 transition-colors',
                              )}
                            >
                              Chi Tiết
                            </button>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td
                          colSpan={5}
                          className={cn(dt.pad, 'py-8 text-center uppercase tracking-wide', dt.empty)}
                        >
                          {isLoading
                            ? 'Đang tải dữ liệu...'
                            : recentDetections.length === 0
                              ? 'Không có dữ liệu nhận diện'
                              : 'Không có dòng khớp bộ lọc'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <DashboardRevenueSidebarCharts summary={summary} isLoading={summaryLoading} />
        </div>
      </div>
    </div>
  );
};

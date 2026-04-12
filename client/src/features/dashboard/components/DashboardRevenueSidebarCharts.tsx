import React, { useMemo } from 'react';
import ReactApexChart from 'react-apexcharts';
import type { ApexOptions } from 'apexcharts';
import { TrendingUp } from 'lucide-react';
import type { DashboardPeriod, DashboardSummary } from '../../../types/api.types';
import { cn } from '../../../utils/cn';
import { useHtmlDarkClass } from '../hooks/use-html-dark-class';

function apexCommon(isDark: boolean): Partial<ApexOptions> {
  return {
    chart: {
      toolbar: { show: false },
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      foreColor: isDark ? '#9ca3af' : '#6b7280',
      background: 'transparent',
      stacked: true,
    },
    theme: { mode: isDark ? 'dark' : 'light' },
    grid: {
      borderColor: isDark ? 'rgba(255,255,255,0.08)' : '#e5e7eb',
      strokeDashArray: 4,
    },
    legend: {
      fontSize: '11px',
      position: 'top',
      horizontalAlign: 'left',
      labels: { colors: isDark ? '#d1d5db' : '#374151' },
    },
    dataLabels: { enabled: false },
    plotOptions: { bar: { borderRadius: 3, columnWidth: '72%' } },
  };
}

function periodChartTitle(period: DashboardPeriod): string {
  if (period === 'day') {
    return 'Thu nhập theo giờ (HĐ trong ngày)';
  }
  if (period === 'month') {
    return 'Thu nhập theo ngày trong tháng';
  }
  return 'Thu nhập theo tháng trong năm';
}

export type DashboardRevenueSidebarChartsProps = {
  summary: DashboardSummary | null;
  isLoading: boolean;
};

export const DashboardRevenueSidebarCharts: React.FC<DashboardRevenueSidebarChartsProps> = ({
  summary,
  isLoading,
}) => {
  const isDark = useHtmlDarkClass();
  const base = useMemo(() => apexCommon(isDark), [isDark]);

  const options: ApexOptions = useMemo(() => {
    const labels = summary?.revenue_chart_labels ?? [];
    return {
      ...base,
      chart: { ...base.chart, type: 'bar', stacked: true },
      colors: ['#6366f1', '#10b981'],
      xaxis: {
        categories: labels,
        labels: {
          rotate: labels.length > 14 ? -45 : 0,
          rotateAlways: labels.length > 14,
        },
      },
      yaxis: {
        labels: {
          formatter: (v) =>
            `${Number(v).toLocaleString('vi-VN', { maximumFractionDigits: 0 })} ₫`,
        },
      },
      tooltip: {
        y: {
          formatter: (v) => `${Number(v).toLocaleString('vi-VN')} ₫`,
        },
      },
    };
  }, [base, summary?.revenue_chart_labels]);

  const series = useMemo(() => {
    if (!summary) {
      return [
        { name: 'Thủ công / đơn hàng', data: [] as number[] },
        { name: 'Tự động (AI)', data: [] as number[] },
      ];
    }
    return [
      { name: 'Thủ công / đơn hàng', data: summary.revenue_chart_manual },
      { name: 'Tự động (AI)', data: summary.revenue_chart_ai },
    ];
  }, [summary]);

  const totalInPeriod = useMemo(() => {
    if (!summary?.revenue_chart_totals?.length) {
      return 0;
    }
    return summary.revenue_chart_totals.reduce((a, b) => a + b, 0);
  }, [summary]);

  return (
    <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl p-5 shadow-xl space-y-4">
      <div className="flex items-start gap-2">
        <TrendingUp className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
        <div>
          <h4 className="text-gray-900 dark:text-white font-bold uppercase tracking-widest text-xs">
            Phân tích thu nhập
          </h4>
          <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">
            {summary ? periodChartTitle(summary.period) : 'Chọn kỳ (ngày / tháng / năm) ở trên.'} Tổng
            hóa đơn (chưa xóa) theo mốc tạo HĐ, chia AI và thủ công/đơn hàng.
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50/80 dark:bg-white/2 px-2 pt-2 pb-1">
        <p className="text-[10px] font-mono uppercase text-gray-500 px-2 mb-2">
          Tổng kỳ:{' '}
          <span className="text-emerald-600 dark:text-emerald-400 font-bold">
            {isLoading
              ? '…'
              : `${totalInPeriod.toLocaleString('vi-VN', { maximumFractionDigits: 0 })} ₫`}
          </span>
        </p>
        {summary && summary.revenue_chart_labels.length > 0 ? (
          <ReactApexChart options={options} series={series} type="bar" height={320} />
        ) : (
          <p className="py-16 text-center text-xs font-mono uppercase tracking-wide text-gray-500">
            {isLoading ? 'Đang tải…' : 'Chưa có dữ liệu hóa đơn trong kỳ'}
          </p>
        )}
      </div>
    </div>
  );
};

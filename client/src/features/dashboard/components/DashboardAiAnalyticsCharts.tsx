import React, { useMemo } from 'react';
import ReactApexChart from 'react-apexcharts';
import type { ApexOptions } from 'apexcharts';
import { BarChart3, RefreshCw } from 'lucide-react';
import type {
  DashboardPeriod,
  DashboardStats,
  DashboardSummary,
  DetectionRead,
} from '../../../types/api.types';
import { cn } from '../../../utils/cn';
import { Button } from '../../../components/Button/Button';
import { useHtmlDarkClass } from '../hooks/use-html-dark-class';
import {
  buildAcceptanceSplit,
  buildConfidenceBuckets,
  buildDetectionsByHourLast24h,
  buildTopShipCounts,
  formatStatsSummary,
} from '../utils/dashboard-analytics-data';

function apexCommon(isDark: boolean): Partial<ApexOptions> {
  return {
    chart: {
      toolbar: { show: false },
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      foreColor: isDark ? '#9ca3af' : '#6b7280',
      background: 'transparent',
      zoom: { enabled: false },
    },
    theme: { mode: isDark ? 'dark' : 'light' },
    grid: {
      borderColor: isDark ? 'rgba(255,255,255,0.08)' : '#e5e7eb',
      strokeDashArray: 4,
    },
    legend: {
      fontSize: '11px',
      labels: { colors: isDark ? '#d1d5db' : '#374151' },
    },
    dataLabels: { enabled: false },
  };
}

function periodLabelVi(p: DashboardPeriod | undefined): string {
  if (p === 'month') {
    return 'tháng này';
  }
  if (p === 'year') {
    return 'năm nay';
  }
  return 'hôm nay';
}

function detectionVolumeChartTitle(p: DashboardPeriod): string {
  if (p === 'month') {
    return 'Lượt nhận diện theo ngày trong tháng';
  }
  if (p === 'year') {
    return 'Lượt nhận diện theo tháng trong năm';
  }
  return 'Lượt nhận diện theo giờ trong ngày';
}

export type DashboardAiAnalyticsChartsProps = {
  detections: DetectionRead[];
  stats: DashboardStats | null;
  summary: DashboardSummary | null;
  summaryPeriod: DashboardPeriod;
  isLoading: boolean;
  onRefresh: () => void;
};

export const DashboardAiAnalyticsCharts: React.FC<DashboardAiAnalyticsChartsProps> = ({
  detections,
  stats,
  summary,
  summaryPeriod,
  isLoading,
  onRefresh,
}) => {
  const isDark = useHtmlDarkClass();
  const base = useMemo(() => apexCommon(isDark), [isDark]);

  const volumeSeries = useMemo(() => {
    const labels = summary?.detection_volume_labels;
    const counts = summary?.detection_volume_counts;
    if (
      labels &&
      labels.length > 0 &&
      counts &&
      counts.length === labels.length
    ) {
      return {
        categories: labels,
        data: counts.map((n) => Number(n)),
        fromSummary: true as const,
      };
    }
    const fb = buildDetectionsByHourLast24h(detections);
    return { ...fb, fromSummary: false as const };
  }, [summary, detections]);
  const topShips = useMemo(() => {
    const summaryShipLabels = summary?.top_ship_labels;
    const summaryShipCounts = summary?.top_ship_counts;
    if (
      summaryShipLabels?.length &&
      summaryShipCounts &&
      summaryShipCounts.length === summaryShipLabels.length
    ) {
      return { labels: summaryShipLabels, counts: summaryShipCounts };
    }
    return buildTopShipCounts(detections, 8);
  }, [summary, detections]);
  const acceptance = useMemo(() => {
    if (
      summary &&
      typeof summary.detections_review_accepted === 'number' &&
      typeof summary.detections_review_not_accepted === 'number' &&
      typeof summary.detections_review_unassigned === 'number'
    ) {
      return {
        labels: ['Đã xác nhận', 'Chưa xác nhận', 'Chưa gán'] as const,
        series: [
          summary.detections_review_accepted,
          summary.detections_review_not_accepted,
          summary.detections_review_unassigned,
        ],
      };
    }
    return buildAcceptanceSplit(detections);
  }, [summary, detections]);
  const acceptanceTotal = useMemo(
    () => acceptance.series.reduce((a, b) => a + b, 0),
    [acceptance.series],
  );
  const confidence = useMemo(() => buildConfidenceBuckets(detections), [detections]);
  const kpi = useMemo(() => formatStatsSummary(stats), [stats]);

  const areaOptions: ApexOptions = useMemo(() => {
    const many = volumeSeries.categories.length > 14;
    return {
      ...base,
      chart: { ...base.chart, type: 'area', sparkline: { enabled: false } },
      stroke: { curve: 'smooth', width: 2 },
      fill: {
        type: 'gradient',
        gradient: {
          shadeIntensity: 1,
          opacityFrom: 0.35,
          opacityTo: 0.05,
          stops: [0, 90, 100],
        },
      },
      colors: ['#2563eb'],
      xaxis: {
        categories: volumeSeries.categories,
        labels: { rotate: many ? -45 : 0, rotateAlways: many },
      },
      yaxis: { min: 0, tickAmount: 4, labels: { formatter: (v) => String(Math.round(Number(v))) } },
      tooltip: { y: { formatter: (v) => `${v} lượt` } },
    };
  }, [base, volumeSeries.categories]);

  const donutOptions: ApexOptions = useMemo(
    () => ({
      ...base,
      chart: { ...base.chart, type: 'donut' },
      labels: [...acceptance.labels],
      colors: ['#059669', '#d97706', '#6b7280'],
      plotOptions: {
        pie: {
          donut: {
            size: '62%',
            labels: {
              show: true,
              total: {
                show: true,
                label: 'Tổng',
                formatter: () => String(acceptanceTotal),
              },
            },
          },
        },
      },
      tooltip: { y: { formatter: (v) => `${v} dòng` } },
    }),
    [base, acceptance.labels, acceptanceTotal],
  );

  const barShipOptions: ApexOptions = useMemo(
    () => ({
      ...base,
      chart: { ...base.chart, type: 'bar' },
      plotOptions: {
        bar: {
          horizontal: true,
          borderRadius: 4,
          barHeight: '72%',
          dataLabels: { position: 'right' },
        },
      },
      colors: ['#7c3aed'],
      xaxis: {
        categories: topShips.labels,
        labels: { formatter: (v) => String(Math.round(Number(v))) },
      },
      tooltip: { y: { formatter: (v) => `${v} lần` } },
    }),
    [base, topShips.labels],
  );

  const columnConfOptions: ApexOptions = useMemo(
    () => ({
      ...base,
      chart: { ...base.chart, type: 'bar' },
      plotOptions: { bar: { columnWidth: '55%', borderRadius: 4 } },
      colors: ['#0ea5e9'],
      xaxis: { categories: confidence.labels },
      yaxis: { min: 0, tickAmount: 4, labels: { formatter: (v) => String(Math.round(Number(v))) } },
      tooltip: { y: { formatter: (v) => `${v} dòng` } },
    }),
    [base, confidence.labels],
  );

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-blue-500" />
          <div>
            <h3 className="text-xs font-bold uppercase tracking-widest text-gray-900 dark:text-white">
              Phân tích dữ liệu nhận diện
            </h3>
            <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5 max-w-xl">
              Biểu đồ lượt nhận diện, trạng thái duyệt và top tàu theo kỳ{' '}
              <span className="font-semibold">{periodLabelVi(summaryPeriod)}</span> (múi giờ VN). Phân bố độ tin cậy
              vẫn theo tối đa 120 dòng đã tải. Tab «Xem trực tiếp» — luồng camera.
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          className="shrink-0 text-[10px] font-bold uppercase tracking-widest"
          onClick={() => void onRefresh()}
          disabled={isLoading}
        >
          <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', isLoading && 'animate-spin')} />
          Làm mới
        </Button>
      </div>

      {kpi.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {kpi.map((row) => (
            <div
              key={row.k}
              className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/[0.03] px-3 py-2"
            >
              <p className="text-[9px] font-bold uppercase tracking-wider text-gray-500">{row.k}</p>
              <p className="text-sm font-mono font-bold text-gray-900 dark:text-white">{row.v}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="lg:col-span-2 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50/80 dark:bg-white/[0.02] p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-0.5 px-1">
            {detectionVolumeChartTitle(summaryPeriod)}
          </p>
          <p className="text-[9px] text-gray-500 dark:text-gray-400 px-1 mb-2 leading-snug">
            Kỳ: {periodLabelVi(summaryPeriod)}
            {!volumeSeries.fromSummary ? ' — đang dùng mẫu 24h gần nhất (API summary chưa có chuỗi khối lượng).' : ''}
          </p>
          <ReactApexChart
            options={areaOptions}
            series={[{ name: 'Lượt nhận diện', data: volumeSeries.data }]}
            type="area"
            height={280}
          />
        </div>

        <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50/80 dark:bg-white/[0.02] p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-0.5 px-1">
            Trạng thái duyệt (kỳ: {periodLabelVi(summaryPeriod)})
          </p>
          <p className="text-[9px] text-gray-500 dark:text-gray-400 px-1 mb-2 leading-snug">
            Đếm theo cùng kỳ ngày / tháng / năm đã chọn phía trên dashboard (Asia/Ho_Chi_Minh).
          </p>
          <ReactApexChart options={donutOptions} series={acceptance.series} type="donut" height={300} />
        </div>

        <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50/80 dark:bg-white/[0.02] p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-0.5 px-1">
            Mã tàu xuất hiện nhiều (top 8 — theo {periodLabelVi(summaryPeriod)})
          </p>
          <p className="text-[9px] text-gray-500 dark:text-gray-400 px-1 mb-2 leading-snug">
            Xếp hạng theo kỳ (ngày / tháng / năm) đã chọn trên dashboard; các biểu đồ khác vẫn dựa trên tối đa
            120 dòng nhận diện đã tải.
          </p>
          {topShips.labels.length === 0 ? (
            <p className="py-16 text-center text-xs font-mono uppercase tracking-wide text-gray-500">
              Chưa có dữ liệu để xếp hạng
            </p>
          ) : (
            <ReactApexChart
              options={barShipOptions}
              series={[{ name: 'Số lần', data: topShips.counts }]}
              type="bar"
              height={Math.max(280, 36 * topShips.labels.length + 80)}
            />
          )}
        </div>

        <div className="lg:col-span-2 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50/80 dark:bg-white/[0.02] p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-1 px-1">
            Phân bố độ tin cậy (confidence)
          </p>
          <ReactApexChart
            options={columnConfOptions}
            series={[{ name: 'Số dòng', data: confidence.series }]}
            type="bar"
            height={240}
          />
        </div>
      </div>
    </div>
  );
};

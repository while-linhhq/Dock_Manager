import { create } from 'zustand';
import type {
  DashboardDetectionAnalytics,
  DashboardPeriod,
  DashboardStats,
  DashboardSummary,
  DetectionRead,
} from '../../../types/api.types';
import { dashboardApi, DASHBOARD_DETECTIONS_LIMIT } from '../services/dashboardApi';
import type { PipelineStatus } from '../services/dashboardApi';

interface DashboardState {
  stats: DashboardStats | null;
  summary: DashboardSummary | null;
  summaryPeriod: DashboardPeriod;
  /**
   * Số tổng hợp của bốn widget phân tích (`GET /dashboard/detection-analytics`).
   * Là nguồn DUY NHẤT của bốn biểu đồ — chúng không còn đếm trên `recentDetections`.
   */
  analytics: DashboardDetectionAnalytics | null;
  recentDetections: DetectionRead[];
  pipelineStatus: PipelineStatus | null;
  isLoading: boolean;
  summaryLoading: boolean;
  error: string | null;
  setSummaryPeriod: (p: DashboardPeriod) => void;
  fetchDashboardData: () => Promise<void>;
  fetchSummary: (period?: DashboardPeriod) => Promise<void>;
  refreshPipelineStatus: () => Promise<void>;
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  stats: null,
  summary: null,
  summaryPeriod: 'day',
  analytics: null,
  recentDetections: [],
  pipelineStatus: null,
  isLoading: false,
  summaryLoading: false,
  error: null,

  setSummaryPeriod: (summaryPeriod) => {
    set({ summaryPeriod });
  },

  fetchSummary: async (period) => {
    const p = period ?? get().summaryPeriod;
    set({ summaryLoading: true, summaryPeriod: p });
    try {
      // Đổi kỳ thì cả `summary` lẫn số của bốn widget phân tích phải đổi theo —
      // hai nguồn này dùng chung một `period` nên không được lệch kỳ nhau.
      const [summary, analytics] = await Promise.all([
        dashboardApi.getSummary(p),
        dashboardApi.getDetectionAnalytics(p),
      ]);
      set({ summary, analytics, summaryLoading: false });
    } catch (err: any) {
      set({
        error: err.message || 'Failed to fetch summary',
        summary: null,
        analytics: null,
        summaryLoading: false,
      });
    }
  },

  fetchDashboardData: async () => {
    set({ isLoading: true, summaryLoading: true, error: null });
    const period = get().summaryPeriod;
    const pipelinePromise = dashboardApi
      .getPipelineStatus()
      .catch((): PipelineStatus | null => null);

    try {
      const [stats, summary, analytics, recentDetections, pipelineStatus] = await Promise.all([
        dashboardApi.getStats(),
        dashboardApi.getSummary(period),
        // Bốn widget phân tích đọc số ở đây, KHÔNG đếm trên `recentDetections` nữa
        // — nhờ vậy sidebar chỉ cần đúng 18 dòng nó hiển thị.
        dashboardApi.getDetectionAnalytics(period),
        dashboardApi
          .getRecentDetections(DASHBOARD_DETECTIONS_LIMIT)
          .catch(() => [] as DetectionRead[]),
        pipelinePromise,
      ]);
      set({
        stats,
        summary,
        summaryPeriod: period,
        analytics,
        recentDetections,
        pipelineStatus,
        isLoading: false,
        summaryLoading: false,
      });
    } catch (err: any) {
      const pipelineStatus = await pipelinePromise;
      set({
        error: err.message || 'Failed to fetch dashboard data',
        pipelineStatus,
        isLoading: false,
        summaryLoading: false,
      });
    }
  },
  refreshPipelineStatus: async () => {
    try {
      const pipelineStatus = await dashboardApi.getPipelineStatus();
      set({ pipelineStatus });
    } catch (err) {
      // Silent error for background refresh
    }
  },
}));

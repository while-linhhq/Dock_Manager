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
  /** Lỗi riêng của `GET /dashboard/detection-analytics` (khác `error` của phần còn lại). */
  analyticsError: string | null;
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

/**
 * Nạp số liệu của bốn widget phân tích, KHÔNG bao giờ reject.
 *
 * Endpoint này không được nằm trần trong `Promise.all`: một lần lỗi ở đây sẽ kéo
 * `summary` (thẻ KPI + biểu đồ vượt line) xuống theo và bốn biểu đồ lặng lẽ vẽ số 0.
 *
 * Quy tắc thống nhất cho CẢ HAI đường tải (`fetchSummary` khi đổi kỳ và
 * `fetchDashboardData` khi làm mới): lỗi thì xoá `analytics` và ghi `analyticsError`,
 * KHÔNG giữ số của kỳ trước — bốn widget luôn được dán nhãn theo `summaryPeriod`
 * hiện tại nên số cũ sẽ bị gán sai kỳ.
 */
function loadAnalytics(period: DashboardPeriod): Promise<{
  analytics: DashboardDetectionAnalytics | null;
  analyticsError: string | null;
}> {
  return dashboardApi
    .getDetectionAnalytics(period)
    .then((analytics) => ({ analytics, analyticsError: null }))
    .catch((err: unknown) => ({
      analytics: null,
      analyticsError:
        err instanceof Error ? err.message : 'Không tải được số liệu phân tích nhận diện',
    }));
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  stats: null,
  summary: null,
  summaryPeriod: 'day',
  analytics: null,
  analyticsError: null,
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
    // Đổi kỳ thì cả `summary` lẫn số của bốn widget phân tích phải đổi theo —
    // hai nguồn này dùng chung một `period` nên không được lệch kỳ nhau.
    // Hai request vẫn chạy song song, nhưng analytics có `catch` riêng nên lỗi của
    // nó không xoá `summary`.
    const analyticsPromise = loadAnalytics(p);
    try {
      const summary = await dashboardApi.getSummary(p);
      const analyticsOutcome = await analyticsPromise;
      set({ summary, ...analyticsOutcome, summaryLoading: false, error: null });
    } catch (err: any) {
      const analyticsOutcome = await analyticsPromise;
      set({
        error: err.message || 'Failed to fetch summary',
        summary: null,
        ...analyticsOutcome,
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
    // Bốn widget phân tích đọc số ở đây, KHÔNG đếm trên `recentDetections` nữa
    // — nhờ vậy sidebar chỉ cần đúng 18 dòng nó hiển thị.
    const analyticsPromise = loadAnalytics(period);

    try {
      const [stats, summary, recentDetections, pipelineStatus] = await Promise.all([
        dashboardApi.getStats(),
        dashboardApi.getSummary(period),
        dashboardApi
          .getRecentDetections(DASHBOARD_DETECTIONS_LIMIT)
          .catch(() => [] as DetectionRead[]),
        pipelinePromise,
      ]);
      const analyticsOutcome = await analyticsPromise;
      set({
        stats,
        summary,
        summaryPeriod: period,
        ...analyticsOutcome,
        recentDetections,
        pipelineStatus,
        isLoading: false,
        summaryLoading: false,
      });
    } catch (err: any) {
      const [pipelineStatus, analyticsOutcome] = await Promise.all([
        pipelinePromise,
        analyticsPromise,
      ]);
      set({
        error: err.message || 'Failed to fetch dashboard data',
        pipelineStatus,
        ...analyticsOutcome,
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

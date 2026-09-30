import { create } from 'zustand';
import { statisticsApi, type OutsideHoursSummaryRow } from '../services/statisticsApi';

interface StatisticsState {
  /** Số lượt neo ngoài giờ theo mã tàu · ngày; bảng log do `usePagedQuery` giữ. */
  outsideSummary: OutsideHoursSummaryRow[];
  isLoading: boolean;
  error: string | null;
  fetchOutsideSummary: (dateFrom?: string, dateTo?: string, shipId?: string) => Promise<void>;
  exportLogs: (logDate?: string, shipId?: string) => Promise<void>;
}

export const useStatisticsStore = create<StatisticsState>((set) => ({
  outsideSummary: [],
  isLoading: false,
  error: null,
  fetchOutsideSummary: async (dateFrom, dateTo, shipId) => {
    try {
      const outsideSummary = await statisticsApi.getOutsideHoursSummary(dateFrom, dateTo, shipId);
      set({ outsideSummary });
    } catch (err: any) {
      // Không chặn bảng log nếu summary lỗi — chỉ log.
      console.error('fetchOutsideSummary failed:', err?.message || err);
      set({ outsideSummary: [] });
    }
  },
  exportLogs: async (logDate, shipId) => {
    set({ isLoading: true });
    try {
      const blob = await statisticsApi.exportExcel(logDate, shipId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `port-logs-${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      set({ isLoading: false });
    } catch (err: unknown) {
      set({
        error: err instanceof Error ? err.message : 'Failed to export logs',
        isLoading: false,
      });
    }
  }
}));

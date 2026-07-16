import { create } from 'zustand';
import type { PortLogRead } from '../../../types/api.types';
import { statisticsApi, type OutsideHoursSummaryRow } from '../services/statisticsApi';

interface StatisticsState {
  logs: PortLogRead[];
  outsideSummary: OutsideHoursSummaryRow[];
  isLoading: boolean;
  error: string | null;
  fetchLogs: (skip?: number, limit?: number, shipId?: string, logDate?: string) => Promise<void>;
  fetchOutsideSummary: (dateFrom?: string, dateTo?: string, shipId?: string) => Promise<void>;
  exportLogs: (logDate?: string, shipId?: string) => Promise<void>;
}

export const useStatisticsStore = create<StatisticsState>((set) => ({
  logs: [],
  outsideSummary: [],
  isLoading: false,
  error: null,
  fetchLogs: async (skip, limit, shipId, logDate) => {
    set({ isLoading: true, error: null });
    try {
      const logs = await statisticsApi.getPortLogs(skip, limit, shipId, logDate);
      set({ logs, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch logs', isLoading: false });
    }
  },
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

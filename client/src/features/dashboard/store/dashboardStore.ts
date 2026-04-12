import { create } from 'zustand';
import type {
  DashboardPeriod,
  DashboardStats,
  DashboardSummary,
  DetectionRead,
} from '../../../types/api.types';
import { dashboardApi } from '../services/dashboardApi';
import type { PipelineStatus } from '../services/dashboardApi';

interface DashboardState {
  stats: DashboardStats | null;
  summary: DashboardSummary | null;
  summaryPeriod: DashboardPeriod;
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
      const summary = await dashboardApi.getSummary(p);
      set({ summary, summaryLoading: false });
    } catch (err: any) {
      set({
        error: err.message || 'Failed to fetch summary',
        summary: null,
        summaryLoading: false,
      });
    }
  },

  fetchDashboardData: async () => {
    set({ isLoading: true, summaryLoading: true, error: null });
    try {
      const period = get().summaryPeriod;
      const [stats, summary, recentDetections, pipelineStatus] = await Promise.all([
        dashboardApi.getStats(),
        dashboardApi.getSummary(period),
        dashboardApi.getRecentDetections(120),
        dashboardApi.getPipelineStatus(),
      ]);
      set({
        stats,
        summary,
        summaryPeriod: period,
        recentDetections,
        pipelineStatus,
        isLoading: false,
        summaryLoading: false,
      });
    } catch (err: any) {
      set({
        error: err.message || 'Failed to fetch dashboard data',
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

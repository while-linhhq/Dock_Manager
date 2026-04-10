import { create } from 'zustand';
import type { DashboardStats, DetectionRead } from '../../../types/api.types';
import { dashboardApi } from '../services/dashboardApi';
import type { PipelineStatus } from '../services/dashboardApi';

interface DashboardState {
  stats: DashboardStats | null;
  recentDetections: DetectionRead[];
  pipelineStatus: PipelineStatus | null;
  isLoading: boolean;
  error: string | null;
  fetchDashboardData: () => Promise<void>;
  refreshPipelineStatus: () => Promise<void>;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  stats: null,
  recentDetections: [],
  pipelineStatus: null,
  isLoading: false,
  error: null,
  fetchDashboardData: async () => {
    set({ isLoading: true, error: null });
    try {
      const [stats, recentDetections, pipelineStatus] = await Promise.all([
        dashboardApi.getStats(),
        dashboardApi.getRecentDetections(),
        dashboardApi.getPipelineStatus(),
      ]);
      set({ stats, recentDetections, pipelineStatus, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch dashboard data', isLoading: false });
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

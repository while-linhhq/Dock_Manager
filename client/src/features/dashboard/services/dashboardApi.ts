import { httpClient } from '../../../services/httpClient';
import type {
  DashboardPeriod,
  DashboardStats,
  DashboardSummary,
  DetectionRead,
} from '../../../types/api.types';

export type PipelineStatus = {
  is_running: boolean;
  ocr_cache_size: number;
};

export const dashboardApi = {
  getSummary: async (period: DashboardPeriod = 'day'): Promise<DashboardSummary> => {
    return httpClient.get<DashboardSummary>(`/dashboard/summary?period=${period}`);
  },
  getStats: async (): Promise<DashboardStats> => {
    return httpClient.get<DashboardStats>('/dashboard/stats');
  },
  getRecentDetections: async (limit: number = 5): Promise<DetectionRead[]> => {
    return httpClient.get<DetectionRead[]>(`/detections/?limit=${limit}`);
  },
  getPipelineStatus: async (): Promise<PipelineStatus> => {
    return httpClient.get<PipelineStatus>('/pipeline/status');
  },
};

import { httpClient } from '../../../services/httpClient';
import type { DashboardStats, DetectionRead } from '../../../types/api.types';

export type PipelineStatus = {
  is_running: boolean;
  ocr_cache_size: number;
}

export const dashboardApi = {
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

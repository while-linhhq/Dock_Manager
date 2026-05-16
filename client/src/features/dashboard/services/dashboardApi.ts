import { httpClient } from '../../../services/httpClient';
import type {
  DashboardPeriod,
  DashboardSystemOverview,
  DashboardStats,
  DashboardSummary,
  DetectionRead,
} from '../../../types/api.types';

export type GpuRuntimeStatus = {
  nvidia_smi?: boolean;
  torch_cuda_available?: boolean;
  paddle_cuda_count?: number;
  paddle_gpu_ok?: boolean;
  recommended_ocr_device?: string;
  device_label?: string | null;
  torch_device?: string | null;
  vram_used_mib?: string;
  vram_total_mib?: string;
  errors?: string[];
};

export type PipelineStatus = {
  is_running: boolean;
  ocr_cache_size: number;
  active_group_id?: number | null;
  seam_anchor_active?: boolean;
  gpu?: GpuRuntimeStatus;
};

export const dashboardApi = {
  getSummary: async (period: DashboardPeriod = 'day'): Promise<DashboardSummary> => {
    return httpClient.get<DashboardSummary>(`/dashboard/summary?period=${period}`);
  },
  getStats: async (): Promise<DashboardStats> => {
    return httpClient.get<DashboardStats>('/dashboard/stats');
  },
  getSystemOverview: async (): Promise<DashboardSystemOverview> => {
    return httpClient.get<DashboardSystemOverview>('/dashboard/system-overview');
  },
  getRecentDetections: async (limit: number = 5): Promise<DetectionRead[]> => {
    return httpClient.get<DetectionRead[]>(`/detections/?limit=${limit}`);
  },
  getPipelineStatus: async (): Promise<PipelineStatus> => {
    return httpClient.get<PipelineStatus>('/pipeline/status');
  },
};

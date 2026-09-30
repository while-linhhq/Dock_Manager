import { httpClient } from '../../../services/httpClient';
import type {
  DashboardPeriod,
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

/**
 * Cửa sổ nhận diện của dashboard — KHÔNG được cắt nhỏ tuỳ tiện.
 *
 * Sidebar chỉ hiện 18 dòng (`SIDEBAR_LIMIT` trong `DashboardRecentDetectionsSidebar`)
 * nhưng mảng này còn là nguồn số của các widget phân tích trong
 * `DashboardAiAnalyticsCharts`:
 * - `buildConfidenceBuckets` LUÔN tính trên đúng mảng này;
 * - `buildTopShipCounts` rơi về mảng này khi `summary.top_ship_labels` rỗng — đúng
 *   trường hợp kỳ `day` (kỳ mặc định khi mở dashboard) hiện nay;
 * - `buildDetectionsByHourLast24h` / `buildAcceptanceSplit` rơi về mảng này khi
 *   `/dashboard/summary` thiếu chuỗi tổng hợp.
 * Vì vậy 120 → 20 là hồi quy số liệu âm thầm, không phải tối ưu (số đo thật ở
 * `.superpowers/sdd/2026-09-30-pagination-dashboard-performance/task-15-report.md`).
 * 120 vẫn dưới trần 200 của API nên đạt mục tiêu "≤ 200 dòng/request"; muốn giảm
 * thật (120 dòng ≈ 10,6 MB, ~0,35–0,49 s) thì bốn widget phải đọc API tổng hợp
 * phía server (Task 17), không phải cắt cửa sổ ở client.
 */
export const DASHBOARD_DETECTIONS_WINDOW = 120;

export const dashboardApi = {
  getSummary: async (period: DashboardPeriod = 'day'): Promise<DashboardSummary> => {
    return httpClient.get<DashboardSummary>(`/dashboard/summary?period=${period}`);
  },
  getStats: async (): Promise<DashboardStats> => {
    return httpClient.get<DashboardStats>('/dashboard/stats');
  },
  getRecentDetections: async (
    limit: number = DASHBOARD_DETECTIONS_WINDOW,
  ): Promise<DetectionRead[]> => {
    return httpClient.get<DetectionRead[]>(`/detections/?limit=${limit}`);
  },
  getPipelineStatus: async (): Promise<PipelineStatus> => {
    return httpClient.get<PipelineStatus>('/pipeline/status');
  },
};

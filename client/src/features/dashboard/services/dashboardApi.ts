import { httpClient } from '../../../services/httpClient';
import type {
  DashboardDetectionAnalytics,
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
 * Cửa sổ nhận diện của dashboard — số dòng sidebar "Nhận diện gần đây" hiển thị.
 *
 * 18 là ĐÚNG số dòng sidebar vẽ (`DashboardRecentDetectionsSidebar`), và cũng là cửa
 * sổ duy nhất dashboard tải về. Bốn widget phân tích (biểu đồ 24 giờ, trạng thái
 * duyệt, top tàu, phân bố độ tin cậy) đọc số tổng hợp từ
 * `GET /dashboard/detection-analytics` — chúng KHÔNG còn đếm trên mảng này.
 *
 * Task 15 phải giữ 120 dòng vì lúc đó bốn widget tự đếm trên mảng (cắt xuống 18 là
 * hồi quy số liệu âm thầm). Task 18 nối client sang API tổng hợp nên mới cắt được;
 * 18 dòng vẫn mang `ocr_results` (đo trên DB thật: 2,27 MB, 99,5 % khối lượng) —
 * phần băng thông đó là việc của Task 19.
 */
export const DASHBOARD_DETECTIONS_LIMIT = 18;

export const dashboardApi = {
  getSummary: async (period: DashboardPeriod = 'day'): Promise<DashboardSummary> => {
    return httpClient.get<DashboardSummary>(`/dashboard/summary?period=${period}`);
  },
  getStats: async (): Promise<DashboardStats> => {
    return httpClient.get<DashboardStats>('/dashboard/stats');
  },
  /**
   * Bốn widget phân tích của dashboard, tổng hợp bằng aggregate ở SQL (Task 17).
   *
   * `period` là đúng `DashboardPeriod` của client (`day | month | year`) — endpoint
   * có cả nhánh `year` như `/dashboard/summary` nên tab "Năm" không còn 422.
   * `by_hour` trong response luôn là 24 giờ cuộn, không phụ thuộc `period`.
   */
  getDetectionAnalytics: async (
    period: DashboardPeriod = 'day',
  ): Promise<DashboardDetectionAnalytics> => {
    return httpClient.get<DashboardDetectionAnalytics>(
      `/dashboard/detection-analytics?period=${period}`,
    );
  },
  getRecentDetections: async (
    limit: number = DASHBOARD_DETECTIONS_LIMIT,
  ): Promise<DetectionRead[]> => {
    return httpClient.get<DetectionRead[]>(`/detections/?limit=${limit}`);
  },
  getPipelineStatus: async (): Promise<PipelineStatus> => {
    return httpClient.get<PipelineStatus>('/pipeline/status');
  },
};

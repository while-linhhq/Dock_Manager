import { httpClient } from '../../../services/httpClient';
import type {
  DetectionRead,
  CameraRead,
  DetectionMediaRead,
  BoundaryLines,
  CameraDetectionSettings,
} from '../../../types/api.types';

export type DetectionVerify = {
  is_accepted: boolean;
  rejection_reason?: string;
}

export type DetectionUpdate = {
  vessel_id?: number | null;
  track_id?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  berth_in_time?: string | null;
  berth_out_time?: string | null;
  confidence?: number | null;
}

export type CameraCreate = {
  name: string;
  rtsp_url: string;
  is_active?: boolean;
}

type CameraApiPayload = {
  camera_name: string;
  rtsp_url: string;
  is_active?: boolean;
}

export type PortConfigRead = {
  key: string;
  value: string;
  description?: string;
}

export type PortConfigUpdate = {
  value: string;
  description?: string;
}

export type PortConfigCreate = {
  key: string;
  value: string;
  description?: string;
}

export type PipelineStartRequest = {
  camera_group_id: number;
  enable_ocr?: boolean;
}

export type LogsResponse = {
  path: string;
  exists: boolean;
  lines: string[];
  returned: number;
  requested: number;
}

/** Bảy bộ lọc của bảng nhận diện — gửi thẳng thành tham số query của API. */
export type DetectionFilters = {
  q?: string;
  isAccepted?: 'all' | 'yes' | 'no';
  vesselId?: string;
  vesselTypeId?: string;
  /** Ngày địa phương `YYYY-MM-DD` (ô lọc `input type="date"`). */
  dateFrom?: string;
  dateTo?: string;
  /** Độ tin cậy tối thiểu theo % (ô lọc nhập 0–100). */
  minConfidencePct?: string;
};

/** Khóa sắp xếp hợp lệ — khớp whitelist `SORT_COLUMNS` của API detections. */
export const DETECTION_SORT_KEYS = [
  'berth',
  'time',
  'ship_id',
  'confidence',
  'camera',
  'status',
] as const;

export type DetectionSortKey = (typeof DETECTION_SORT_KEYS)[number];

export type DetectionSort = {
  key: DetectionSortKey;
  order: 'asc' | 'desc';
};

export function isDetectionSortKey(value: string): value is DetectionSortKey {
  return DETECTION_SORT_KEYS.some((key) => key === value);
}

/**
 * Ngày địa phương `YYYY-MM-DD` → instant UTC để server so với
 * `coalesce(start_time, created_at)`. `endOfDay` dành cho mốc "đến ngày"
 * (23:59:59.999 giờ địa phương) — đúng khoảng ngày mà bộ lọc client-side
 * trước đây áp dụng.
 */
function localDateToUtcIso(value: string | undefined, endOfDay: boolean): string | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value ?? '').trim());
  if (!match) {
    return undefined;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = endOfDay
    ? new Date(year, month - 1, day, 23, 59, 59, 999)
    : new Date(year, month - 1, day);
  // `new Date(y, m, d)` tự cuộn ngày/tháng không hợp lệ (31/02 → 02/03) nên so lại.
  if (date.getMonth() !== month - 1 || date.getDate() !== day) {
    return undefined;
  }
  return date.toISOString();
}

function toCameraApiPayload(data: CameraCreate | Partial<CameraCreate>): Partial<CameraApiPayload> {
  return {
    ...(data.name != null ? { camera_name: data.name } : {}),
    ...(data.rtsp_url != null ? { rtsp_url: data.rtsp_url } : {}),
    ...(data.is_active != null ? { is_active: data.is_active } : {}),
  };
}

export const portApi = {
  /**
   * Một trang nhận diện: 7 bộ lọc + sắp xếp chạy ở SQL phía server.
   * Tham số khớp `fetcher` của `usePagedQuery` (`skip`/`limit`/`filters`/`sort`).
   */
  getDetectionsPage: async (request: {
    skip: number;
    limit: number;
    filters: DetectionFilters;
    sort?: DetectionSort;
  }): Promise<{ items: DetectionRead[]; total: number }> => {
    const { skip, limit, filters, sort } = request;
    const minConfidencePct = (filters.minConfidencePct ?? '').trim();
    const minConfidence = minConfidencePct ? Number(minConfidencePct) : Number.NaN;

    return httpClient.getPaged<DetectionRead>('/detections/', {
      skip,
      limit,
      q: filters.q || undefined,
      // "Tất cả" thì bỏ hẳn tham số, chỉ gửi khi người dùng chọn rõ có/chưa duyệt.
      is_accepted:
        filters.isAccepted === 'yes' ? true : filters.isAccepted === 'no' ? false : undefined,
      vessel_id: filters.vesselId || undefined,
      vessel_type_id: filters.vesselTypeId || undefined,
      occurred_from: localDateToUtcIso(filters.dateFrom, false),
      occurred_to: localDateToUtcIso(filters.dateTo, true),
      min_confidence: Number.isFinite(minConfidence) ? minConfidence / 100 : undefined,
      sort: sort?.key,
      order: sort?.order,
      // include_presigned_paths: đổi s3://... thành URL media qua API để modal đối chiếu
      // (nhánh fallback khi detection không có bản ghi media) mở được từ trình duyệt ở xa.
      include_presigned_paths: true,
    });
  },
  verifyDetection: async (id: string, data: DetectionVerify): Promise<DetectionRead> => {
    return httpClient.post<DetectionRead>(`/detections/${id}/verify`, data);
  },
  updateDetection: async (id: string, data: DetectionUpdate): Promise<DetectionRead> => {
    return httpClient.patch<DetectionRead>(`/detections/${id}`, data);
  },
  getDetectionMedia: async (id: string): Promise<DetectionMediaRead[]> => {
    return httpClient.get<DetectionMediaRead[]>(`/detections/${id}/media`);
  },
  getCameras: async (activeOnly: boolean = false): Promise<CameraRead[]> => {
    return httpClient.get<CameraRead[]>(`/cameras/?active_only=${activeOnly}`);
  },
  getCamera: async (cameraId: string | number): Promise<CameraRead> => {
    return httpClient.get<CameraRead>(`/cameras/${cameraId}`);
  },
  setBoundaryLines: async (
    cameraId: string | number,
    payload: BoundaryLines,
  ): Promise<CameraRead> => {
    return httpClient.put<CameraRead>(`/cameras/${cameraId}/boundary-lines`, payload);
  },
  setDetectionSettings: async (
    cameraId: string | number,
    payload: CameraDetectionSettings,
  ): Promise<CameraRead> => {
    return httpClient.put<CameraRead>(`/cameras/${cameraId}/detection-settings`, payload);
  },
  clearBoundaryLines: async (cameraId: string | number): Promise<CameraRead> => {
    return httpClient.delete<CameraRead>(`/cameras/${cameraId}/boundary-lines`);
  },
  createCamera: async (data: CameraCreate): Promise<CameraRead> => {
    return httpClient.post<CameraRead>('/cameras/', toCameraApiPayload(data));
  },
  updateCamera: async (id: string, data: Partial<CameraCreate>): Promise<CameraRead> => {
    return httpClient.put<CameraRead>(`/cameras/${id}`, toCameraApiPayload(data));
  },
  deleteCamera: async (id: string | number): Promise<void> => {
    await httpClient.delete(`/cameras/${id}`);
  },
  getPortConfigs: async (): Promise<PortConfigRead[]> => {
    return httpClient.get<PortConfigRead[]>('/port-configs/');
  },
  updatePortConfig: async (key: string, data: PortConfigUpdate): Promise<PortConfigRead> => {
    return httpClient.put<PortConfigRead>(`/port-configs/${key}`, data);
  },
  createPortConfig: async (data: PortConfigCreate): Promise<PortConfigRead> => {
    return httpClient.post<PortConfigRead>('/port-configs/', data);
  },
  deletePortConfig: async (key: string): Promise<void> => {
    return httpClient.delete(`/port-configs/${key}`);
  },
  deleteDetection: async (id: string): Promise<void> => {
    return httpClient.delete(`/detections/${id}`);
  },
  startPipeline: async (
    data: PipelineStartRequest,
  ): Promise<{
    message: string;
    camera_group_id?: number;
    camera_group_name?: string;
  }> => {
    return httpClient.post('/pipeline/start', data);
  },
  stopPipeline: async (): Promise<{ message: string }> => {
    return httpClient.post('/pipeline/stop');
  },
  shutdownServer: async (): Promise<{ message: string; orphan_ocr_killed: number[] }> => {
    return httpClient.post('/pipeline/shutdown-server');
  },
  getLogs: async (lines: number = 200): Promise<LogsResponse> => {
    return httpClient.get<LogsResponse>(`/pipeline/logs?lines=${lines}`);
  },
};

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

function toCameraApiPayload(data: CameraCreate | Partial<CameraCreate>): Partial<CameraApiPayload> {
  return {
    ...(data.name != null ? { camera_name: data.name } : {}),
    ...(data.rtsp_url != null ? { rtsp_url: data.rtsp_url } : {}),
    ...(data.is_active != null ? { is_active: data.is_active } : {}),
  };
}

export const portApi = {
  getDetections: async (skip: number = 0, limit: number = 100, vesselId?: string): Promise<DetectionRead[]> => {
    const params = new URLSearchParams({ skip: skip.toString(), limit: limit.toString() });
    if (vesselId) params.append('vessel_id', vesselId);
    // include_presigned_paths: đổi s3://... thành URL media qua API để modal đối chiếu
    // (nhánh fallback khi detection không có bản ghi media) mở được từ trình duyệt ở xa.
    params.append('include_presigned_paths', 'true');
    return httpClient.get<DetectionRead[]>(`/detections/?${params.toString()}`);
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

import { httpClient } from '../../../services/httpClient';
import type { DetectionRead, CameraRead } from '../../../types/api.types';

export type DetectionVerify = {
  is_accepted: boolean;
  rejection_reason?: string;
}

export type CameraCreate = {
  name: string;
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
  source?: string;
  camera_id?: number;
  enable_ocr?: boolean;
}

export const portApi = {
  getDetections: async (skip: number = 0, limit: number = 100, vesselId?: string): Promise<DetectionRead[]> => {
    const params = new URLSearchParams({ skip: skip.toString(), limit: limit.toString() });
    if (vesselId) params.append('vessel_id', vesselId);
    return httpClient.get<DetectionRead[]>(`/detections/?${params.toString()}`);
  },
  verifyDetection: async (id: string, data: DetectionVerify): Promise<DetectionRead> => {
    return httpClient.post<DetectionRead>(`/detections/${id}/verify`, data);
  },
  getCameras: async (activeOnly: boolean = false): Promise<CameraRead[]> => {
    return httpClient.get<CameraRead[]>(`/cameras/?active_only=${activeOnly}`);
  },
  createCamera: async (data: CameraCreate): Promise<CameraRead> => {
    return httpClient.post<CameraRead>('/cameras/', data);
  },
  updateCamera: async (id: string, data: Partial<CameraCreate>): Promise<CameraRead> => {
    return httpClient.put<CameraRead>(`/cameras/${id}`, data);
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
  ): Promise<{ message: string; source: string; camera_id?: number; camera_name?: string }> => {
    return httpClient.post('/pipeline/start', data);
  },
  stopPipeline: async (): Promise<{ message: string }> => {
    return httpClient.post('/pipeline/stop');
  },
};

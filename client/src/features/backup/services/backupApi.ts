import { httpClient } from '../../../services/httpClient';
import type { AuditLogRead } from '../../../types/api.types';

export type DetectionMediaRead = {
  id: string;
  detection_id: string;
  media_type: 'image' | 'video';
  file_path: string;
  created_at: string;
}

export const backupApi = {
  getAuditLogs: async (userId?: string, limit: number = 50): Promise<AuditLogRead[]> => {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (userId) params.append('user_id', userId);
    return httpClient.get<AuditLogRead[]>(`/audit-logs/?${params.toString()}`);
  },
  getDetectionMedia: async (detectionId: string): Promise<DetectionMediaRead[]> => {
    return httpClient.get<DetectionMediaRead[]>(`/detections/${detectionId}/media`);
  },
};

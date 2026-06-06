import { httpClient } from './httpClient';
import type { DetectionMediaRead, DetectionRead } from '../types/api.types';

export async function fetchDetectionCompareMedia(
  detectionId: string | number,
): Promise<DetectionMediaRead[]> {
  const media = await httpClient.get<DetectionMediaRead[]>(`/detections/${detectionId}/media`);
  if (media.length > 0) {
    return media;
  }

  const det = await httpClient.get<DetectionRead>(`/detections/${detectionId}`);
  const fallback: DetectionMediaRead[] = [];
  if (det.audit_image_path || det.audit_image_url) {
    fallback.push({
      id: -1,
      detection_id: Number(det.id),
      media_type: 'image',
      file_path: det.audit_image_path || det.audit_image_url || '',
      file_size: null,
      created_at: det.created_at,
    });
  }
  if (det.video_path || det.video_url) {
    fallback.push({
      id: -2,
      detection_id: Number(det.id),
      media_type: 'video',
      file_path: det.video_path || det.video_url || '',
      file_size: null,
      created_at: det.created_at,
    });
  }
  return fallback;
}

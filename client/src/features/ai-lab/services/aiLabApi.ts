import { httpClient } from '../../../services/httpClient';
import type { LabDetectionResponse, LabGroupCamResponse, LabOcrResponse, LabVisualSearchResponse } from '../types/ai-lab.types';

export const aiLabApi = {
  detectMedia: (
    file: File,
    options?: { frameStride?: number; maxOutputFrames?: number; enableOcr?: boolean },
  ): Promise<LabDetectionResponse> => {
    const form = new FormData();
    form.append('file', file);
    form.append('frame_stride', String(options?.frameStride ?? 8));
    form.append('max_output_frames', String(options?.maxOutputFrames ?? 48));
    form.append('enable_ocr', String(options?.enableOcr !== false));
    return httpClient.post<LabDetectionResponse>('/ai-lab/detect', form);
  },

  runGroupCamTest: (
    items: Array<{ cameraId: number; file: File }>,
    options?: { groupId?: number | null; frameStride?: number; maxOutputFrames?: number; enableOcr?: boolean },
  ): Promise<LabGroupCamResponse> => {
    const form = new FormData();
    items.forEach((item) => {
      form.append('files', item.file);
      form.append('camera_ids', String(item.cameraId));
    });
    if (options?.groupId) {
      form.append('group_id', String(options.groupId));
    }
    form.append('frame_stride', String(options?.frameStride ?? 8));
    form.append('max_output_frames', String(options?.maxOutputFrames ?? 48));
    form.append('enable_ocr', String(options?.enableOcr !== false));
    return httpClient.post<LabGroupCamResponse>('/ai-lab/group-cam-test', form);
  },

  visualSearch: (file: File): Promise<LabVisualSearchResponse> => {
    const form = new FormData();
    form.append('file', file);
    return httpClient.post<LabVisualSearchResponse>('/ai-lab/visual-search', form);
  },

  runOcr: (file: File): Promise<LabOcrResponse> => {
    const form = new FormData();
    form.append('file', file);
    return httpClient.post<LabOcrResponse>('/ai-lab/ocr', form);
  },
};

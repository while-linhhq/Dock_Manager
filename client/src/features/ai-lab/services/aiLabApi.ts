import { httpClient } from '../../../services/httpClient';
import type { LabDetectionResponse, LabOcrResponse, LabVisualSearchResponse } from '../types/ai-lab.types';

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

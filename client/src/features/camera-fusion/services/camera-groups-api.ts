import { httpClient } from '../../../services/httpClient';
import { authStorage } from '../../../services/authStorage';
import type { CameraGroup, CameraGroupPayload } from '../types/fusion.types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

async function fetchBlob(endpoint: string, options: RequestInit = {}): Promise<Blob> {
  const headers = new Headers(options.headers);
  const token = authStorage.getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(`${BASE_URL}${endpoint}`, { ...options, headers });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.blob();
}

export const cameraGroupsApi = {
  list: (activeOnly = false): Promise<CameraGroup[]> =>
    httpClient.get<CameraGroup[]>(`/camera-groups/?active_only=${activeOnly}`),
  get: (id: string | number): Promise<CameraGroup> =>
    httpClient.get<CameraGroup>(`/camera-groups/${id}`),
  create: (payload: CameraGroupPayload): Promise<CameraGroup> =>
    httpClient.post<CameraGroup>('/camera-groups/', payload),
  update: (id: string | number, payload: Partial<CameraGroupPayload>): Promise<CameraGroup> =>
    httpClient.patch<CameraGroup>(`/camera-groups/${id}`, payload),
  delete: (id: string | number): Promise<void> =>
    httpClient.delete<void>(`/camera-groups/${id}`),
  snapshot: (cameraId: string | number): Promise<Blob> =>
    fetchBlob(`/cameras/${cameraId}/snapshot`),
  previewFused: (payload: Omit<CameraGroupPayload, 'name' | 'description' | 'is_active'>): Promise<Blob> =>
    fetchBlob('/camera-groups/preview-fused', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

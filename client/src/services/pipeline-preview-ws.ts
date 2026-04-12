import { authStorage } from './authStorage';

/** WebSocket URL for authenticated pipeline JPEG preview (same host/path as REST API). */
export function buildPipelinePreviewWsUrl(): string | null {
  const token = authStorage.getToken();
  if (!token) {
    return null;
  }
  const httpBase =
    import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
  const u = new URL(httpBase);
  const wsProto = u.protocol === 'https:' ? 'wss:' : 'ws:';
  const path = u.pathname.replace(/\/$/, '');
  const q = new URLSearchParams({ token });
  return `${wsProto}//${u.host}${path}/pipeline/preview-stream?${q.toString()}`;
}

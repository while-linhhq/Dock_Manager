import { authStorage } from './authStorage';

/** Chuẩn hóa base REST (absolute) — env thường là `/api/v1` hoặc full URL. */
function resolveApiBaseUrl(): string {
  const raw = (import.meta.env.VITE_API_BASE_URL || '').trim();
  if (!raw) {
    return typeof window !== 'undefined' && window.location?.origin
      ? `${window.location.origin}/api/v1`
      : 'http://localhost:5173/api/v1';
  }
  if (/^https?:\/\//i.test(raw)) {
    return raw.replace(/\/$/, '');
  }
  const path = raw.startsWith('/') ? raw : `/${raw}`;
  const origin =
    typeof window !== 'undefined' && window.location?.origin
      ? window.location.origin
      : 'http://localhost:5173';
  return `${origin}${path}`.replace(/\/$/, '');
}

/** If API base is relative, prefer explicit proxy target for WS host (prod proxy often blocks WS upgrade). */
function resolveWsBaseUrl(): string {
  const wsBaseOverride = (import.meta.env.VITE_PIPELINE_PREVIEW_WS_BASE || '').trim();
  if (wsBaseOverride) {
    return wsBaseOverride.replace(/\/$/, '');
  }

  const apiBaseRaw = (import.meta.env.VITE_API_BASE_URL || '').trim();
  const proxyTarget = (import.meta.env.VITE_API_PROXY_TARGET || '').trim();
  const apiBasePath = apiBaseRaw
    ? (apiBaseRaw.startsWith('/') ? apiBaseRaw : `/${apiBaseRaw}`)
    : '/api/v1';

  if (proxyTarget && !/^https?:\/\//i.test(apiBaseRaw)) {
    return `${proxyTarget.replace(/\/$/, '')}${apiBasePath}`.replace(/\/$/, '');
  }

  return resolveApiBaseUrl();
}

/**
 * WebSocket URL for pipeline JPEG preview (JWT in query).
 * Mặc định: cùng host/path với REST (`resolveApiBaseUrl`).
 * Nếu nginx phía SPA không proxy WebSocket: set `VITE_PIPELINE_PREVIEW_WS_BASE`
 * Example: `wss://api-basondock.iotforce.io.vn/api/v1` (trailing slash optional).
 */
export function buildPipelinePreviewWsUrl(): string | null {
  const token = authStorage.getToken();
  if (!token) {
    return null;
  }
  const q = new URLSearchParams({ token });
  const streamPath = '/pipeline/preview-stream';
  const wsBase = resolveWsBaseUrl();
  const u = new URL(wsBase);
  const wsProto = u.protocol === 'https:' ? 'wss:' : 'ws:';
  const path = u.pathname.replace(/\/$/, '');
  return `${wsProto}//${u.host}${path}${streamPath}?${q.toString()}`;
}

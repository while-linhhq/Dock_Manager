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

/** Trang đang chạy trên chính máy chủ? Chỉ khi đó mới được ghim WS về 127.0.0.1. */
function isLocalPage(): boolean {
  if (typeof window === 'undefined' || !window.location) {
    return true;
  }
  const host = (window.location.hostname || '').toLowerCase();
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
}

/**
 * Base cho WebSocket.
 * - `VITE_PIPELINE_PREVIEW_WS_BASE` luôn thắng (dùng khi proxy phía trước không nâng cấp WS).
 * - Chỉ ghim về `VITE_API_PROXY_TARGET` khi trang chạy trên localhost; trước đây ghim vô
 *   điều kiện nên truy cập từ máy khác (qua domain) sẽ trỏ vào 127.0.0.1 của chính họ → không có preview.
 * - Còn lại: same-origin khi API base là đường dẫn tương đối, ngược lại dùng API base tuyệt đối.
 */
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

  if (isLocalPage() && proxyTarget && !/^https?:\/\//i.test(apiBaseRaw)) {
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

/**
 * WebSocket URL for realtime backend log streaming (JWT in query).
 * `lines` = số dòng tail gửi ban đầu khi kết nối.
 */
export function buildLogsStreamWsUrl(lines = 200): string | null {
  const token = authStorage.getToken();
  if (!token) {
    return null;
  }
  const q = new URLSearchParams({ token, lines: String(lines) });
  const streamPath = '/pipeline/logs-stream';
  const wsBase = resolveWsBaseUrl();
  const u = new URL(wsBase);
  const wsProto = u.protocol === 'https:' ? 'wss:' : 'ws:';
  const path = u.pathname.replace(/\/$/, '');
  return `${wsProto}//${u.host}${path}${streamPath}?${q.toString()}`;
}

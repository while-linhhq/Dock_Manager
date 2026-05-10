import { useEffect, useState } from 'react';
import { authStorage } from '../../../services/authStorage';

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

function buildCameraStreamUrl(cameraId: number | string): string | null {
  const token = authStorage.getToken();
  if (!token) {
    return null;
  }
  const wsBase = resolveWsBaseUrl();
  const url = new URL(wsBase);
  const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const path = url.pathname.replace(/\/$/, '');
  const query = new URLSearchParams({ token });
  return `${wsProtocol}//${url.host}${path}/camera-groups/editor-preview/${cameraId}?${query.toString()}`;
}

export function useCameraStream(cameraId?: number | string | null) {
  const [url, setUrl] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!cameraId) {
      const timer = window.setTimeout(() => {
        setUrl((previous) => {
          if (previous) {
            URL.revokeObjectURL(previous);
          }
          return null;
        });
        setIsConnected(false);
      }, 0);
      return () => window.clearTimeout(timer);
    }

    let socket: WebSocket | null = null;
    let closed = false;
    let retryTimer: number | null = null;
    let activeUrl: string | null = null;
    let retries = 0;

    const connect = () => {
      const streamUrl = buildCameraStreamUrl(cameraId);
      if (!streamUrl || closed) {
        return;
      }

      socket = new WebSocket(streamUrl);
      socket.binaryType = 'blob';

      socket.onopen = () => {
        if (closed) {
          return;
        }
        retries = 0;
        setIsConnected(true);
      };

      socket.onmessage = (event) => {
        if (closed) {
          return;
        }
        if (typeof event.data === 'string') {
          return;
        }
        const nextUrl = URL.createObjectURL(event.data as Blob);
        setUrl((previous) => {
          if (previous) {
            URL.revokeObjectURL(previous);
          }
          activeUrl = nextUrl;
          return nextUrl;
        });
      };

      socket.onclose = () => {
        if (closed) {
          return;
        }
        setIsConnected(false);
        retries += 1;
        const delay = Math.min(5000, 500 * retries);
        retryTimer = window.setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();

    return () => {
      closed = true;
      if (retryTimer != null) {
        window.clearTimeout(retryTimer);
      }
      socket?.close();
      if (activeUrl) {
        URL.revokeObjectURL(activeUrl);
      }
    };
  }, [cameraId]);

  return { url, isConnected };
}

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
  const [receivedFps, setReceivedFps] = useState(0);
  const [renderFps, setRenderFps] = useState(0);

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
        setReceivedFps(0);
        setRenderFps(0);
      }, 0);
      return () => window.clearTimeout(timer);
    }

    let socket: WebSocket | null = null;
    let closed = false;
    let connectTimer: number | null = null;
    let retryTimer: number | null = null;
    let activeUrl: string | null = null;
    let pendingUrl: string | null = null;
    let animationFrame: number | null = null;
    let retries = 0;
    let receivedCount = 0;
    let renderedCount = 0;
    let fpsWindowStartedAt = performance.now();

    const flushFrame = () => {
      animationFrame = null;
      if (!pendingUrl) {
        return;
      }
      const nextUrl = pendingUrl;
      pendingUrl = null;
      setUrl((previous) => {
        if (previous && previous !== nextUrl) {
          URL.revokeObjectURL(previous);
        }
        activeUrl = nextUrl;
        return nextUrl;
      });
      renderedCount += 1;
    };

    const updateFps = () => {
      const now = performance.now();
      if (now - fpsWindowStartedAt < 1000) {
        return;
      }
      setReceivedFps(receivedCount);
      setRenderFps(renderedCount);
      receivedCount = 0;
      renderedCount = 0;
      fpsWindowStartedAt = now;
    };

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
        receivedCount += 1;
        if (pendingUrl) {
          URL.revokeObjectURL(pendingUrl);
        }
        pendingUrl = nextUrl;
        if (animationFrame == null) {
          animationFrame = window.requestAnimationFrame(flushFrame);
        }
        updateFps();
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

    connectTimer = window.setTimeout(connect, 50);

    return () => {
      closed = true;
      if (connectTimer != null) {
        window.clearTimeout(connectTimer);
      }
      if (retryTimer != null) {
        window.clearTimeout(retryTimer);
      }
      socket?.close();
      if (animationFrame != null) {
        window.cancelAnimationFrame(animationFrame);
      }
      if (activeUrl) {
        URL.revokeObjectURL(activeUrl);
      }
      if (pendingUrl) {
        URL.revokeObjectURL(pendingUrl);
      }
    };
  }, [cameraId]);

  return { url, isConnected, receivedFps, renderFps };
}

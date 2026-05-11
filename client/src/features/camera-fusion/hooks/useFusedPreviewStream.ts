import { useEffect, useMemo, useRef, useState } from 'react';
import { authStorage } from '../../../services/authStorage';
import type { CameraGroupMember, FusionMode, StitchMetadata } from '../types/fusion.types';

type FusedPreviewPayload = {
  fusion_mode: FusionMode;
  canvas_width: number;
  canvas_height: number;
  members: CameraGroupMember[];
  stitch_metadata?: StitchMetadata | null;
};

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

function buildFusedPreviewStreamUrl(): string | null {
  const token = authStorage.getToken();
  if (!token) {
    return null;
  }
  const wsBase = resolveWsBaseUrl();
  const url = new URL(wsBase);
  const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const path = url.pathname.replace(/\/$/, '');
  const query = new URLSearchParams({ token });
  return `${wsProtocol}//${url.host}${path}/camera-groups/editor-preview/fused?${query.toString()}`;
}

export function useFusedPreviewStream(payload: FusedPreviewPayload, streamKey = '') {
  const [url, setUrl] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receivedFps, setReceivedFps] = useState(0);
  const [renderFps, setRenderFps] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const payloadJson = useMemo(() => JSON.stringify(payload), [payload]);
  const payloadJsonRef = useRef(payloadJson);

  useEffect(() => {
    payloadJsonRef.current = payloadJson;
  }, [payloadJson]);

  useEffect(() => {
    if (payload.members.length === 0) {
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

    const sendPayload = () => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(payloadJsonRef.current);
      }
    };

    const connect = () => {
      const streamUrl = buildFusedPreviewStreamUrl();
      if (!streamUrl || closed) {
        return;
      }

      socket = new WebSocket(streamUrl);
      socketRef.current = socket;
      socket.binaryType = 'blob';

      socket.onopen = () => {
        if (closed) {
          return;
        }
        retries = 0;
        setIsConnected(true);
        setError(null);
        sendPayload();
      };

      socket.onmessage = (event) => {
        if (closed || typeof event.data === 'string') {
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
        if (!closed) {
          setError('Không mở được fused preview stream.');
        }
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
  }, [payload.members.length, streamKey]);

  useEffect(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(payloadJson);
    }
  }, [payloadJson]);

  return { url, isConnected, error, receivedFps, renderFps };
}

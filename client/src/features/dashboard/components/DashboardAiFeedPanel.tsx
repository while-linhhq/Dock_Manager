import React, { useEffect, useRef, useState } from 'react';
import { Camera, Ship, Video, BarChart3 } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { buildPipelinePreviewWsUrl } from '../../../services/pipeline-preview-ws';
import type { PipelineStatus } from '../services/dashboardApi';
import type {
  DashboardPeriod,
  DashboardStats,
  DashboardSummary,
  DetectionRead,
} from '../../../types/api.types';
import { DashboardAiAnalyticsCharts } from './DashboardAiAnalyticsCharts';

type AiPanelTab = 'live' | 'analytics';

export type DashboardAiFeedPanelProps = {
  pipelineStatus: PipelineStatus | null;
  detections: DetectionRead[];
  stats: DashboardStats | null;
  summary: DashboardSummary | null;
  summaryPeriod: DashboardPeriod;
  isLoading: boolean;
  onRefreshAnalytics: () => void;
};

export const DashboardAiFeedPanel: React.FC<DashboardAiFeedPanelProps> = ({
  pipelineStatus,
  detections,
  stats,
  summary,
  summaryPeriod,
  isLoading,
  onRefreshAnalytics,
}) => {
  const [tab, setTab] = useState<AiPanelTab>('live');
  const [pipelinePreviewUrl, setPipelinePreviewUrl] = useState<string | null>(null);
  const previewObjectUrlRef = useRef<string | null>(null);

  const wsActive = tab === 'live' && Boolean(pipelineStatus?.is_running);

  useEffect(() => {
    if (!wsActive) {
      if (previewObjectUrlRef.current) {
        URL.revokeObjectURL(previewObjectUrlRef.current);
        previewObjectUrlRef.current = null;
      }
      setPipelinePreviewUrl(null);
      return;
    }

    const wsUrl = buildPipelinePreviewWsUrl();
    if (!wsUrl) {
      return;
    }

    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let watchdogTimer: ReturnType<typeof setInterval> | null = null;
    let lastMessageAt = Date.now();

    const clearReconnect = () => {
      if (reconnectTimer != null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const clearWatchdog = () => {
      if (watchdogTimer != null) {
        clearInterval(watchdogTimer);
        watchdogTimer = null;
      }
    };

    const revokePreview = () => {
      if (previewObjectUrlRef.current) {
        URL.revokeObjectURL(previewObjectUrlRef.current);
        previewObjectUrlRef.current = null;
      }
      setPipelinePreviewUrl(null);
    };

    const hardResetSocket = () => {
      try {
        ws?.close();
      } catch {
        // ignore
      }
      ws = null;
    };

    const connect = () => {
      if (cancelled) {
        return;
      }
      clearReconnect();
      clearWatchdog();
      lastMessageAt = Date.now();
      ws = new WebSocket(wsUrl);
      ws.binaryType = 'blob';

      ws.onopen = () => {
        attempt = 0;
        clearWatchdog();
        watchdogTimer = setInterval(() => {
          // If we stop receiving frames for a while, force reconnect.
          // This recovers from "half-open" WS where the browser thinks it's open but nothing flows.
          if (Date.now() - lastMessageAt > 10_000) {
            hardResetSocket();
          }
        }, 2000);
      };

      ws.onmessage = (ev: MessageEvent) => {
        lastMessageAt = Date.now();
        const blob = ev.data as Blob;
        // Server may send text keepalive messages; ignore.
        if (!(blob instanceof Blob) || blob.size === 0) {
          return;
        }
        const next = URL.createObjectURL(blob);
        if (previewObjectUrlRef.current) {
          URL.revokeObjectURL(previewObjectUrlRef.current);
        }
        previewObjectUrlRef.current = next;
        setPipelinePreviewUrl(next);
      };

      ws.onerror = () => {
        /* onclose schedules reconnect */
      };

      ws.onclose = () => {
        if (cancelled) {
          return;
        }
        clearWatchdog();
        attempt += 1;
        if (attempt > 20) {
          return;
        }
        reconnectTimer = setTimeout(connect, Math.min(10_000, 350 * attempt));
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearReconnect();
      clearWatchdog();
      ws?.close();
      revokePreview();
    };
  }, [wsActive]);

  return (
    <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl overflow-hidden shadow-2xl">
      <div className="p-4 border-b border-gray-200 dark:border-white/5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between bg-gray-50 dark:bg-white/[0.02]">
        <div className="flex items-center space-x-2">
          <Camera className="w-4 h-4 text-blue-500 shrink-0" />
          <span className="text-xs font-bold uppercase tracking-widest text-gray-900 dark:text-white">
            AI — Camera &amp; phân tích
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg bg-gray-200/80 dark:bg-white/10 p-0.5">
            <button
              type="button"
              onClick={() => setTab('live')}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest transition-all',
                tab === 'live'
                  ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white',
              )}
            >
              <Video className="h-3.5 w-3.5" />
              Xem trực tiếp
            </button>
            <button
              type="button"
              onClick={() => setTab('analytics')}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest transition-all',
                tab === 'analytics'
                  ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white',
              )}
            >
              <BarChart3 className="h-3.5 w-3.5" />
              Phân tích dữ liệu
            </button>
          </div>
          <div className="hidden sm:block h-3 w-px bg-gray-200 dark:bg-white/10" />
          <div className="flex items-center space-x-3">
            <span className="flex items-center space-x-1">
              <span
                className={cn(
                  'w-1.5 h-1.5 rounded-full',
                  pipelineStatus?.is_running ? 'animate-pulse bg-red-500' : 'bg-gray-500',
                )}
              />
              <span
                className={cn(
                  'text-[10px] font-mono uppercase',
                  pipelineStatus?.is_running ? 'text-red-500' : 'text-gray-500',
                )}
              >
                {pipelineStatus?.is_running ? 'Đang ghi' : 'Dừng'}
              </span>
            </span>
            <div className="h-3 w-px bg-gray-200 dark:bg-white/10" />
            <span className="text-[10px] font-mono text-gray-500 uppercase">
              Cache: {pipelineStatus?.ocr_cache_size || 0}
            </span>
          </div>
        </div>
      </div>

      {tab === 'live' ? (
        <div className="aspect-video bg-black relative flex items-center justify-center group cursor-crosshair overflow-hidden">
          <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-blue-500/20 via-transparent to-transparent pointer-events-none" />
          {pipelinePreviewUrl ? (
            <img
              src={pipelinePreviewUrl}
              alt=""
              className="absolute inset-0 h-full w-full object-contain"
            />
          ) : (
            <Ship className="relative z-[1] w-20 h-20 text-white/5 group-hover:text-blue-500/10 transition-colors duration-500" />
          )}

          {pipelineStatus?.is_running && !pipelinePreviewUrl && (
            <div className="absolute top-1/4 left-1/4 w-1/2 h-1/2 border-2 border-blue-500/50 rounded-sm z-[1]">
              <div className="absolute -top-6 left-0 bg-blue-500 text-white text-[10px] font-bold px-2 py-0.5 uppercase tracking-tighter rounded-t-sm">
                Đang quét...
              </div>
            </div>
          )}

          <div className="absolute bottom-4 right-4 flex space-x-2 z-[2]">
            <div className="px-2 py-1 bg-black/60 backdrop-blur-md border border-white/10 rounded text-[9px] font-mono text-white uppercase tracking-tighter">
              Hệ thống: {pipelineStatus?.is_running ? 'ONLINE' : 'OFFLINE'}
            </div>
          </div>
        </div>
      ) : (
        <DashboardAiAnalyticsCharts
          detections={detections}
          stats={stats}
          summary={summary}
          summaryPeriod={summaryPeriod}
          isLoading={isLoading}
          onRefresh={onRefreshAnalytics}
        />
      )}
    </div>
  );
};

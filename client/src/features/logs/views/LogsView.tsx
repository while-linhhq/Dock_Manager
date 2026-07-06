import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScrollText, Search, ArrowDownToLine, Wifi, WifiOff, Trash2 } from 'lucide-react';
import { buildLogsStreamWsUrl } from '../../../services/pipeline-preview-ws';

const LINE_OPTIONS = [100, 200, 500, 1000, 2000];
// Giới hạn số dòng giữ trong bộ nhớ để tránh tab phình RAM khi stream chạy lâu.
const MAX_BUFFER_LINES = 5000;
// Keepalive sentinel từ server (bỏ qua, không hiển thị).
const KEEPALIVE = '\x00ka';
const RECONNECT_DELAY_MS = 2000;

type ConnState = 'connecting' | 'open' | 'closed';

function levelClass(line: string): string {
  if (/\bERROR\b|\bCRITICAL\b|Traceback/i.test(line)) {
    return 'text-red-600 dark:text-red-400';
  }
  if (/\bWARNING\b/i.test(line)) {
    return 'text-amber-600 dark:text-amber-400';
  }
  if (/\bINFO\b/i.test(line)) {
    return 'text-blue-600 dark:text-blue-300';
  }
  if (/\bDEBUG\b/i.test(line)) {
    return 'text-gray-400 dark:text-gray-500';
  }
  return 'text-gray-700 dark:text-gray-300';
}

export const LogsView: React.FC = () => {
  const [lines, setLines] = useState<string[]>([]);
  const [connState, setConnState] = useState<ConnState>('connecting');
  const [lineCount, setLineCount] = useState(200);
  const [q, setQ] = useState('');
  const [followTail, setFollowTail] = useState(true);
  const [paused, setPaused] = useState(false);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const pausedRef = useRef(paused);
  const closedByUserRef = useRef(false);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  const connect = useCallback(() => {
    const url = buildLogsStreamWsUrl(lineCount);
    if (!url) {
      setConnState('closed');
      return;
    }
    setConnState('connecting');
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => setConnState('open');

    socket.onmessage = (event) => {
      if (pausedRef.current) {
        return;
      }
      const text = typeof event.data === 'string' ? event.data : '';
      if (text === KEEPALIVE || text === '') {
        return;
      }
      setLines((prev) => {
        const next = prev.length >= MAX_BUFFER_LINES
          ? [...prev.slice(prev.length - MAX_BUFFER_LINES + 1), text]
          : [...prev, text];
        return next;
      });
    };

    socket.onclose = () => {
      setConnState('closed');
      socketRef.current = null;
      if (!closedByUserRef.current) {
        reconnectTimerRef.current = window.setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    socket.onerror = () => {
      socket.close();
    };
  }, [lineCount]);

  // (Re)connect khi đổi số dòng tail ban đầu.
  useEffect(() => {
    closedByUserRef.current = false;
    setLines([]);
    connect();
    return () => {
      closedByUserRef.current = true;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [connect]);

  const filteredLines = useMemo(() => {
    if (!q.trim()) {
      return lines;
    }
    const needle = q.toLowerCase();
    return lines.filter((line) => line.toLowerCase().includes(needle));
  }, [lines, q]);

  useEffect(() => {
    if (followTail && !paused && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredLines, followTail, paused]);

  const statusMeta: Record<ConnState, { label: string; cls: string; icon: React.ReactNode }> = {
    connecting: {
      label: 'Đang kết nối…',
      cls: 'text-amber-500',
      icon: <Wifi className="w-3.5 h-3.5 animate-pulse" />,
    },
    open: {
      label: 'Trực tiếp',
      cls: 'text-green-500',
      icon: <Wifi className="w-3.5 h-3.5" />,
    },
    closed: {
      label: 'Mất kết nối — đang thử lại',
      cls: 'text-red-500',
      icon: <WifiOff className="w-3.5 h-3.5" />,
    },
  };
  const status = statusMeta[connState];

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-blue-600/10 rounded-xl">
            <ScrollText className="w-6 h-6 text-blue-600" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white uppercase tracking-widest">
              Xem Logs Server
            </h2>
            <div className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-widest font-mono ${status.cls}`}>
              {status.icon}
              {status.label}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPaused((p) => !p)}
            className={`rounded-xl px-4 py-2.5 text-xs font-bold uppercase tracking-widest text-white ${
              paused ? 'bg-amber-600 hover:bg-amber-700' : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {paused ? 'Tiếp tục' : 'Tạm dừng'}
          </button>
          <button
            type="button"
            onClick={() => setLines([])}
            className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-xs font-bold uppercase tracking-widest text-gray-600 hover:bg-gray-50 dark:border-white/10 dark:bg-[#121214] dark:text-gray-300"
          >
            <Trash2 className="w-4 h-4" />
            Xóa màn hình
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Lọc theo từ khóa (vd: ERROR, login, pipeline)"
            className="w-full rounded-xl border border-gray-200 bg-white py-2.5 pl-10 pr-3 text-sm dark:border-white/10 dark:bg-[#121214] dark:text-white"
          />
        </div>
        <select
          value={lineCount}
          onChange={(e) => setLineCount(Number(e.target.value))}
          className="rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm dark:border-white/10 dark:bg-[#121214] dark:text-white"
        >
          {LINE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              tail {n} dòng
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-xs font-bold uppercase tracking-wider text-gray-600 dark:border-white/10 dark:bg-[#121214] dark:text-gray-300">
          <input
            type="checkbox"
            checked={followTail}
            onChange={(e) => setFollowTail(e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <ArrowDownToLine className="w-3.5 h-3.5" />
          Cuộn cuối
        </label>
      </div>

      <div
        ref={scrollRef}
        className="h-[calc(100dvh-320px)] min-h-[300px] overflow-auto rounded-2xl border border-gray-200 bg-gray-950 p-4 font-mono text-xs leading-relaxed dark:border-white/10"
      >
        {filteredLines.length === 0 ? (
          <p className="text-gray-500">
            {connState === 'connecting'
              ? 'Đang kết nối…'
              : q.trim()
                ? 'Không có dòng khớp bộ lọc.'
                : 'Chưa có log. Server có thể chưa ghi log ra file (LOG_TO_FILE=true) — cần khởi động lại backend.'}
          </p>
        ) : (
          filteredLines.map((line, idx) => (
            <div key={idx} className={`whitespace-pre-wrap break-words ${levelClass(line)}`}>
              {line || '\u00A0'}
            </div>
          ))
        )}
      </div>

      <p className="text-[11px] text-gray-500 font-mono">
        Hiển thị {filteredLines.length}/{lines.length} dòng
        {q.trim() ? ` (đã lọc từ ${lines.length})` : ''}
        {paused ? ' • ĐANG TẠM DỪNG' : ''}
        {lines.length >= MAX_BUFFER_LINES ? ` • giữ tối đa ${MAX_BUFFER_LINES} dòng` : ''}.
      </p>
    </div>
  );
};

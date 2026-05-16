import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Anchor, RefreshCw, Settings, ShieldCheck, ShieldOff } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { PATHS } from '../../../router/paths';
import { cameraGroupsApi, type CameraGroup } from '../../camera-fusion';
import { LockBackgroundButton } from './LockBackgroundButton';
import { seamAnchorApi } from '../services/seam-anchor-api';
import type { SeamAnchorEntry } from '../types/seam-anchor.types';

type SeamAnchorDashboardCardProps = {
  isRunning: boolean;
  activeGroupId: number | null | undefined;
  seamAnchorActive: boolean | undefined;
};

const POLL_INTERVAL_MS = 5000;

function formatRelative(ts: number): string {
  if (!ts) return '—';
  const diff = Math.max(0, Date.now() / 1000 - ts);
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export const SeamAnchorDashboardCard: React.FC<SeamAnchorDashboardCardProps> = ({
  isRunning,
  activeGroupId,
  seamAnchorActive,
}) => {
  const [groupCache, setGroupCache] = useState<Record<number, CameraGroup>>({});
  const [anchorState, setAnchorState] = useState<{ groupId: number | null; anchors: SeamAnchorEntry[] }>(
    { groupId: null, anchors: [] },
  );
  const [refreshTick, setRefreshTick] = useState(0);
  const fetchedGroupsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!activeGroupId || fetchedGroupsRef.current.has(activeGroupId)) {
      return;
    }
    fetchedGroupsRef.current.add(activeGroupId);
    let cancelled = false;
    cameraGroupsApi
      .get(activeGroupId)
      .then((res) => {
        if (cancelled) return;
        setGroupCache((cache) => ({ ...cache, [res.id]: res }));
      })
      .catch(() => {
        fetchedGroupsRef.current.delete(activeGroupId);
      });
    return () => {
      cancelled = true;
    };
  }, [activeGroupId]);

  useEffect(() => {
    if (!isRunning || !seamAnchorActive) {
      return;
    }

    let cancelled = false;
    const fetchState = () => {
      seamAnchorApi
        .getState()
        .then((res) => {
          if (cancelled) return;
          setAnchorState({
            groupId: res.group_id ?? null,
            anchors: res.anchors ?? [],
          });
        })
        .catch(() => {
          if (cancelled) return;
          setAnchorState({ groupId: null, anchors: [] });
        });
    };

    fetchState();
    const timer = window.setInterval(fetchState, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [isRunning, seamAnchorActive, refreshTick]);

  const group = activeGroupId ? groupCache[activeGroupId] ?? null : null;
  const anchors =
    isRunning && seamAnchorActive && anchorState.groupId === (activeGroupId ?? null)
      ? anchorState.anchors
      : [];

  const cameraIds = useMemo(
    () =>
      (group?.members ?? [])
        .filter((member) => member.enabled)
        .map((member) => Number(member.camera_id)),
    [group],
  );

  const hasGroupContext = Boolean(activeGroupId && group);
  const statusBadge = isRunning && seamAnchorActive ? (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-emerald-500">
      <ShieldCheck className="h-3 w-3" />
      Active
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-gray-500/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-gray-500">
      <ShieldOff className="h-3 w-3" />
      {isRunning ? 'Disabled' : 'Pipeline OFF'}
    </span>
  );

  return (
    <div className="rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-white/5 dark:bg-[#121214]">
      <div className="flex flex-col gap-3 border-b border-gray-200 p-4 dark:border-white/5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-600/10 p-2.5">
            <Anchor className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold uppercase tracking-widest text-gray-900 dark:text-white">
                Seam Anchor — Mooring Persistence
              </h3>
              {statusBadge}
            </div>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              {hasGroupContext
                ? `Đang neo theo group "${group?.name}" (${cameraIds.length} camera).`
                : 'Khởi chạy pipeline cho một group hybrid để bật seam anchor.'}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`${PATHS.PORT}?tab=seam-anchor`}
            className="inline-flex items-center gap-1.5 rounded-xl border border-blue-200 bg-blue-600/10 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-blue-600 hover:bg-blue-600/20 dark:border-blue-500/30 dark:text-blue-400"
          >
            <Settings className="h-3 w-3" />
            Cấu hình
          </Link>
          <button
            type="button"
            onClick={() => setRefreshTick((tick) => tick + 1)}
            disabled={!isRunning || !seamAnchorActive}
            className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-gray-600 hover:bg-gray-50 disabled:opacity-40 dark:border-white/10 dark:text-gray-300 dark:hover:bg-white/5"
          >
            <RefreshCw className="h-3 w-3" />
            Refresh
          </button>
          <LockBackgroundButton
            groupId={activeGroupId ?? undefined}
            disabled={!activeGroupId}
            label="Lock all in group"
          />
        </div>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-3">
        <Metric
          label="Anchored boats"
          value={String(anchors.length)}
          accent={anchors.length > 0 ? 'emerald' : 'neutral'}
        />
        <Metric
          label="Group active"
          value={hasGroupContext ? group?.name ?? `#${activeGroupId}` : '—'}
          accent={hasGroupContext ? 'blue' : 'neutral'}
        />
        <Metric
          label="Cameras"
          value={cameraIds.length > 0 ? String(cameraIds.length) : '—'}
          accent="neutral"
        />
      </div>

      {anchors.length > 0 ? (
        <div className="border-t border-gray-200 px-4 pb-4 pt-3 dark:border-white/5">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">
            Đang giữ ID ({anchors.length})
          </p>
          <ul className="space-y-1.5">
            {anchors.slice(0, 5).map((anchor) => (
              <li
                key={anchor.global_id}
                className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-[11px] dark:bg-white/5"
              >
                <div className="flex items-center gap-2 font-mono">
                  <span className="font-bold text-gray-900 dark:text-white">
                    {anchor.ship_id ?? '—'}
                  </span>
                  <span className="text-gray-400">
                    cam {anchor.cam_a_id}
                    {anchor.cam_b_id != null ? ` ↔ ${anchor.cam_b_id}` : ''}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[10px] font-mono uppercase">
                  <span className="text-gray-500">
                    Score A {anchor.last_score_a.toFixed(2)} / B {anchor.last_score_b.toFixed(2)}
                  </span>
                  <span className="text-gray-400">{formatRelative(anchor.last_seen_ts)} ago</span>
                </div>
              </li>
            ))}
          </ul>
          {anchors.length > 5 ? (
            <p className="mt-2 text-[10px] text-gray-500">+ {anchors.length - 5} khác…</p>
          ) : null}
        </div>
      ) : null}

      {!isRunning ? (
        <div className="border-t border-gray-200 px-4 py-3 text-[11px] text-gray-500 dark:border-white/5 dark:text-gray-400">
          Pipeline chưa chạy. Bạn vẫn có thể lock nền từ trang cấu hình Camera Group (chụp adhoc qua RTSP).
        </div>
      ) : !activeGroupId ? (
        <div className={cn(
          'border-t border-gray-200 px-4 py-3 text-[11px] text-amber-600 dark:border-white/5 dark:text-amber-400',
        )}>
          Pipeline đang chạy single camera. Seam anchor chỉ hoạt động trong group hybrid (≥ 2 camera).
        </div>
      ) : null}
    </div>
  );
};

const Metric: React.FC<{
  label: string;
  value: string;
  accent: 'neutral' | 'emerald' | 'blue';
}> = ({ label, value, accent }) => {
  const accentClasses = {
    neutral: 'text-gray-900 dark:text-white',
    emerald: 'text-emerald-500',
    blue: 'text-blue-500',
  } as const;
  return (
    <div className="rounded-xl bg-gray-50 px-3 py-3 dark:bg-white/[0.03]">
      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{label}</p>
      <p className={cn('mt-1 text-lg font-extrabold tracking-tight', accentClasses[accent])}>
        {value}
      </p>
    </div>
  );
};

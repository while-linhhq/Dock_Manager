import React, { useEffect, useMemo, useState } from 'react';
import { cameraGroupsApi } from '../services/camera-groups-api';
import { useCameraStream } from '../hooks/useCameraStream';
import type {
  CalibrationPointPair,
  CameraGroupMember,
  PairMatchStat,
  StitchMetadata,
} from '../types/fusion.types';

const getPairKey = (sourceCameraId: number, targetCameraId: number) =>
  `${sourceCameraId}-${targetCameraId}`;

export const CalibrationPanel: React.FC<{
  groupId?: number | null;
  member?: CameraGroupMember;
  members: CameraGroupMember[];
  onMembersChange: (members: CameraGroupMember[]) => void;
  onCanvasChange?: (width: number, height: number) => void;
  onStitchMetadataChange?: (metadata: StitchMetadata | null) => void;
}> = ({ groupId, members, onMembersChange, onCanvasChange, onStitchMetadataChange }) => {
  const enabledMembers = useMemo(
    () => members.filter((item) => item.enabled),
    [members],
  );
  const memberByCameraId = useMemo(
    () => new Map(enabledMembers.map((item) => [item.camera_id, item])),
    [enabledMembers],
  );
  const enabledCameraIds = useMemo(
    () => enabledMembers.map((item) => item.camera_id),
    [enabledMembers],
  );
  const [cameraOrder, setCameraOrder] = useState<number[]>(
    () => enabledMembers.map((item) => item.camera_id),
  );
  const effectiveCameraOrder = useMemo(() => {
    const kept = cameraOrder.filter((cameraId) => enabledCameraIds.includes(cameraId));
    const added = enabledCameraIds.filter((cameraId) => !kept.includes(cameraId));
    return [...kept, ...added];
  }, [cameraOrder, enabledCameraIds]);
  const [referenceCameraId, setReferenceCameraId] = useState<number | null>(
    enabledMembers[0]?.camera_id ?? null,
  );
  const effectiveReferenceCameraId = referenceCameraId && effectiveCameraOrder.includes(referenceCameraId)
    ? referenceCameraId
    : effectiveCameraOrder[0] ?? null;
  const adjacentPairs = useMemo(
    () =>
      effectiveCameraOrder
        .slice(0, -1)
        .map((cameraId, index) => [cameraId, effectiveCameraOrder[index + 1]] as const),
    [effectiveCameraOrder],
  );
  const defaultPairKey = adjacentPairs[0]
    ? getPairKey(adjacentPairs[0][0], adjacentPairs[0][1])
    : '';
  const [selectedPairKey, setSelectedPairKey] = useState(defaultPairKey);
  const [pointsByPair, setPointsByPair] = useState<Record<string, CalibrationPointPair[]>>({});
  const [pendingSrc, setPendingSrc] = useState<[number, number] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pairStats, setPairStats] = useState<PairMatchStat[]>([]);
  const [isAutoCalibrating, setIsAutoCalibrating] = useState(false);
  const [isApplyingManualChain, setIsApplyingManualChain] = useState(false);
  const selectedPair = useMemo(
    () => adjacentPairs.find(([sourceId, targetId]) => getPairKey(sourceId, targetId) === selectedPairKey),
    [adjacentPairs, selectedPairKey],
  );
  const sourceCameraId = selectedPair?.[0] ?? null;
  const targetCameraId = selectedPair?.[1] ?? null;
  const sourceMember = sourceCameraId ? memberByCameraId.get(sourceCameraId) : undefined;
  const targetMember = targetCameraId ? memberByCameraId.get(targetCameraId) : undefined;
  const currentPoints = selectedPairKey ? pointsByPair[selectedPairKey] ?? [] : [];
  const { url: sourceUrl } = useCameraStream(sourceCameraId);
  const { url: targetUrl } = useCameraStream(targetCameraId);

  useEffect(() => {
    if (enabledCameraIds.length === 0) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setCameraOrder((current) => {
        const kept = current.filter((cameraId) => enabledCameraIds.includes(cameraId));
        const added = enabledCameraIds.filter((cameraId) => !kept.includes(cameraId));
        return [...kept, ...added];
      });
      setReferenceCameraId((current) =>
        current && enabledCameraIds.includes(current) ? current : enabledCameraIds[0],
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [enabledCameraIds]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (!selectedPairKey || !adjacentPairs.some(([sourceId, targetId]) => (
        getPairKey(sourceId, targetId) === selectedPairKey
      ))) {
        setSelectedPairKey(defaultPairKey);
        setPendingSrc(null);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [adjacentPairs, defaultPairKey, selectedPairKey]);

  const moveCamera = (cameraId: number, direction: -1 | 1) => {
    setCameraOrder((current) => {
      const index = current.indexOf(cameraId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.length) {
        return current;
      }
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
    setPendingSrc(null);
  };

  const addPoint = (kind: 'src' | 'target', event: React.MouseEvent<HTMLDivElement>) => {
    if (!selectedPairKey) {
      setMessage('Chọn một cặp camera liền kề trước.');
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const point: [number, number] = [
      Math.round(event.clientX - rect.left),
      Math.round(event.clientY - rect.top),
    ];
    if (kind === 'src') {
      setPendingSrc(point);
      return;
    }
    if (!pendingSrc) {
      setMessage('Chọn điểm trên camera nguồn trước.');
      return;
    }
    setPointsByPair((current) => ({
      ...current,
      [selectedPairKey]: [...(current[selectedPairKey] ?? []), { src: pendingSrc, dst: point }],
    }));
    setPendingSrc(null);
  };

  const removeLastPoint = () => {
    if (!selectedPairKey) {
      return;
    }
    setPointsByPair((current) => ({
      ...current,
      [selectedPairKey]: (current[selectedPairKey] ?? []).slice(0, -1),
    }));
    setPendingSrc(null);
  };

  const runAutoCalibrate = async () => {
    if (!groupId) {
      setMessage('Lưu group trước, sau đó chạy Auto Calibrate.');
      return;
    }
    if (enabledMembers.length < 2) {
      setMessage('Cần ít nhất 2 camera đang enabled.');
      return;
    }
    setIsAutoCalibrating(true);
    setMessage(null);
    try {
      const result = await cameraGroupsApi.autoCalibrate(groupId, {
        referenceCameraId: effectiveReferenceCameraId,
        cameraOrder: effectiveCameraOrder,
      });
      setPairStats(result.pair_stats);
      const group = await cameraGroupsApi.get(groupId);
      onMembersChange(group.members);
      onCanvasChange?.(result.canvas_width, result.canvas_height);
      onStitchMetadataChange?.(group.stitch_metadata ?? result.stitch_metadata ?? null);
      onStitchMetadataChange?.(group.stitch_metadata ?? result.stitch_metadata ?? null);
      setReferenceCameraId(result.reference_camera_id);
      setMessage(
        `Auto calibrated panorama: ${result.canvas_width}x${result.canvas_height}, reference camera ${result.reference_camera_id}.`,
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Auto calibrate failed');
    } finally {
      setIsAutoCalibrating(false);
    }
  };

  const applyManualChain = async () => {
    if (!groupId) {
      setMessage('Lưu group trước, sau đó apply manual chain.');
      return;
    }
    const missingPairs = adjacentPairs
      .filter(([sourceId, targetId]) => (pointsByPair[getPairKey(sourceId, targetId)] ?? []).length < 4)
      .map(([sourceId, targetId]) => `${sourceId}-${targetId}`);
    if (missingPairs.length > 0) {
      setMessage(`Cần ít nhất 4 cặp điểm cho các edge: ${missingPairs.join(', ')}.`);
      return;
    }
    setIsApplyingManualChain(true);
    setMessage(null);
    try {
      const result = await cameraGroupsApi.manualPairChain(groupId, {
        reference_camera_id: effectiveReferenceCameraId,
        camera_order: effectiveCameraOrder,
        pairs: adjacentPairs.map(([sourceId, targetId]) => ({
          source_camera_id: sourceId,
          target_camera_id: targetId,
          points: pointsByPair[getPairKey(sourceId, targetId)] ?? [],
        })),
      });
      setPairStats(result.pair_stats);
      const group = await cameraGroupsApi.get(groupId);
      onMembersChange(group.members);
      onCanvasChange?.(result.canvas_width, result.canvas_height);
      setReferenceCameraId(result.reference_camera_id);
      setPendingSrc(null);
      setMessage(
        `Manual chain applied: ${result.canvas_width}x${result.canvas_height}, reference camera ${result.reference_camera_id}.`,
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Manual chain failed');
    } finally {
      setIsApplyingManualChain(false);
    }
  };

  if (enabledMembers.length === 0) {
    return (
      <div className="rounded-2xl border border-gray-200 p-4 text-sm text-gray-500 dark:border-white/10">
        Thêm và enable ít nhất 2 camera để panorama calibration.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#121214]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
            Panorama Calibration
          </p>
          <p className="text-xs text-gray-500">
            Cấu hình thứ tự camera, backend chỉ match hoặc chain các cặp liền kề theo thứ tự đó.
          </p>
        </div>
        <button
          type="button"
          className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-50"
          disabled={isAutoCalibrating || !groupId || cameraOrder.length < 2}
          onClick={runAutoCalibrate}
        >
          {isAutoCalibrating ? 'Auto calibrating...' : 'Auto Calibrate'}
        </button>
      </div>

      <div className="mb-4 grid gap-3 md:grid-cols-2">
        <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
          Reference Camera
          <select
            className="mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white"
            value={effectiveReferenceCameraId ?? ''}
            onChange={(event) => {
              setReferenceCameraId(Number(event.target.value));
              setPendingSrc(null);
            }}
          >
            {effectiveCameraOrder.map((cameraId) => {
              const item = memberByCameraId.get(cameraId);
              return (
                <option key={cameraId} value={cameraId}>
                  {item?.camera?.camera_name ?? `Camera ${cameraId}`}
                </option>
              );
            })}
          </select>
        </label>
        <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
          Adjacent Pair
          <select
            className="mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white"
            value={selectedPairKey}
            onChange={(event) => {
              setSelectedPairKey(event.target.value);
              setPendingSrc(null);
            }}
          >
            {adjacentPairs.map(([sourceId, targetId]) => (
              <option key={getPairKey(sourceId, targetId)} value={getPairKey(sourceId, targetId)}>
                Camera {sourceId} {'->'} Camera {targetId}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mb-4 rounded-xl border border-gray-200 p-3 dark:border-white/10">
        <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">
          Camera order
        </p>
        <div className="grid gap-2">
          {effectiveCameraOrder.map((cameraId, index) => {
            const item = memberByCameraId.get(cameraId);
            return (
              <div
                key={cameraId}
                className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2 text-xs dark:bg-white/5"
              >
                <span className="font-semibold text-gray-700 dark:text-gray-200">
                  {index + 1}. {item?.camera?.camera_name ?? `Camera ${cameraId}`}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="rounded-lg border border-gray-200 px-2 py-1 text-gray-600 disabled:opacity-40 dark:border-white/10 dark:text-gray-300"
                    disabled={index === 0}
                    onClick={() => moveCamera(cameraId, -1)}
                  >
                    Up
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-gray-200 px-2 py-1 text-gray-600 disabled:opacity-40 dark:border-white/10 dark:text-gray-300"
                    disabled={index === effectiveCameraOrder.length - 1}
                    onClick={() => moveCamera(cameraId, 1)}
                  >
                    Down
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-[11px] text-gray-500">
          Adjacent pairs: {adjacentPairs.map(([sourceId, targetId]) => `${sourceId}-${targetId}`).join(', ')}
        </p>
      </div>

      {pairStats.length > 0 ? (
        <div className="mb-4 rounded-xl border border-gray-200 p-3 dark:border-white/10">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">
            Match stats
          </p>
          <div className="grid gap-2 md:grid-cols-2">
            {pairStats.map((stat) => (
              <div
                key={`${stat.source_camera_id}-${stat.target_camera_id}`}
                className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-white/5 dark:text-gray-300"
              >
                Camera {stat.source_camera_id} ↔ {stat.target_camera_id}: {stat.inliers}/{stat.matches}{' '}
                inliers ({Math.round(stat.confidence * 100)}%)
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <CameraPointPicker
          title={`Source: ${sourceMember?.camera?.camera_name ?? `Camera ${sourceCameraId ?? ''}`}`}
          url={sourceUrl}
          onPick={(event) => addPoint('src', event)}
        />
        <CameraPointPicker
          title={`Target: ${targetMember?.camera?.camera_name ?? `Camera ${targetCameraId ?? ''}`}`}
          url={targetUrl}
          onPick={(event) => addPoint('target', event)}
        />
      </div>
      <div className="mt-4 flex items-center justify-between gap-4">
        <p className="text-xs text-gray-500">
          Current pair: {currentPoints.length} point pairs.{' '}
          {pendingSrc ? 'Đã chọn source, chọn điểm tương ứng trên target.' : ''}
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-xl border border-gray-200 px-4 py-2 text-xs font-bold uppercase tracking-widest text-gray-600 disabled:opacity-50 dark:border-white/10 dark:text-gray-300"
            disabled={currentPoints.length === 0}
            onClick={removeLastPoint}
          >
            Undo point
          </button>
          <button
            type="button"
            className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-50"
            disabled={isApplyingManualChain || adjacentPairs.length === 0}
            onClick={applyManualChain}
          >
            {isApplyingManualChain ? 'Applying...' : 'Apply manual chain'}
          </button>
        </div>
      </div>
      {message ? <p className="mt-2 text-[11px] text-blue-500">{message}</p> : null}
    </div>
  );
};

const CameraPointPicker: React.FC<{
  title: string;
  url: string | null;
  onPick: (event: React.MouseEvent<HTMLDivElement>) => void;
}> = ({ title, url, onPick }) => (
  <div>
    <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500">{title}</p>
    <div
      className="relative flex h-64 cursor-crosshair items-center justify-center overflow-hidden rounded-xl bg-black"
      onClick={onPick}
    >
      {url ? <img src={url} alt="" className="h-full w-full object-contain" /> : null}
    </div>
  </div>
);

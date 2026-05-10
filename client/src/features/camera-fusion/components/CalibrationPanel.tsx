import React, { useEffect, useMemo, useState } from 'react';
import { cameraGroupsApi } from '../services/camera-groups-api';
import { useCameraStream } from '../hooks/useCameraStream';
import type { CalibrationPointPair, CameraGroupMember, PairMatchStat } from '../types/fusion.types';

export const CalibrationPanel: React.FC<{
  groupId?: number | null;
  member?: CameraGroupMember;
  members: CameraGroupMember[];
  onMembersChange: (members: CameraGroupMember[]) => void;
  onCanvasChange?: (width: number, height: number) => void;
}> = ({ groupId, member, members, onMembersChange, onCanvasChange }) => {
  const enabledMembers = useMemo(
    () => members.filter((item) => item.enabled),
    [members],
  );
  const [referenceCameraId, setReferenceCameraId] = useState<number | null>(
    enabledMembers[0]?.camera_id ?? null,
  );
  const [sourceCameraId, setSourceCameraId] = useState<number | null>(
    member?.camera_id ?? enabledMembers.find((item) => item.camera_id !== referenceCameraId)?.camera_id ?? null,
  );
  const [points, setPoints] = useState<CalibrationPointPair[]>([]);
  const [pendingSrc, setPendingSrc] = useState<[number, number] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pairStats, setPairStats] = useState<PairMatchStat[]>([]);
  const [isAutoCalibrating, setIsAutoCalibrating] = useState(false);
  const [isRefining, setIsRefining] = useState(false);
  const sourceMember = members.find((item) => item.camera_id === sourceCameraId);
  const referenceMember = members.find((item) => item.camera_id === referenceCameraId);
  const { url: sourceUrl } = useCameraStream(sourceCameraId);
  const { url: referenceUrl } = useCameraStream(referenceCameraId);

  useEffect(() => {
    if (enabledMembers.length === 0) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setReferenceCameraId((current) =>
        current && enabledMembers.some((item) => item.camera_id === current)
          ? current
          : enabledMembers[0].camera_id,
      );
      setSourceCameraId((current) =>
        current && enabledMembers.some((item) => item.camera_id === current)
          ? current
          : enabledMembers[1]?.camera_id ?? enabledMembers[0].camera_id,
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [enabledMembers]);

  const addPoint = (kind: 'src' | 'reference', event: React.MouseEvent<HTMLDivElement>) => {
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
      setMessage('Chọn điểm trên camera cần refine trước.');
      return;
    }
    setPoints([...points, { src: pendingSrc, dst: point }]);
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
      const result = await cameraGroupsApi.autoCalibrate(groupId, referenceCameraId);
      setPairStats(result.pair_stats);
      const group = await cameraGroupsApi.get(groupId);
      onMembersChange(group.members);
      onCanvasChange?.(result.canvas_width, result.canvas_height);
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

  const refine = async () => {
    if (!sourceMember || !referenceMember || sourceMember.camera_id === referenceMember.camera_id) {
      setMessage('Chọn 2 camera khác nhau để manual refine.');
      return;
    }
    if (points.length < 4) {
      setMessage('Cần ít nhất 4 cặp điểm.');
      return;
    }
    if (!groupId) {
      setMessage('Lưu group trước, sau đó manual refine.');
      return;
    }
    setIsRefining(true);
    try {
      const result = await cameraGroupsApi.manualRefine(groupId, sourceMember.camera_id, points);
      onMembersChange(
        members.map((item) =>
          item.camera_id === sourceMember.camera_id
            ? { ...item, homography: result.homography, calibration_points: points }
            : item,
        ),
      );
      setPoints([]);
      setPendingSrc(null);
      setMessage(`Manual refined (${result.inliers} inliers).`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Manual refine failed');
    } finally {
      setIsRefining(false);
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
            Auto stitch trước, sau đó chọn cùng một điểm vật lý trên 2 camera để refine thủ công.
          </p>
        </div>
        <button
          type="button"
          className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white disabled:opacity-50"
          disabled={isAutoCalibrating || !groupId}
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
            value={referenceCameraId ?? ''}
            onChange={(event) => {
              setReferenceCameraId(Number(event.target.value));
              setPoints([]);
              setPendingSrc(null);
            }}
          >
            {enabledMembers.map((item) => (
              <option key={item.camera_id} value={item.camera_id}>
                {item.camera?.camera_name ?? `Camera ${item.camera_id}`}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
          Camera cần refine
          <select
            className="mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white"
            value={sourceCameraId ?? ''}
            onChange={(event) => {
              setSourceCameraId(Number(event.target.value));
              setPoints([]);
              setPendingSrc(null);
            }}
          >
            {enabledMembers.map((item) => (
              <option key={item.camera_id} value={item.camera_id}>
                {item.camera?.camera_name ?? `Camera ${item.camera_id}`}
              </option>
            ))}
          </select>
        </label>
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
          title={`Reference: ${referenceMember?.camera?.camera_name ?? `Camera ${referenceCameraId ?? ''}`}`}
          url={referenceUrl}
          onPick={(event) => addPoint('reference', event)}
        />
      </div>
      <div className="mt-4 flex items-center justify-between gap-4">
        <p className="text-xs text-gray-500">
          {points.length} point pairs. {pendingSrc ? 'Đã chọn source, chọn điểm tương ứng trên reference.' : ''}
        </p>
        <button
          type="button"
          className="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white"
          disabled={isRefining}
          onClick={refine}
        >
          {isRefining ? 'Refining...' : 'Manual refine'}
        </button>
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

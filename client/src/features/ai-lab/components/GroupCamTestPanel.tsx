import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FileVideo, Grid2X2, Loader2, Play, Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cameraGroupsApi } from '../../camera-fusion/services/camera-groups-api';
import type { CameraGroup } from '../../camera-fusion/types/fusion.types';
import { aiLabApi } from '../services/aiLabApi';
import type { LabGroupCamResponse, LabGroupCameraFrame } from '../types/ai-lab.types';

const ACCEPT = 'video/mp4,video/webm,video/quicktime,video/x-msvideo,video/x-matroska';
const ALLOWED_VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.avi', '.mkv'];

type UploadRow = {
  id: string;
  cameraId: string;
  file: File | null;
  previewUrl: string | null;
};

function imageDataUrl(base64?: string | null): string | null {
  return base64 ? `data:image/jpeg;base64,${base64}` : null;
}

function isAllowedVideo(file: File): boolean {
  const name = file.name.toLowerCase();
  return file.type.toLowerCase().startsWith('video/') || ALLOWED_VIDEO_EXTENSIONS.some((ext) => name.endsWith(ext));
}

function newRow(): UploadRow {
  return { id: crypto.randomUUID(), cameraId: '', file: null, previewUrl: null };
}

export const GroupCamTestPanel: React.FC = () => {
  const inputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const [groups, setGroups] = useState<CameraGroup[]>([]);
  const [groupId, setGroupId] = useState<string>('');
  const [rows, setRows] = useState<UploadRow[]>([newRow(), newRow()]);
  const [frameStride, setFrameStride] = useState(8);
  const [enableOcr, setEnableOcr] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LabGroupCamResponse | null>(null);
  const [frameIdx, setFrameIdx] = useState(0);
  const [selectedCameraId, setSelectedCameraId] = useState<number | 'fused'>('fused');
  const [draggingRowId, setDraggingRowId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    cameraGroupsApi.list(true)
      .then((items) => {
        if (!alive) return;
        setGroups(items);
        if (!groupId && items[0]) {
          setGroupId(String(items[0].id));
        }
      })
      .catch(() => undefined);
    return () => { alive = false; };
  }, [groupId]);

  const selectedGroup = useMemo(
    () => groups.find((group) => String(group.id) === groupId) ?? null,
    [groups, groupId],
  );

  const cameraOptions = selectedGroup?.members.filter((member) => member.enabled) ?? [];
  const activeFrame = result?.frames[frameIdx] ?? null;
  const activeCameraFrame: LabGroupCameraFrame | null = activeFrame && selectedCameraId !== 'fused'
    ? activeFrame.cameras.find((camera) => camera.camera_id === selectedCameraId) ?? null
    : null;
  const previewUrl = selectedCameraId === 'fused'
    ? imageDataUrl(activeFrame?.fused_jpeg_base64 ?? activeFrame?.cameras[0]?.jpeg_base64)
    : imageDataUrl(activeCameraFrame?.jpeg_base64);

  const updateRow = (id: string, patch: Partial<UploadRow>) => {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  const setRowFile = (id: string, file: File | null) => {
    setError(null);
    if (file && !isAllowedVideo(file)) {
      setError(`Định dạng video không hỗ trợ: ${file.name}`);
      return;
    }
    updateRow(id, {
      file,
      previewUrl: file ? URL.createObjectURL(file) : null,
    });
    setResult(null);
    setFrameIdx(0);
  };

  const removeRow = (id: string) => {
    setRows((current) => (current.length <= 2 ? current : current.filter((row) => row.id !== id)));
  };

  const handleDrop = (rowId: string, event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setDraggingRowId(null);
    setRowFile(rowId, event.dataTransfer.files?.[0] ?? null);
  };

  const runTest = async () => {
    const items = rows
      .filter((row) => row.file && row.cameraId)
      .map((row) => ({ cameraId: Number(row.cameraId), file: row.file as File }));
    if (items.length < 2) {
      setError('Cần chọn ít nhất 2 video camera.');
      return;
    }
    setIsRunning(true);
    setError(null);
    try {
      const response = await aiLabApi.runGroupCamTest(items, {
        groupId: groupId ? Number(groupId) : null,
        frameStride,
        maxOutputFrames: 48,
        enableOcr,
      });
      setResult(response);
      setFrameIdx(0);
      setSelectedCameraId(response.frames[0]?.fused_jpeg_base64 ? 'fused' : response.frames[0]?.cameras[0]?.camera_id ?? 'fused');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chạy Group Cam Test thất bại');
      setResult(null);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-5 space-y-4">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-900 dark:text-white">
            Group Cam Test
          </h3>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Import nhiều video quay cùng thời điểm để replay pipeline theo từng frame, xem preview từng camera hoặc fused layout.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-[260px_160px_1fr]">
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Camera group</label>
            <select
              value={groupId}
              onChange={(event) => setGroupId(event.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-3 py-2 text-sm"
            >
              <option value="">Không dùng fused layout</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>{group.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Bước frame</label>
            <input
              type="number"
              min={1}
              max={30}
              value={frameStride}
              onChange={(event) => setFrameStride(Math.max(1, Number(event.target.value) || 1))}
              className="mt-1 w-full rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-3 py-2 text-sm"
            />
          </div>

          <label className="flex items-end gap-2 pb-2 text-xs text-gray-600 dark:text-gray-300">
            <input
              type="checkbox"
              checked={enableOcr}
              onChange={(event) => setEnableOcr(event.target.checked)}
              className="rounded border-gray-300"
            />
            Bật OCR (Paddle)
          </label>
        </div>

        <div className="space-y-3">
          {rows.map((row, index) => (
            <div key={row.id} className="grid gap-3 rounded-xl bg-gray-50 dark:bg-white/[0.03] p-3 lg:grid-cols-[220px_1fr_40px]">
              <select
                value={row.cameraId}
                onChange={(event) => updateRow(row.id, { cameraId: event.target.value })}
                className="rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-3 py-2 text-sm"
              >
                <option value="">Camera #{index + 1}</option>
                {cameraOptions.map((member) => (
                  <option key={member.camera_id} value={member.camera_id}>
                    {member.camera?.name ?? `Camera ${member.camera_id}`}
                  </option>
                ))}
              </select>
              <div
                role="button"
                tabIndex={0}
                onClick={() => inputRefs.current[row.id]?.click()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    inputRefs.current[row.id]?.click();
                  }
                }}
                onDragEnter={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setDraggingRowId(row.id);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  event.dataTransfer.dropEffect = 'copy';
                  setDraggingRowId(row.id);
                }}
                onDragLeave={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  const next = event.relatedTarget as Node | null;
                  if (next && event.currentTarget.contains(next)) return;
                  setDraggingRowId(null);
                }}
                onDrop={(event) => handleDrop(row.id, event)}
                className={`min-h-36 cursor-pointer rounded-xl border border-dashed p-3 transition-colors ${draggingRowId === row.id ? 'border-cyan-500 bg-cyan-500/10' : 'border-gray-300 bg-white dark:border-white/10 dark:bg-white/[0.03]'}`}
              >
                <input
                  ref={(element) => { inputRefs.current[row.id] = element; }}
                  type="file"
                  accept={ACCEPT}
                  className="hidden"
                  onChange={(event) => setRowFile(row.id, event.target.files?.[0] ?? null)}
                />
                {row.previewUrl ? (
                  <div className="grid gap-3 md:grid-cols-[220px_1fr]">
                    <video src={row.previewUrl} controls preload="metadata" className="h-32 w-full rounded-lg bg-black object-contain" />
                    <div className="flex flex-col justify-center text-xs text-gray-600 dark:text-gray-300">
                      <p className="font-semibold text-gray-900 dark:text-white">{row.file?.name}</p>
                      <p className="mt-1 text-gray-500">{row.file ? `${(row.file.size / 1024 / 1024).toFixed(1)} MB` : ''}</p>
                      <p className="mt-2 text-[11px] text-gray-500">Kéo file khác vào đây để thay video.</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex h-full min-h-28 flex-col items-center justify-center gap-2 text-center text-gray-500">
                    <FileVideo className="h-8 w-8 text-cyan-500" />
                    <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">Kéo thả video camera vào đây</p>
                    <p className="text-[11px]">hoặc bấm để chọn · mp4, webm, mov, avi, mkv</p>
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => removeRow(row.id)}
                disabled={rows.length <= 2}
                className="inline-flex items-center justify-center rounded-lg text-gray-400 hover:text-red-500 disabled:opacity-40"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <Button type="button" variant="outline" onClick={() => setRows((current) => [...current, newRow()])}>
            <Plus className="h-4 w-4" /> Thêm camera
          </Button>
          <Button type="button" onClick={() => void runTest()} disabled={isRunning} className="inline-flex items-center gap-2">
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Chạy Group Cam Test
          </Button>
        </div>

        {error ? <p className="text-sm text-red-500">{error}</p> : null}
      </div>

      {result ? (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-6">
          <div className="rounded-2xl border border-gray-200 dark:border-white/10 overflow-hidden bg-black">
            {previewUrl ? (
              <img src={previewUrl} alt="Group cam preview" className="w-full max-h-[min(78vh,920px)] object-contain bg-black" />
            ) : (
              <div className="flex h-80 items-center justify-center text-gray-500"><Grid2X2 className="h-12 w-12 opacity-20" /></div>
            )}
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4 text-xs font-mono space-y-1 text-gray-600 dark:text-gray-300">
              <p>Group: {result.group_name || '—'}</p>
              <p>Số camera: {result.camera_count}</p>
              <p>Frame trả về: {result.sampled_frames}</p>
              <p>Stride: {result.frame_stride}</p>
              {activeFrame ? <p>Thời điểm: {activeFrame.time_sec.toFixed(2)}s</p> : null}
              {result.ocr_enabled ? <p>OCR: bật · device {result.ocr_device ?? '—'}</p> : <p>OCR: tắt</p>}
            </div>

            {result.frames.length > 1 ? (
              <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4">
                <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Frame {frameIdx + 1} / {result.frames.length}</label>
                <input type="range" min={0} max={Math.max(0, result.frames.length - 1)} value={frameIdx} onChange={(event) => setFrameIdx(Number(event.target.value))} className="mt-2 w-full" />
              </div>
            ) : null}

            {activeFrame ? (
              <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4 space-y-3">
                <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Preview</label>
                <select
                  value={selectedCameraId}
                  onChange={(event) => setSelectedCameraId(event.target.value === 'fused' ? 'fused' : Number(event.target.value))}
                  className="w-full rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-3 py-2 text-sm"
                >
                  <option value="fused">Fused layout</option>
                  {activeFrame.cameras.map((camera) => (
                    <option key={camera.camera_id} value={camera.camera_id}>
                      Camera {camera.camera_id} · {camera.filename}
                    </option>
                  ))}
                </select>

                <div className="max-h-80 space-y-2 overflow-y-auto">
                  {(selectedCameraId === 'fused' ? activeFrame.cameras : activeCameraFrame ? [activeCameraFrame] : []).map((camera) => (
                    <div key={camera.camera_id} className="rounded-lg bg-gray-50 dark:bg-white/[0.03] px-3 py-2 text-[11px] font-mono">
                      <p className="text-gray-900 dark:text-white">Camera {camera.camera_id}</p>
                      <p className="text-gray-500">{camera.filename}</p>
                      <p className="text-gray-500">Detections: {camera.boats.length}</p>
                      {camera.boats.map((boat) => (
                        <p key={`${camera.camera_id}-${boat.track_id}-${boat.box.join('-')}`} className="text-gray-400">
                          Track {boat.track_id} · {boat.state} · ship_id {boat.ship_id ?? '—'} · bbox [{boat.box.join(', ')}]
                        </p>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

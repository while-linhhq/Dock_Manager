import React, { useMemo, useState } from 'react';
import { Crop, Loader2, Play, Ship } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { FileDropzone } from './FileDropzone';
import { aiLabApi } from '../services/aiLabApi';
import { cropBboxAndDownload } from '../utils/crop-bbox-download';
import type { LabBoatDetection, LabDetectionFrame, LabDetectionResponse } from '../types/ai-lab.types';

const ACCEPT = 'image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime,video/x-msvideo';
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.mp4', '.webm', '.mov', '.avi', '.mkv'];

function frameDataUrl(frame: LabDetectionFrame): string {
  return `data:image/jpeg;base64,${frame.jpeg_base64}`;
}

export const DetectionLabPanel: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [frameStride, setFrameStride] = useState(8);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LabDetectionResponse | null>(null);
  const [frameIdx, setFrameIdx] = useState(0);
  const [savingTrackId, setSavingTrackId] = useState<string | null>(null);
  const [cropError, setCropError] = useState<string | null>(null);

  const activeFrame = result?.frames[frameIdx] ?? null;
  const isVideo = result?.media_type === 'video';

  const summary = useMemo(() => {
    if (!activeFrame) {
      return null;
    }
    const confirmed = activeFrame.boats.filter((b) => b.state === 'CONFIRMED').length;
    return {
      boats: activeFrame.boats.length,
      confirmed,
    };
  }, [activeFrame]);

  const onPickFile = (picked: File | null) => {
    setFile(picked);
    setResult(null);
    setFrameIdx(0);
    setError(null);
  };

  const runTest = async () => {
    if (!file) {
      return;
    }
    setIsRunning(true);
    setError(null);
    try {
      const response = await aiLabApi.detectMedia(file, {
        frameStride,
        maxOutputFrames: 48,
      });
      setResult(response);
      setFrameIdx(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chạy test thất bại');
      setResult(null);
    } finally {
      setIsRunning(false);
    }
  };

  const saveBboxCrop = async (boat: LabBoatDetection) => {
    if (!file || !result || !activeFrame) {
      return;
    }
    setSavingTrackId(boat.track_id);
    setCropError(null);
    try {
      await cropBboxAndDownload({
        file,
        mediaType: result.media_type,
        box: boat.box,
        timeSec: activeFrame.time_sec,
        frameIndex: activeFrame.frame_index,
        sourceFilename: result.filename,
        trackId: boat.track_id,
      });
    } catch (err) {
      setCropError(err instanceof Error ? err.message : 'Cắt & lưu thất bại');
    } finally {
      setSavingTrackId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-5 space-y-4">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-900 dark:text-white">
            Kiểm tra nhận diện (pipeline offline)
          </h3>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Kéo thả hoặc chọn ảnh/video — chạy YOLO + tracker giống pipeline, trả frame có overlay bbox/track.
          </p>
        </div>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
          <FileDropzone
            accept={ACCEPT}
            allowedExtensions={ALLOWED_EXTENSIONS}
            file={file}
            onFileChange={onPickFile}
            emptyTitle="Kéo thả ảnh / video vào đây"
            emptyHint="hoặc bấm để chọn · jpg, png, webp, mp4, mov, avi"
            accent="blue"
          />

          <div className="w-full lg:w-48">
            <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
              Bước frame (video)
            </label>
            <input
              type="number"
              min={1}
              max={30}
              value={frameStride}
              onChange={(event) => setFrameStride(Math.max(1, Number(event.target.value) || 1))}
              className="mt-1 w-full rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 px-3 py-2 text-sm"
            />
          </div>

          <Button
            type="button"
            onClick={() => void runTest()}
            disabled={!file || isRunning}
            className="inline-flex items-center gap-2"
          >
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Chạy test
          </Button>
        </div>

        {error ? (
          <p className="text-sm text-red-500">{error}</p>
        ) : null}
      </div>

      {result ? (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-6">
          <div className="rounded-2xl border border-gray-200 dark:border-white/10 overflow-hidden bg-black">
            {activeFrame ? (
              <img
                src={frameDataUrl(activeFrame)}
                alt={`Lab frame ${activeFrame.frame_index}`}
                className="w-full max-h-[min(78vh,920px)] object-contain bg-black"
              />
            ) : (
              <div className="flex h-80 items-center justify-center text-gray-500">
                <Ship className="h-12 w-12 opacity-20" />
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4 text-xs font-mono space-y-1 text-gray-600 dark:text-gray-300">
              <p>File: {result.filename}</p>
              <p>Loại: {result.media_type}</p>
              <p>Tổng frame: {result.total_frames}</p>
              <p>Frame trả về: {result.sampled_frames}</p>
              {isVideo ? <p>Stride: {result.frame_stride ?? frameStride}</p> : null}
              {activeFrame ? <p>Thời điểm: {activeFrame.time_sec.toFixed(2)}s</p> : null}
              {summary ? (
                <p>
                  Tàu: {summary.boats} · CONFIRMED: {summary.confirmed}
                </p>
              ) : null}
            </div>

            {isVideo && result.frames.length > 1 ? (
              <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4">
                <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                  Frame {frameIdx + 1} / {result.frames.length}
                </label>
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, result.frames.length - 1)}
                  value={frameIdx}
                  onChange={(event) => setFrameIdx(Number(event.target.value))}
                  className="mt-2 w-full"
                />
              </div>
            ) : null}

            {activeFrame && activeFrame.boats.length > 0 ? (
              <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-[#121214] p-4 space-y-2 max-h-80 overflow-y-auto">
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                  Detections
                </p>
                {cropError ? (
                  <p className="text-[11px] text-red-500">{cropError}</p>
                ) : null}
                {activeFrame.boats.map((boat) => (
                  <div
                    key={`${boat.track_id}-${boat.box.join('-')}`}
                    className="rounded-lg bg-gray-50 dark:bg-white/[0.03] px-3 py-2 text-[11px] font-mono space-y-2"
                  >
                    <div>
                      <p className="text-gray-900 dark:text-white">Track {boat.track_id}</p>
                      <p className="text-gray-500">
                        {boat.state} · conf {(boat.confidence * 100).toFixed(1)}%
                      </p>
                      <p className="text-gray-500 truncate">
                        ship_id: {boat.ship_id ?? '—'}
                      </p>
                      <p className="text-gray-400">
                        bbox: [{boat.box.join(', ')}]
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      className="h-8 w-full text-[10px] font-bold uppercase tracking-widest inline-flex items-center justify-center gap-1.5"
                      disabled={!file || savingTrackId === boat.track_id}
                      onClick={() => void saveBboxCrop(boat)}
                    >
                      {savingTrackId === boat.track_id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Crop className="h-3.5 w-3.5" />
                      )}
                      Cắt &amp; lưu
                    </Button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

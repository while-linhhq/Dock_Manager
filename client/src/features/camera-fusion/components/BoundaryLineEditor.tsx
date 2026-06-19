import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '../../../components/Button/Button';
import { portApi } from '../../port/services/portApi';
import { ApiError } from '../../../services/httpClient';
import type { BoundaryLines, BoundaryPoint } from '../../../types/api.types';
import { useCameraSnapshot } from '../hooks/useCameraSnapshot';

type Point = { x: number; y: number };
type FrameRef = { w: number; h: number };

type Props = {
  cameraId: number;
};

type ActiveLine = 1 | 2;

function normalizeLegacyLine(raw: unknown): Point[] {
  if (Array.isArray(raw)) {
    return raw.map((p) => ({ x: Number(p.x), y: Number(p.y) }));
  }
  if (raw && typeof raw === 'object' && 'x1' in raw) {
    const seg = raw as { x1: number; y1: number; x2: number; y2: number };
    return [
      { x: seg.x1, y: seg.y1 },
      { x: seg.x2, y: seg.y2 },
    ];
  }
  return [];
}

function getImageFit(img: HTMLImageElement) {
  const w = img.clientWidth;
  const h = img.clientHeight;
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  if (nw <= 0 || nh <= 0 || w <= 0 || h <= 0) {
    return null;
  }
  const scale = Math.min(w / nw, h / nh);
  return {
    offsetX: (w - nw * scale) / 2,
    offsetY: (h - nh * scale) / 2,
    drawW: nw * scale,
    drawH: nh * scale,
  };
}

function toDisplayPoint(point: Point, frameRef: FrameRef, img: HTMLImageElement): Point {
  const fit = getImageFit(img);
  if (!fit || frameRef.w <= 0 || frameRef.h <= 0) {
    return point;
  }
  const sx = fit.drawW / frameRef.w;
  const sy = fit.drawH / frameRef.h;
  return {
    x: fit.offsetX + point.x * sx,
    y: fit.offsetY + point.y * sy,
  };
}

function polylineToDisplay(
  points: Point[],
  frameRef: FrameRef,
  img: HTMLImageElement,
): string {
  if (points.length < 2 || frameRef.w <= 0 || frameRef.h <= 0) {
    return '';
  }
  return points
    .map((point) => {
      const d = toDisplayPoint(point, frameRef, img);
      return `${d.x},${d.y}`;
    })
    .join(' ');
}

export const BoundaryLineEditor: React.FC<Props> = ({ cameraId }) => {
  const { url, isLoading } = useCameraSnapshot(cameraId);
  const imgRef = useRef<HTMLImageElement>(null);
  const [line1Points, setLine1Points] = useState<Point[]>([]);
  const [line2Points, setLine2Points] = useState<Point[]>([]);
  const [activeLine, setActiveLine] = useState<ActiveLine>(1);
  const [frameRef, setFrameRef] = useState<FrameRef>({ w: 0, h: 0 });
  const [displaySize, setDisplaySize] = useState({ w: 0, h: 0 });
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [renderTick, setRenderTick] = useState(0);

  const applyBoundaryLines = useCallback((lines: BoundaryLines) => {
    setLine1Points(normalizeLegacyLine(lines.line1));
    setLine2Points(normalizeLegacyLine(lines.line2));
    setFrameRef({ w: lines.frame_w, h: lines.frame_h });
  }, []);

  const syncDisplaySize = useCallback(() => {
    const img = imgRef.current;
    if (!img) {
      return;
    }
    setDisplaySize({ w: img.clientWidth, h: img.clientHeight });
    setRenderTick((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLine1Points([]);
    setLine2Points([]);
    setActiveLine(1);
    setFrameRef({ w: 0, h: 0 });
    setMessage(null);

    portApi
      .getCamera(cameraId)
      .then((camera) => {
        if (cancelled || !camera.boundary_lines) {
          return;
        }
        applyBoundaryLines(camera.boundary_lines);
      })
      .catch(() => {
        if (!cancelled) {
          setMessage('Không tải được cấu hình đường biên.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cameraId, applyBoundaryLines]);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) {
      return;
    }
    const observer = new ResizeObserver(() => syncDisplaySize());
    observer.observe(img);
    return () => observer.disconnect();
  }, [url, syncDisplaySize]);

  const toNative = (clientX: number, clientY: number): Point | null => {
    const img = imgRef.current;
    if (!img || frameRef.w <= 0 || frameRef.h <= 0) {
      return null;
    }
    const fit = getImageFit(img);
    if (!fit) {
      return null;
    }
    const rect = img.getBoundingClientRect();
    const localX = clientX - rect.left - fit.offsetX;
    const localY = clientY - rect.top - fit.offsetY;
    if (localX < 0 || localY < 0 || localX > fit.drawW || localY > fit.drawH) {
      return null;
    }
    return {
      x: Math.round((localX / fit.drawW) * frameRef.w),
      y: Math.round((localY / fit.drawH) * frameRef.h),
    };
  };

  const handleImageLoad = () => {
    const img = imgRef.current;
    if (!img) {
      return;
    }
    setFrameRef((previous) => {
      if (previous.w > 0 && previous.h > 0) {
        return previous;
      }
      return { w: img.naturalWidth, h: img.naturalHeight };
    });
    syncDisplaySize();
  };

  const handleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const native = toNative(event.clientX, event.clientY);
    if (!native) {
      return;
    }
    if (activeLine === 1) {
      setLine1Points((prev) => [...prev, native]);
    } else {
      setLine2Points((prev) => [...prev, native]);
    }
    setMessage(null);
  };

  const handleUndo = () => {
    if (activeLine === 1) {
      setLine1Points((prev) => prev.slice(0, -1));
    } else {
      setLine2Points((prev) => prev.slice(0, -1));
    }
    setMessage(null);
  };

  const handleClear = async () => {
    setIsSaving(true);
    try {
      await portApi.clearBoundaryLines(cameraId);
      setLine1Points([]);
      setLine2Points([]);
      setActiveLine(1);
      const img = imgRef.current;
      setFrameRef({
        w: img?.naturalWidth ?? 0,
        h: img?.naturalHeight ?? 0,
      });
      setMessage('Đã xóa đường biên.');
    } catch {
      setMessage('Xóa đường biên thất bại.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSave = async () => {
    const img = imgRef.current;
    const frameW = frameRef.w > 0 ? frameRef.w : img?.naturalWidth ?? 0;
    const frameH = frameRef.h > 0 ? frameRef.h : img?.naturalHeight ?? 0;
    if (line1Points.length < 2 || line2Points.length < 2 || frameW <= 0 || frameH <= 0) {
      setMessage('Mỗi đường cần ít nhất 2 điểm.');
      return;
    }
    const toBoundaryPoints = (pts: Point[]): BoundaryPoint[] =>
      pts.map((p) => ({ x: p.x, y: p.y }));
    const payload: BoundaryLines = {
      enabled: true,
      frame_w: Math.round(frameW),
      frame_h: Math.round(frameH),
      line1: toBoundaryPoints(line1Points),
      line2: toBoundaryPoints(line2Points),
    };
    setIsSaving(true);
    try {
      const saved = await portApi.setBoundaryLines(cameraId, payload);
      if (saved.boundary_lines) {
        applyBoundaryLines(saved.boundary_lines);
      } else {
        setFrameRef({ w: frameW, h: frameH });
      }
      setMessage('Đã lưu đường biên.');
    } catch (error) {
      const detail = error instanceof ApiError ? error.message : null;
      setMessage(detail ? `Lưu thất bại: ${detail}` : 'Lưu đường biên thất bại.');
    } finally {
      setIsSaving(false);
    }
  };

  const img = imgRef.current;
  const line1Polyline =
    img && frameRef.w > 0 ? polylineToDisplay(line1Points, frameRef, img) : '';
  const line2Polyline =
    img && frameRef.w > 0 ? polylineToDisplay(line2Points, frameRef, img) : '';
  void renderTick;

  const activePoints = activeLine === 1 ? line1Points : line2Points;

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#121214]">
      <div className="mb-4">
        <p className="text-xs font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
          Vẽ đường biên (camera {cameraId})
        </p>
        <p className="text-xs text-gray-500">
          Chọn line1/line2, click thêm điểm để tạo đường gấp khúc. Tâm bbox đi line1 → line2 = vào cảng;
          ngược lại = ra cảng.
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <button
          type="button"
          className={`rounded-lg px-3 py-1 text-xs font-semibold ${
            activeLine === 1
              ? 'bg-green-600 text-white'
              : 'border border-gray-200 text-gray-600 dark:border-white/10 dark:text-gray-300'
          }`}
          onClick={() => setActiveLine(1)}
        >
          Line 1 — IN ({line1Points.length} điểm)
        </button>
        <button
          type="button"
          className={`rounded-lg px-3 py-1 text-xs font-semibold ${
            activeLine === 2
              ? 'bg-red-600 text-white'
              : 'border border-gray-200 text-gray-600 dark:border-white/10 dark:text-gray-300'
          }`}
          onClick={() => setActiveLine(2)}
        >
          Line 2 — OUT ({line2Points.length} điểm)
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-gray-500">Đang tải snapshot...</p>
      ) : null}

      {url ? (
        <div
          className="relative inline-block max-w-full cursor-crosshair"
          onClick={handleClick}
          role="presentation"
        >
          <img
            ref={imgRef}
            src={url}
            alt={`Camera ${cameraId} snapshot`}
            className="max-h-[420px] w-full object-contain"
            onLoad={handleImageLoad}
          />
          {displaySize.w > 0 && displaySize.h > 0 && img ? (
            <svg
              className="pointer-events-none absolute inset-0 h-full w-full"
              viewBox={`0 0 ${displaySize.w} ${displaySize.h}`}
            >
              {line1Polyline ? (
                <polyline
                  points={line1Polyline}
                  fill="none"
                  stroke="#00c853"
                  strokeWidth={2}
                />
              ) : null}
              {line2Polyline ? (
                <polyline
                  points={line2Polyline}
                  fill="none"
                  stroke="#ff1744"
                  strokeWidth={2}
                />
              ) : null}
              {line1Points.map((point, index) => {
                const d = toDisplayPoint(point, frameRef, img);
                return (
                  <circle
                    key={`l1-${index}-${point.x}-${point.y}`}
                    cx={d.x}
                    cy={d.y}
                    r={4}
                    fill="#00c853"
                  />
                );
              })}
              {line2Points.map((point, index) => {
                const d = toDisplayPoint(point, frameRef, img);
                return (
                  <circle
                    key={`l2-${index}-${point.x}-${point.y}`}
                    cx={d.x}
                    cy={d.y}
                    r={4}
                    fill="#ff1744"
                  />
                );
              })}
            </svg>
          ) : null}
        </div>
      ) : (
        <p className="text-xs text-amber-600">Không lấy được snapshot camera.</p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          onClick={handleSave}
          disabled={isSaving || line1Points.length < 2 || line2Points.length < 2}
        >
          Lưu
        </Button>
        <Button
          variant="secondary"
          onClick={handleUndo}
          disabled={isSaving || activePoints.length === 0}
        >
          Hoàn tác điểm
        </Button>
        <Button variant="secondary" onClick={handleClear} disabled={isSaving}>
          Xóa
        </Button>
      </div>
      {message ? (
        <p className="mt-2 text-xs text-gray-600 dark:text-gray-300">{message}</p>
      ) : null}
    </div>
  );
};

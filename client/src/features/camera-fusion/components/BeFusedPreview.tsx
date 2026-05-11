import React, { useMemo } from 'react';
import { Loader2, Server } from 'lucide-react';
import { useFusedPreviewStream } from '../hooks/useFusedPreviewStream';
import type { CameraGroupMember } from '../types/fusion.types';

export const BeFusedPreview: React.FC<{
  canvasWidth: number;
  canvasHeight: number;
  members: CameraGroupMember[];
}> = ({ canvasWidth, canvasHeight, members }) => {
  const streamKey = useMemo(
    () =>
      JSON.stringify({
        canvasWidth,
        canvasHeight,
        layout: members.map((member) => ({
          cameraId: member.camera_id,
          enabled: member.enabled,
          x: member.layout_x,
          y: member.layout_y,
          w: member.layout_w,
          h: member.layout_h,
          rotation: member.layout_rotation,
          cropTop: member.crop_top,
          cropBottom: member.crop_bottom,
          cropLeft: member.crop_left,
          cropRight: member.crop_right,
        })),
      }),
    [canvasHeight, canvasWidth, members],
  );
  const { url, isConnected, error, receivedFps, renderFps } = useFusedPreviewStream(
    {
      fusion_mode: 'layout',
      canvas_width: canvasWidth,
      canvas_height: canvasHeight,
      members,
    },
    streamKey,
  );

  return (
    <div className="rounded-2xl border border-blue-500/20 bg-blue-950/20 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Server className="h-4 w-4 text-blue-300" />
          <p className="text-xs font-bold uppercase tracking-widest text-blue-100">BE Fused Preview</p>
        </div>
        <div className="flex items-center gap-2">
          {isConnected ? (
            <span className="rounded bg-black/30 px-2 py-1 text-[10px] font-mono text-blue-100">
              RX {receivedFps} / UI {renderFps} FPS
            </span>
          ) : null}
          {!isConnected && members.length > 0 ? (
            <Loader2 className="h-4 w-4 animate-spin text-blue-200" />
          ) : null}
        </div>
      </div>
      <div className="flex min-h-[220px] items-center justify-center overflow-hidden rounded-xl bg-black">
        {url ? (
          <img src={url} alt="Backend fused preview" className="max-h-[420px] w-full object-contain" />
        ) : (
          <p className="px-6 text-center text-xs text-white/50">
            Backend preview sẽ xuất hiện sau khi chọn camera và BE đọc được frame.
          </p>
        )}
      </div>
      {error ? <p className="mt-2 text-[11px] text-red-300">{error}</p> : null}
      <p className="mt-2 text-[10px] uppercase tracking-widest text-blue-100/60">
        Source of truth: ảnh này được render bởi backend bằng cùng fuser dùng cho YOLO.
        {isConnected ? ' WebSocket live.' : ''}
      </p>
    </div>
  );
};

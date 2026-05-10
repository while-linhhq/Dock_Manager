import React from 'react';
import { Loader2, Server } from 'lucide-react';
import { useFusedPreviewStream } from '../hooks/useFusedPreviewStream';
import type { CameraGroupMember, FusionMode } from '../types/fusion.types';

export const BeFusedPreview: React.FC<{
  fusionMode: FusionMode;
  canvasWidth: number;
  canvasHeight: number;
  members: CameraGroupMember[];
}> = ({ fusionMode, canvasWidth, canvasHeight, members }) => {
  const { url, isConnected, error } = useFusedPreviewStream({
    fusion_mode: fusionMode,
    canvas_width: canvasWidth,
    canvas_height: canvasHeight,
    members,
  });

  return (
    <div className="rounded-2xl border border-blue-500/20 bg-blue-950/20 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Server className="h-4 w-4 text-blue-300" />
          <p className="text-xs font-bold uppercase tracking-widest text-blue-100">BE Fused Preview</p>
        </div>
        {!isConnected && members.length > 0 ? (
          <Loader2 className="h-4 w-4 animate-spin text-blue-200" />
        ) : null}
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

import React from 'react';
import { Camera } from 'lucide-react';
import { useCameraStream } from '../hooks/useCameraStream';
import type { CameraGroupMember } from '../types/fusion.types';

export const CameraTile: React.FC<{
  member: CameraGroupMember;
  scale: number;
  selected: boolean;
  onMouseDown: (event: React.MouseEvent<HTMLDivElement>) => void;
}> = ({ member, scale, selected, onMouseDown }) => {
  const { url, isConnected, renderFps } = useCameraStream(member.camera_id);
  const baseWidth = member.layout_w ?? 320;
  const baseHeight = member.layout_h ?? 180;
  const cropLeft = Math.min(Math.max(0, member.crop_left ?? 0), Math.max(0, baseWidth - 1));
  const cropRight = Math.min(Math.max(0, member.crop_right ?? 0), Math.max(0, baseWidth - cropLeft - 1));
  const cropTop = Math.min(Math.max(0, member.crop_top ?? 0), Math.max(0, baseHeight - 1));
  const cropBottom = Math.min(Math.max(0, member.crop_bottom ?? 0), Math.max(0, baseHeight - cropTop - 1));
  const width = Math.max(1, baseWidth - cropLeft - cropRight) * scale;
  const height = Math.max(1, baseHeight - cropTop - cropBottom) * scale;

  return (
    <div
      className={[
        'absolute overflow-hidden rounded-lg border bg-black/40 shadow-xl',
        selected ? 'border-blue-400 ring-2 ring-blue-400/40' : 'border-white/30',
      ].join(' ')}
      style={{
        left: member.layout_x * scale,
        top: member.layout_y * scale,
        width,
        height,
        transform: `rotate(${member.layout_rotation}deg)`,
        zIndex: 10 + member.priority,
      }}
      onMouseDown={onMouseDown}
    >
      {url ? (
        <img
          src={url}
          alt=""
          className="absolute object-cover opacity-60"
          draggable={false}
          style={{
            left: -cropLeft * scale,
            top: -cropTop * scale,
            width: baseWidth * scale,
            height: baseHeight * scale,
          }}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-white/50">
          <Camera className="h-8 w-8" />
        </div>
      )}
      <div className="absolute left-2 top-2 rounded bg-black/70 px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-white">
        {member.camera?.camera_name ?? `Camera ${member.camera_id}`}
      </div>
      {renderFps > 0 ? (
        <div className="absolute bottom-2 left-2 rounded bg-black/70 px-1.5 py-0.5 text-[9px] font-mono text-white/80">
          {renderFps} FPS
        </div>
      ) : null}
      <div
        className={[
          'absolute right-2 top-2 h-2 w-2 rounded-full',
          isConnected ? 'bg-emerald-400' : 'bg-amber-400',
        ].join(' ')}
      />
      <div className="absolute bottom-1 right-1 h-4 w-4 rounded-sm border border-white/70 bg-blue-500/70" />
    </div>
  );
};

import React, { useMemo, useRef } from 'react';
import { CameraTile } from './CameraTile';
import type { CameraGroupMember } from '../types/fusion.types';

type DragState = {
  cameraId: number;
  startX: number;
  startY: number;
  baseX: number;
  baseY: number;
};

export const FusionCanvas: React.FC<{
  canvasWidth: number;
  canvasHeight: number;
  members: CameraGroupMember[];
  selectedCameraId: number | null;
  onSelect: (cameraId: number) => void;
  onMembersChange: (members: CameraGroupMember[]) => void;
}> = ({ canvasWidth, canvasHeight, members, selectedCameraId, onSelect, onMembersChange }) => {
  const dragRef = useRef<DragState | null>(null);
  const scale = useMemo(() => Math.min(1, 900 / canvasWidth), [canvasWidth]);

  const updateMember = (cameraId: number, patch: Partial<CameraGroupMember>) => {
    onMembersChange(
      members.map((member) =>
        member.camera_id === cameraId ? { ...member, ...patch } : member,
      ),
    );
  };

  const onMouseMove = (event: React.MouseEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) {
      return;
    }
    updateMember(drag.cameraId, {
      layout_x: Math.max(0, Math.round(drag.baseX + (event.clientX - drag.startX) / scale)),
      layout_y: Math.max(0, Math.round(drag.baseY + (event.clientY - drag.startY) / scale)),
    });
  };

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-white">Layout Canvas</p>
          <p className="text-[11px] text-white/50">
            UI layer only - fused pixels are rendered by backend preview.
          </p>
        </div>
        <p className="font-mono text-[11px] text-white/50">
          {canvasWidth} x {canvasHeight}
        </p>
      </div>
      <div
        className="relative overflow-hidden rounded-xl border border-white/10 bg-black"
        style={{ width: canvasWidth * scale, height: canvasHeight * scale }}
        onMouseMove={onMouseMove}
        onMouseUp={() => {
          dragRef.current = null;
        }}
        onMouseLeave={() => {
          dragRef.current = null;
        }}
      >
        {members.map((member) => (
          <CameraTile
            key={member.camera_id}
            member={member}
            scale={scale}
            selected={member.camera_id === selectedCameraId}
            onMouseDown={(event) => {
              event.preventDefault();
              onSelect(member.camera_id);
              dragRef.current = {
                cameraId: member.camera_id,
                startX: event.clientX,
                startY: event.clientY,
                baseX: member.layout_x,
                baseY: member.layout_y,
              };
            }}
          />
        ))}
      </div>
    </div>
  );
};

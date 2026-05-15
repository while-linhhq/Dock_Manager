import React from 'react';
import type { CameraRead } from '../../../types/api.types';
import type { CameraGroupMember } from '../types/fusion.types';
import { normalizeMemberPriorities } from '../utils/camera-group-order';

export const MemberList: React.FC<{
  cameras: CameraRead[];
  members: CameraGroupMember[];
  selectedCameraId: number | null;
  onSelect: (cameraId: number) => void;
  onMembersChange: (members: CameraGroupMember[]) => void;
}> = ({ cameras, members, selectedCameraId, onSelect, onMembersChange }) => {
  const addCamera = (cameraId: number) => {
    const camera = cameras.find((item) => Number(item.id) === cameraId);
    if (!camera || members.some((member) => member.camera_id === cameraId)) {
      return;
    }
    onMembersChange(
      normalizeMemberPriorities([
      ...members,
      {
        camera_id: cameraId,
        camera,
        role: 'tile',
        priority: members.length,
        layout_x: 40 + members.length * 40,
        layout_y: 40 + members.length * 40,
        layout_w: 640,
        layout_h: 360,
        layout_rotation: 0,
        crop_top: 0,
        crop_bottom: 0,
        crop_left: 0,
        crop_right: 0,
        enabled: true,
      },
    ]),
    );
  };

  const updateMember = (cameraId: number, patch: Partial<CameraGroupMember>) => {
    onMembersChange(
      members.map((member) =>
        member.camera_id === cameraId ? { ...member, ...patch } : member,
      ),
    );
  };

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#121214]">
      <p className="mb-3 text-xs font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
        Camera Members
      </p>
      <select
        className="mb-4 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-black dark:text-white"
        value=""
        onChange={(event) => addCamera(Number(event.target.value))}
      >
        <option value="">+ Thêm camera</option>
        {cameras
          .filter((camera) => !members.some((member) => member.camera_id === Number(camera.id)))
          .map((camera) => (
            <option key={camera.id} value={camera.id}>
              {camera.camera_name || camera.name || `Camera ${camera.id}`}
            </option>
          ))}
      </select>
      <div className="space-y-3">
        {members.map((member) => (
          <div
            key={member.camera_id}
            className={[
              'rounded-xl border p-3',
              selectedCameraId === member.camera_id
                ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/30'
                : 'border-gray-200 dark:border-white/10',
            ].join(' ')}
            onClick={() => onSelect(member.camera_id)}
          >
            <div className="mb-3 flex items-center justify-between gap-2">
              <p className="text-xs font-bold text-gray-900 dark:text-white">
                {member.camera?.camera_name ?? `Camera ${member.camera_id}`}
              </p>
              <button
                type="button"
                className="text-[10px] font-bold uppercase tracking-widest text-red-500"
                onClick={(event) => {
                  event.stopPropagation();
                  onMembersChange(
                    normalizeMemberPriorities(
                      members.filter((item) => item.camera_id !== member.camera_id),
                    ),
                  );
                }}
              >
                Xóa
              </button>
            </div>
            <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-400">
              Layout
            </p>
            <div className="grid grid-cols-3 gap-2">
              {[
                ['X', 'layout_x'],
                ['Y', 'layout_y'],
                ['W', 'layout_w'],
                ['H', 'layout_h'],
                ['Rot', 'layout_rotation'],
              ].map(([label, key]) => (
                <label key={key} className="text-[10px] uppercase tracking-widest text-gray-500">
                  {label}
                  <input
                    type="number"
                    className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-2 py-1 text-xs dark:border-white/10 dark:bg-black dark:text-white"
                    value={Number((member as unknown as Record<string, number | undefined>)[key] ?? 0)}
                    onChange={(event) =>
                      updateMember(member.camera_id, { [key]: Number(event.target.value) } as Partial<CameraGroupMember>)
                    }
                  />
                </label>
              ))}
            </div>
            <p className="mb-2 mt-3 text-[10px] font-bold uppercase tracking-widest text-gray-400">
              Crop px
            </p>
            <div className="grid grid-cols-4 gap-2">
              {[
                ['Top', 'crop_top'],
                ['Bottom', 'crop_bottom'],
                ['Left', 'crop_left'],
                ['Right', 'crop_right'],
              ].map(([label, key]) => (
                <label key={key} className="text-[10px] uppercase tracking-widest text-gray-500">
                  {label}
                  <input
                    type="number"
                    min={0}
                    className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-2 py-1 text-xs dark:border-white/10 dark:bg-black dark:text-white"
                    value={Number((member as unknown as Record<string, number | undefined>)[key] ?? 0)}
                    onChange={(event) =>
                      updateMember(member.camera_id, {
                        [key]: Math.max(0, Number(event.target.value)),
                      } as Partial<CameraGroupMember>)
                    }
                  />
                </label>
              ))}
            </div>
            <label className="mt-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-gray-500">
              <input
                type="checkbox"
                checked={member.enabled}
                onChange={(event) => updateMember(member.camera_id, { enabled: event.target.checked })}
              />
              Enabled
            </label>
          </div>
        ))}
      </div>
    </div>
  );
};

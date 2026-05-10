import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { PATHS } from '../../../router/paths';
import { cameraGroupsApi } from '../services/camera-groups-api';
import type { CameraGroup } from '../types/fusion.types';

export const FusionGroupListView: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const [groups, setGroups] = useState<CameraGroup[]>([]);

  const load = () => {
    cameraGroupsApi.list(false).then(setGroups).catch(console.error);
  };

  useEffect(() => {
    load();
  }, []);

  const remove = async (group: CameraGroup) => {
    if (!window.confirm(`Xóa camera group "${group.name}"?`)) {
      return;
    }
    await cameraGroupsApi.delete(group.id);
    load();
  };

  return (
    <div className={compact ? 'space-y-6' : 'h-full overflow-y-auto p-6'}>
      <div className={compact ? 'space-y-6' : 'mx-auto max-w-6xl space-y-6'}>
        <div className="flex items-center justify-between">
          {compact ? (
            <div>
              <h2 className="text-sm font-bold uppercase tracking-widest text-gray-900 dark:text-white">
                Group Camera
              </h2>
              <p className="text-xs text-gray-500">
                Cấu hình fused frame ở BE cho multi-camera detection.
              </p>
            </div>
          ) : (
            <div>
              <h1 className="text-2xl font-black tracking-tight text-gray-900 dark:text-white">
                Camera Fusion Groups
              </h1>
              <p className="text-sm text-gray-500">
                Cấu hình fused frame ở BE cho multi-camera detection.
              </p>
            </div>
          )}
          <Link to={`${PATHS.CAMERA_FUSION}/new`}>
            <Button className="flex items-center gap-2">
              <Plus className="h-4 w-4" /> New group
            </Button>
          </Link>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {groups.map((group) => (
            <div
              key={group.id}
              className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-[#121214]"
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-bold text-gray-900 dark:text-white">{group.name}</h2>
                  <p className="text-xs uppercase tracking-widest text-gray-500">
                    {group.fusion_mode} · {group.canvas_width}x{group.canvas_height}
                  </p>
                </div>
                <span className={group.is_active ? 'text-xs text-emerald-500' : 'text-xs text-gray-400'}>
                  {group.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>
              <p className="mb-4 min-h-10 text-sm text-gray-500">
                {group.description || `${group.members.length} camera members`}
              </p>
              <div className="flex items-center justify-between">
                <Link
                  to={`${PATHS.CAMERA_FUSION}/${group.id}`}
                  className="text-xs font-bold uppercase tracking-widest text-blue-500"
                >
                  Edit
                </Link>
                <button
                  type="button"
                  onClick={() => remove(group)}
                  className="rounded-lg p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

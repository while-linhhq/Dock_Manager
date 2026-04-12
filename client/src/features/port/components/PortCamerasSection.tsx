import React from 'react';
import { Camera, Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import type { CameraRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

export type PortCamerasSectionProps = {
  camQ: string;
  setCamQ: (v: string) => void;
  camActive: 'all' | 'on' | 'off';
  setCamActive: (v: 'all' | 'on' | 'off') => void;
  resetCamFilters: () => void;
  camFilterCount: number;
  onOpenAddCamera: () => void;
  filteredCameras: CameraRead[];
  cameras: CameraRead[];
  isLoading: boolean;
  onEditCamera: (cam: CameraRead) => void;
  onDeleteCamera: (cam: CameraRead) => void;
};

export const PortCamerasSection: React.FC<PortCamerasSectionProps> = ({
  camQ,
  setCamQ,
  camActive,
  setCamActive,
  resetCamFilters,
  camFilterCount,
  onOpenAddCamera,
  filteredCameras,
  cameras,
  isLoading,
  onEditCamera,
  onDeleteCamera,
}) => {
  return (
    <div className="space-y-6">
      <TableFilterPanel
        title="Bộ lọc camera"
        onReset={resetCamFilters}
        activeCount={camFilterCount}
      >
        <FilterField label="Tên / URL RTSP">
          <input
            type="text"
            value={camQ}
            onChange={(e) => setCamQ(e.target.value)}
            placeholder="Lọc..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Hoạt động">
          <select
            value={camActive}
            onChange={(e) => setCamActive(e.target.value as 'all' | 'on' | 'off')}
            className={filterControlClass}
          >
            <option value="all">Tất cả</option>
            <option value="on">Đang bật</option>
            <option value="off">Tắt</option>
          </select>
        </FilterField>
      </TableFilterPanel>

      <div className="flex justify-between items-center">
        <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
          Quản Lý Camera Giám Sát
        </h3>
        <Button
          type="button"
          onClick={onOpenAddCamera}
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
        >
          <Plus className="w-4 h-4 mr-2" />
          Thêm Camera
        </Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredCameras.length > 0 ? (
          filteredCameras.map((cam) => (
            <div
              key={cam.id}
              className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl space-y-4"
            >
              <div className="flex justify-between items-start">
                <div className="p-3 bg-blue-600/10 rounded-xl">
                  <Camera className="w-6 h-6 text-blue-600" />
                </div>
                <span
                  className={cn(
                    'text-[10px] font-bold px-2 py-1 rounded-full uppercase tracking-tighter',
                    cam.is_active ? 'bg-green-500/10 text-green-500' : 'bg-gray-500/10 text-gray-500',
                  )}
                >
                  {cam.is_active ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>
              <div>
                <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase">
                  {cam.camera_name || cam.name}
                </h4>
                <p className="text-[10px] text-gray-500 font-mono truncate mt-1">{cam.rtsp_url}</p>
              </div>
              <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-end items-center gap-4">
                <button
                  type="button"
                  onClick={() => onEditCamera(cam)}
                  className="text-[10px] font-bold text-gray-500 hover:text-blue-600 uppercase tracking-widest transition-colors"
                >
                  Chỉnh Sửa
                </button>
                <button
                  type="button"
                  onClick={() => onDeleteCamera(cam)}
                  disabled={isLoading}
                  className="inline-flex items-center gap-1 text-[10px] font-bold text-red-600/90 hover:text-red-500 uppercase tracking-widest transition-colors disabled:opacity-50"
                >
                  <Trash2 className="w-3 h-3" />
                  Xóa
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="col-span-full py-12 text-center text-gray-500 text-xs uppercase font-mono">
            {cameras.length === 0 ? 'Chưa có camera' : 'Không có camera khớp bộ lọc'}
          </div>
        )}
      </div>
    </div>
  );
};

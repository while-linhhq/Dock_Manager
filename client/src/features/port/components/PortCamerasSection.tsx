import React from 'react';
import { AlertCircle, AlertTriangle, Camera, Plus, Trash2 } from 'lucide-react';
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
  /** Giới hạn camera của license hiện tại; `0` = chưa biết/chưa cấp. */
  licenseLimit: number;
  /** `true` khi license ở chế độ `enforce` (chặn thật ở server). */
  licenseEnforced: boolean;
  /** Lỗi từ API khi thêm/sửa camera (vd 403 CAMERA_LIMIT). */
  cameraError: string | null;
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
  licenseLimit,
  licenseEnforced,
  cameraError,
}) => {
  const remainingSlots = Math.max(0, licenseLimit - cameras.length);
  const showNearLimitWarning =
    licenseLimit > 0 && licenseLimit - cameras.length <= 2;
  const addCameraDisabled = licenseEnforced && cameras.length >= licenseLimit;
  const addCameraTitle = addCameraDisabled
    ? licenseLimit > 0
      ? `Đã đạt giới hạn ${licenseLimit} camera của license (hiện có ${cameras.length}). Liên hệ DTG để nâng giới hạn.`
      : 'License hiện tại không cho phép tạo camera. Liên hệ DTG để được cấp giới hạn.'
    : licenseLimit > 0
      ? `License cho phép tối đa ${licenseLimit} camera (hiện có ${cameras.length}).`
      : undefined;

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
          disabled={addCameraDisabled}
          title={addCameraTitle}
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
        >
          <Plus className="w-4 h-4 mr-2" />
          Thêm Camera
        </Button>
      </div>

      {showNearLimitWarning && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            {`Sắp đạt giới hạn camera: ${cameras.length}/${licenseLimit} — còn ${remainingSlots} slot. Liên hệ DTG để nâng giới hạn.`}
          </span>
        </div>
      )}

      {cameraError && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-relaxed text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
        >
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{cameraError}</span>
        </div>
      )}

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

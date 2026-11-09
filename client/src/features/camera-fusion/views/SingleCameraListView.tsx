import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { AlertCircle, AlertTriangle, Camera, Loader2, Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import type { CameraRead } from '../../../types/api.types';
import { cn } from '../../../utils/cn';
import { matchesAnyField } from '../../../utils/table-filters';
import { cameraSchema } from '../../port/port-schemas';
import type { CameraCreate } from '../../port/services/portApi';
import { usePortStore } from '../../port/store/portStore';
import { useLicenseStore } from '../../license/store/licenseStore';

export const SingleCameraListView: React.FC = () => {
  const [isCameraModalOpen, setIsCameraModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [cameraKeyword, setCameraKeyword] = useState('');
  const [cameraActive, setCameraActive] = useState<'all' | 'on' | 'off'>('all');
  const [cameraError, setCameraError] = useState<string | null>(null);
  const { cameras, isLoading, fetchCameras, upsertCamera, deleteCamera } = usePortStore();

  const licenseStatus = useLicenseStore((state) => state.status);
  const licenseLimit = Number(licenseStatus?.features?.max_cameras ?? 0);
  const licenseEnforced = licenseStatus?.enforcement_mode === 'enforce';
  const showNearLimitWarning = licenseLimit > 0 && licenseLimit - cameras.length <= 2;
  const cameraLimitReached = licenseEnforced && cameras.length >= licenseLimit;
  const addCameraTitle = cameraLimitReached
    ? `Đã đạt giới hạn ${licenseLimit} camera của license (hiện có ${cameras.length}). Liên hệ DTG để nâng giới hạn.`
    : licenseLimit > 0
      ? `License cho phép tối đa ${licenseLimit} camera (hiện có ${cameras.length}).`
      : undefined;

  const cameraForm = useForm<CameraCreate>({
    resolver: zodResolver(cameraSchema),
    defaultValues: { is_active: true },
  });

  useEffect(() => {
    fetchCameras(false);
  }, [fetchCameras]);

  const filteredCameras = useMemo(() => {
    return cameras.filter((cameraItem) => {
      if (!matchesAnyField(cameraKeyword, cameraItem.camera_name, cameraItem.name, cameraItem.rtsp_url)) {
        return false;
      }
      if (cameraActive === 'on' && !cameraItem.is_active) {
        return false;
      }
      if (cameraActive === 'off' && cameraItem.is_active) {
        return false;
      }
      return true;
    });
  }, [cameraActive, cameraKeyword, cameras]);

  const cameraFilterCount = (cameraKeyword.trim() ? 1 : 0) + (cameraActive !== 'all' ? 1 : 0);

  const resetCameraFilters = () => {
    setCameraKeyword('');
    setCameraActive('all');
  };

  const openCreateCamera = () => {
    setEditingId(null);
    setCameraError(null);
    cameraForm.reset({ is_active: true });
    setIsCameraModalOpen(true);
  };

  const handleEditCamera = (cameraItem: CameraRead) => {
    setEditingId(String(cameraItem.id));
    setCameraError(null);
    cameraForm.reset({
      name: cameraItem.camera_name || cameraItem.name || '',
      rtsp_url: cameraItem.rtsp_url,
      is_active: cameraItem.is_active,
    });
    setIsCameraModalOpen(true);
  };

  const handleDeleteCamera = async (cameraItem: CameraRead) => {
    const label = cameraItem.camera_name || cameraItem.name || `Camera ${cameraItem.id}`;
    if (!window.confirm(`Xóa vĩnh viễn camera «${label}»? Hành động không hoàn tác.`)) {
      return;
    }
    if (editingId != null && String(editingId) === String(cameraItem.id)) {
      setIsCameraModalOpen(false);
      setEditingId(null);
      cameraForm.reset({ is_active: true });
    }
    await deleteCamera(cameraItem.id);
  };

  const closeCameraModal = () => {
    // Giữ `cameraError` để banner đỏ vẫn hiển thị trên lưới camera sau khi đóng modal lỗi.
    setIsCameraModalOpen(false);
  };

  const onCameraSubmit = async (data: CameraCreate) => {
    try {
      await upsertCamera(editingId, data);
    } catch (err) {
      // Giữ modal mở để người dùng thấy camera chưa được lưu (vd 403 CAMERA_LIMIT).
      setCameraError(err instanceof Error ? err.message : 'Không lưu được camera');
      return;
    }
    setIsCameraModalOpen(false);
    setCameraError(null);
    setEditingId(null);
    cameraForm.reset({ is_active: true });
  };

  return (
    <div className="space-y-6">
      <TableFilterPanel
        title="Bộ lọc camera"
        onReset={resetCameraFilters}
        activeCount={cameraFilterCount}
      >
        <FilterField label="Từ khóa">
          <input
            type="text"
            value={cameraKeyword}
            onChange={(event) => setCameraKeyword(event.target.value)}
            placeholder="Tên camera / RTSP..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Trạng thái">
          <select
            value={cameraActive}
            onChange={(event) => setCameraActive(event.target.value as 'all' | 'on' | 'off')}
            className={filterControlClass}
          >
            <option value="all">Tất cả</option>
            <option value="on">Đang bật</option>
            <option value="off">Tắt</option>
          </select>
        </FilterField>
      </TableFilterPanel>

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-widest text-gray-900 dark:text-white">
            Camera đơn
          </h2>
          <p className="text-xs text-gray-500">Quản lý RTSP camera dùng cho pipeline và camera group.</p>
        </div>
        <Button
          type="button"
          onClick={openCreateCamera}
          disabled={cameraLimitReached}
          title={addCameraTitle}
          className="bg-blue-600 text-white shadow-lg shadow-blue-600/20 hover:bg-blue-700"
        >
          <Plus className="mr-2 h-4 w-4" />
          Thêm Camera
        </Button>
      </div>

      {showNearLimitWarning && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {`Sắp đạt giới hạn camera: ${cameras.length}/${licenseLimit} — còn ${licenseLimit - cameras.length} slot. Liên hệ DTG để nâng giới hạn.`}
          </span>
        </div>
      )}

      {cameraError && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-relaxed text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{cameraError}</span>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {filteredCameras.length > 0 ? (
          filteredCameras.map((cameraItem) => (
            <div
              key={cameraItem.id}
              className="space-y-4 rounded-2xl border border-gray-200 bg-white p-6 shadow-xl dark:border-white/5 dark:bg-[#121214]"
            >
              <div className="flex items-start justify-between">
                <div className="rounded-xl bg-blue-600/10 p-3">
                  <Camera className="h-6 w-6 text-blue-600" />
                </div>
                <span
                  className={cn(
                    'rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-tighter',
                    cameraItem.is_active ? 'bg-green-500/10 text-green-500' : 'bg-gray-500/10 text-gray-500',
                  )}
                >
                  {cameraItem.is_active ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>
              <div>
                <h3 className="text-sm font-bold uppercase text-gray-900 dark:text-white">
                  {cameraItem.camera_name || cameraItem.name}
                </h3>
                <p className="mt-1 truncate font-mono text-[10px] text-gray-500">
                  {cameraItem.rtsp_url}
                </p>
              </div>
              <div className="flex items-center justify-end gap-4 border-t border-gray-100 pt-4 dark:border-white/5">
                <button
                  type="button"
                  onClick={() => handleEditCamera(cameraItem)}
                  className="text-[10px] font-bold uppercase tracking-widest text-gray-500 transition-colors hover:text-blue-600"
                >
                  Chỉnh Sửa
                </button>
                <button
                  type="button"
                  onClick={() => handleDeleteCamera(cameraItem)}
                  disabled={isLoading}
                  className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-red-600/90 transition-colors hover:text-red-500 disabled:opacity-50"
                >
                  <Trash2 className="h-3 w-3" />
                  Xóa
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="col-span-full py-12 text-center font-mono text-xs uppercase text-gray-500">
            {cameras.length === 0 ? 'Chưa có camera' : 'Không có camera khớp bộ lọc'}
          </div>
        )}
      </div>

      <Modal
        isOpen={isCameraModalOpen}
        onClose={closeCameraModal}
        title={editingId ? 'Chỉnh Sửa Camera' : 'Thêm Camera Mới'}
      >
        <form onSubmit={cameraForm.handleSubmit(onCameraSubmit)} className="space-y-4">
          <Input
            label="Tên Camera"
            placeholder="VD: Camera Cảng Trước"
            {...cameraForm.register('name')}
            error={cameraForm.formState.errors.name?.message}
          />
          <Input
            label="RTSP URL"
            placeholder="rtsp://username:password@ip:port/path"
            {...cameraForm.register('rtsp_url')}
            error={cameraForm.formState.errors.rtsp_url?.message}
          />
          <div className="ml-1 flex items-center space-x-2">
            <input
              type="checkbox"
              id="fusion_cam_is_active"
              {...cameraForm.register('is_active')}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label
              htmlFor="fusion_cam_is_active"
              className="text-[10px] font-bold uppercase tracking-widest text-gray-700 dark:text-gray-300"
            >
              Kích Hoạt Camera
            </label>
          </div>
          <div className="flex space-x-3 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={closeCameraModal}
              className="flex-1"
            >
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 text-white hover:bg-blue-700"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : editingId ? 'Cập Nhật' : 'Thêm Mới'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

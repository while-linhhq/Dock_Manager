import React from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Loader2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import type { CameraCreate, PortConfigCreate } from '../services/portApi';

export type PortModalsProps = {
  isCameraModalOpen: boolean;
  onCloseCamera: () => void;
  cameraForm: UseFormReturn<CameraCreate>;
  onCameraSubmit: (data: CameraCreate) => void | Promise<void>;
  editingCameraId: string | null;
  isLoading: boolean;
  isConfigModalOpen: boolean;
  onCloseConfig: () => void;
  configForm: UseFormReturn<PortConfigCreate>;
  onConfigSubmit: (data: PortConfigCreate) => void | Promise<void>;
  editingConfigKey: string | null;
};

export const PortModals: React.FC<PortModalsProps> = ({
  isCameraModalOpen,
  onCloseCamera,
  cameraForm,
  onCameraSubmit,
  editingCameraId,
  isLoading,
  isConfigModalOpen,
  onCloseConfig,
  configForm,
  onConfigSubmit,
  editingConfigKey,
}) => {
  return (
    <>
      <Modal
        isOpen={isCameraModalOpen}
        onClose={onCloseCamera}
        title={editingCameraId ? 'Chỉnh Sửa Camera' : 'Thêm Camera Mới'}
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
          <div className="flex items-center space-x-2 ml-1">
            <input
              type="checkbox"
              id="cam_is_active"
              {...cameraForm.register('is_active')}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label
              htmlFor="cam_is_active"
              className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest"
            >
              Kích Hoạt Camera
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onCloseCamera} className="flex-1">
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : editingCameraId ? (
                'Cập Nhật'
              ) : (
                'Thêm Mới'
              )}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={isConfigModalOpen}
        onClose={onCloseConfig}
        title={editingConfigKey ? `Cấu Hình: ${editingConfigKey}` : 'Thêm Config Mới'}
      >
        <form onSubmit={configForm.handleSubmit(onConfigSubmit)} className="space-y-4">
          <Input
            label="Key"
            {...configForm.register('key')}
            error={configForm.formState.errors.key?.message}
            disabled={Boolean(editingConfigKey)}
          />
          <Input
            label="Giá Trị"
            {...configForm.register('value')}
            error={configForm.formState.errors.value?.message}
          />
          <Input label="Mô Tả" {...configForm.register('description')} />
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onCloseConfig} className="flex-1">
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Lưu Thay Đổi'}
            </Button>
          </div>
        </form>
      </Modal>

    </>
  );
};

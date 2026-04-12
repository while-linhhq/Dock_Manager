import React from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Loader2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import type { CameraRead } from '../../../types/api.types';
import type { CameraCreate, PortConfigCreate, PipelineStartRequest } from '../services/portApi';

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
  isPipelineModalOpen: boolean;
  onClosePipeline: () => void;
  pipelineForm: UseFormReturn<PipelineStartRequest>;
  onPipelineSubmit: (data: PipelineStartRequest) => void | Promise<void>;
  selectedCameraId: string;
  setSelectedCameraId: (v: string) => void;
  cameras: CameraRead[];
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
  isPipelineModalOpen,
  onClosePipeline,
  pipelineForm,
  onPipelineSubmit,
  selectedCameraId,
  setSelectedCameraId,
  cameras,
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

      <Modal isOpen={isPipelineModalOpen} onClose={onClosePipeline} title="Khởi Chạy AI Pipeline">
        <form onSubmit={pipelineForm.handleSubmit(onPipelineSubmit)} className="space-y-4">
          <div>
            <label className="mb-2 block text-[10px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
              Chọn Camera Đã Tạo
            </label>
            <select
              value={selectedCameraId}
              className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm dark:border-white/10 dark:bg-[#121214] dark:text-white"
              onChange={(e) => {
                const value = e.target.value;
                setSelectedCameraId(value);
                if (!value) {
                  return;
                }
                const selected = cameras.find((cam) => String(cam.id) === value);
                if (selected?.rtsp_url) {
                  pipelineForm.setValue('source', selected.rtsp_url);
                }
              }}
            >
              <option value="">-- Không chọn (nhập source thủ công) --</option>
              {cameras
                .filter((cam) => cam.is_active)
                .map((cam) => (
                  <option key={cam.id} value={String(cam.id)}>
                    {(cam.camera_name || cam.name) ?? `Camera ${cam.id}`}
                  </option>
                ))}
            </select>
            <p className="mt-1.5 text-[10px] text-gray-500 dark:text-gray-400 leading-relaxed">
              Chỉ liệt kê camera đang bật. Camera tắt: mở tab Camera → bật «Kích hoạt», hoặc không chọn
              camera và dán RTSP vào ô nguồn.
            </p>
          </div>
          <Input
            label="Nguồn Video (Index, URL, hoặc tự fill từ Camera)"
            placeholder="0"
            {...pipelineForm.register('source')}
            error={pipelineForm.formState.errors.source?.message}
          />
          <div className="flex items-center space-x-2 ml-1">
            <input
              type="checkbox"
              id="enable_ocr"
              {...pipelineForm.register('enable_ocr')}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label
              htmlFor="enable_ocr"
              className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest"
            >
              Bật Nhận Diện Mã Tàu (OCR)
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onClosePipeline} className="flex-1">
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Bắt Đầu Xử Lý'}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};

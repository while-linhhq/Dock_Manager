import React, { useEffect, useState } from 'react';
import { 
  Camera, 
  Settings, 
  Cpu, 
  Search, 
  CheckCircle2, 
  XCircle, 
  Plus, 
  Play, 
  Square,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import { cn } from '../../../utils/cn';
import { getDetectionDisplayTimeIso, getDetectionShipLabel } from '../../../utils/detection-display';
import { usePortStore } from '../store/portStore';
import type { CameraCreate, PortConfigCreate, PipelineStartRequest } from '../services/portApi';

const cameraSchema = z.object({
  name: z.string().min(1, 'Tên camera là bắt buộc'),
  rtsp_url: z.string().url('URL RTSP không hợp lệ'),
  is_active: z.boolean().default(true),
});

const configSchema = z.object({
  key: z.string().min(1, 'Key không được để trống'),
  value: z.string().min(1, 'Giá trị không được để trống'),
  description: z.string().optional(),
});

const pipelineSchema = z.object({
  source: z.string().optional(),
  enable_ocr: z.boolean().default(true),
});

export const PortView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'detections' | 'cameras' | 'configs' | 'pipeline'>('detections');
  const [isCameraModalOpen, setIsCameraModalOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [isPipelineModalOpen, setIsPipelineModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingConfigKey, setEditingConfigKey] = useState<string | null>(null);
  const [selectedCameraId, setSelectedCameraId] = useState<string>('');

  const {
    detections, cameras, configs, isLoading, 
    fetchDetections, fetchCameras, fetchConfigs, 
    verifyDetection, upsertCamera, upsertConfig, deleteConfig, deleteDetection,
    startPipeline, stopPipeline 
  } = usePortStore();

  const cameraForm = useForm<CameraCreate>({
    resolver: zodResolver(cameraSchema),
    defaultValues: { is_active: true }
  });

  const configForm = useForm<PortConfigCreate>({
    resolver: zodResolver(configSchema)
  });

  const pipelineForm = useForm<PipelineStartRequest>({
    resolver: zodResolver(pipelineSchema),
    defaultValues: { source: '', enable_ocr: true }
  });

  useEffect(() => {
    if (activeTab === 'detections') fetchDetections();
    if (activeTab === 'cameras' || activeTab === 'pipeline') fetchCameras();
    if (activeTab === 'configs') fetchConfigs();
  }, [activeTab, fetchDetections, fetchCameras, fetchConfigs]);

  const onCameraSubmit = async (data: CameraCreate) => {
    try {
      await upsertCamera(editingId, data);
      setIsCameraModalOpen(false);
      cameraForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const onConfigSubmit = async (data: PortConfigCreate) => {
    try {
      await upsertConfig(editingConfigKey, data);
      setIsConfigModalOpen(false);
      configForm.reset();
      setEditingConfigKey(null);
    } catch (err) {
      console.error(err);
    }
  };

  const onPipelineSubmit = async (data: PipelineStartRequest) => {
    try {
      const payload: PipelineStartRequest = {
        enable_ocr: data.enable_ocr,
      };
      if (selectedCameraId) {
        payload.camera_id = Number(selectedCameraId);
      } else if (data.source && data.source.trim()) {
        payload.source = data.source.trim();
      }
      await startPipeline(payload);
      setIsPipelineModalOpen(false);
      setSelectedCameraId('');
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditCamera = (cam: any) => {
    setEditingId(cam.id);
    cameraForm.reset({
      name: cam.name,
      rtsp_url: cam.rtsp_url,
      is_active: cam.is_active,
    });
    setIsCameraModalOpen(true);
  };

  const handleEditConfig = (cfg: any) => {
    setEditingConfigKey(cfg.key);
    configForm.reset({
      key: cfg.key,
      value: cfg.value,
      description: cfg.description || '',
    });
    setIsConfigModalOpen(true);
  };

  const handleDeleteConfig = async (key: string) => {
    if (!window.confirm(`Xác nhận xóa config "${key}"?`)) {
      return;
    }
    await deleteConfig(key);
  };

  const handleDeleteDetection = async (id: string) => {
    if (!window.confirm('Xác nhận xóa bản ghi nhận diện này?')) {
      return;
    }
    await deleteDetection(id);
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit overflow-x-auto">
        {[
          { id: 'detections', label: 'Nhận Diện', icon: ShieldCheck },
          { id: 'cameras', label: 'Camera', icon: Camera },
          { id: 'configs', label: 'Cấu Hình', icon: Settings },
          { id: 'pipeline', label: 'AI Pipeline', icon: Cpu },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={cn(
              "px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2 whitespace-nowrap",
              activeTab === tab.id 
                ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm" 
                : "text-gray-500 hover:text-gray-900 dark:hover:text-white"
            )}
          >
            <tab.icon className="w-4 h-4" />
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {activeTab === 'detections' && (
        <div className="space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input 
                type="text" 
                placeholder="Tìm mã tàu..." 
                className="w-full pl-10 pr-4 py-2 bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white"
              />
            </div>
            <Button variant="outline" onClick={() => fetchDetections()} className="border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400">
              <RefreshCw className={cn("w-4 h-4 mr-2", isLoading && "animate-spin")} />
              Làm Mới
            </Button>
          </div>

          <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.01]">
                    <th className="px-6 py-4">Thời Gian</th>
                    <th className="px-6 py-4">Mã Tàu</th>
                    <th className="px-6 py-4">Độ Tin Cậy</th>
                    <th className="px-6 py-4">Trạng Thái</th>
                    <th className="px-6 py-4 text-right">Thao Tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-white/5">
                  {isLoading && detections.length === 0 ? (
                    <tr><td colSpan={5} className="px-6 py-12 text-center"><Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" /></td></tr>
                  ) : detections.length > 0 ? (
                    detections.map((det) => (
                      <tr key={det.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors">
                        <td className="px-6 py-4 text-[10px] font-mono text-gray-400">
                          {(() => {
                            const iso = getDetectionDisplayTimeIso(det);
                            return iso
                              ? new Date(iso).toLocaleString('vi-VN')
                              : '\u2014';
                          })()}
                        </td>
                        <td className="px-6 py-4 text-xs font-bold text-gray-900 dark:text-white uppercase">
                          {getDetectionShipLabel(det)}
                        </td>
                        <td className="px-6 py-4 text-xs font-mono text-blue-500">
                          {(((det.confidence ?? 0) as number) * 100).toFixed(1)}%
                        </td>
                        <td className="px-6 py-4">
                          <span className={cn(
                            "inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border",
                            det.is_accepted === true
                              ? "text-emerald-500 bg-emerald-500/10 border-emerald-500/20"
                              : "text-amber-500 bg-amber-500/10 border-amber-500/20"
                          )}>
                            {det.is_accepted === true ? 'Đã Xác Nhận' : 'Chờ Duyệt'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right space-x-2">
                          {det.is_accepted !== true && (
                            <>
                              <button 
                                onClick={() => verifyDetection(det.id, { is_accepted: true })}
                                className="p-1.5 text-emerald-500 hover:bg-emerald-500/10 rounded-lg transition-all"
                              >
                                <CheckCircle2 className="w-4 h-4" />
                              </button>
                              <button 
                                onClick={() => verifyDetection(det.id, { is_accepted: false })}
                                className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg transition-all"
                              >
                                <XCircle className="w-4 h-4" />
                              </button>
                            </>
                          )}
                          <button
                            onClick={() => handleDeleteDetection(det.id)}
                            className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg transition-all"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr><td colSpan={5} className="px-6 py-12 text-center text-gray-500 text-xs uppercase font-mono">Không có dữ liệu nhận diện</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'cameras' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">Quản Lý Camera Giám Sát</h3>
            <Button 
              onClick={() => {
                setEditingId(null);
                cameraForm.reset({ is_active: true });
                setIsCameraModalOpen(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
            >
              <Plus className="w-4 h-4 mr-2" />
              Thêm Camera
            </Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {cameras.map((cam) => (
              <div key={cam.id} className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl space-y-4">
                <div className="flex justify-between items-start">
                  <div className="p-3 bg-blue-600/10 rounded-xl"><Camera className="w-6 h-6 text-blue-600" /></div>
                  <span className={cn(
                    "text-[10px] font-bold px-2 py-1 rounded-full uppercase tracking-tighter",
                    cam.is_active ? "bg-green-500/10 text-green-500" : "bg-gray-500/10 text-gray-500"
                  )}>{cam.is_active ? 'ONLINE' : 'OFFLINE'}</span>
                </div>
                <div>
                  <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase">
                    {cam.camera_name || cam.name}
                  </h4>
                  <p className="text-[10px] text-gray-500 font-mono truncate mt-1">{cam.rtsp_url}</p>
                </div>
                <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-end">
                  <button 
                    onClick={() => handleEditCamera(cam)}
                    className="text-[10px] font-bold text-gray-500 hover:text-blue-600 uppercase tracking-widest transition-colors"
                  >
                    Chỉnh Sửa
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'configs' && (
        <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
          <div className="p-6 border-b border-gray-200 dark:border-white/5 flex items-center justify-between">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">Cấu Hình Cảng</h3>
            <Button
              onClick={() => {
                setEditingConfigKey(null);
                configForm.reset({ key: '', value: '', description: '' });
                setIsConfigModalOpen(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              <Plus className="w-4 h-4 mr-2" />
              Thêm Config
            </Button>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-white/5">
            {configs.map((cfg) => (
              <div key={cfg.key} className="p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-gray-50 dark:hover:bg-white/[0.01] transition-colors">
                <div>
                  <p className="text-xs font-bold text-gray-900 dark:text-white uppercase font-mono">{cfg.key}</p>
                  <p className="text-[10px] text-gray-500 uppercase tracking-widest mt-1">{cfg.description || 'Không có mô tả'}</p>
                </div>
                <div className="flex items-center space-x-4">
                  <span className="px-4 py-2 bg-gray-100 dark:bg-white/5 rounded-lg text-xs font-mono text-blue-500 font-bold">{cfg.value}</span>
                  <button 
                    onClick={() => handleEditConfig(cfg)}
                    className="text-[10px] font-bold text-blue-600 hover:text-blue-500 uppercase tracking-widest"
                  >
                    Thay Đổi
                  </button>
                  <button
                    onClick={() => handleDeleteConfig(cfg.key)}
                    className="text-[10px] font-bold text-red-600 hover:text-red-500 uppercase tracking-widest inline-flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    Xóa
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'pipeline' && (
        <div className="max-w-2xl mx-auto bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl p-8 space-y-8">
          <div className="text-center space-y-2">
            <div className="p-4 bg-blue-600/10 rounded-full w-fit mx-auto"><Cpu className="w-12 h-12 text-blue-600" /></div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white uppercase tracking-widest">Điều Khiển AI Core</h3>
            <p className="text-xs text-gray-500 uppercase tracking-widest">Khởi chạy hoặc dừng luồng xử lý nhận diện tàu</p>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <Button 
              onClick={() => {
                setSelectedCameraId('');
                pipelineForm.reset({ source: '', enable_ocr: true });
                setIsPipelineModalOpen(true);
              }}
              className="py-6 bg-emerald-600 hover:bg-emerald-700 text-white flex flex-col space-y-2 h-auto"
            >
              <Play className="w-6 h-6" />
              <span className="text-xs font-bold uppercase tracking-widest">Bắt Đầu Pipeline</span>
            </Button>
            <Button 
              onClick={() => stopPipeline()}
              className="py-6 bg-red-600 hover:bg-red-700 text-white flex flex-col space-y-2 h-auto"
            >
              <Square className="w-6 h-6" />
              <span className="text-xs font-bold uppercase tracking-widest">Dừng Hệ Thống</span>
            </Button>
          </div>

          <div className="p-6 bg-gray-50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5 space-y-4">
            <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Trạng Thái Hiện Tại</h4>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-600 dark:text-gray-300 font-bold uppercase">Engine Status</span>
              <span className="flex items-center text-xs font-mono text-green-500 font-bold">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse" />
                OPERATIONAL
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Camera Modal */}
      <Modal
        isOpen={isCameraModalOpen}
        onClose={() => setIsCameraModalOpen(false)}
        title={editingId ? "Chỉnh Sửa Camera" : "Thêm Camera Mới"}
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
            <label htmlFor="cam_is_active" className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest">
              Kích Hoạt Camera
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={() => setIsCameraModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingId ? "Cập Nhật" : "Thêm Mới")}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Config Modal */}
      <Modal
        isOpen={isConfigModalOpen}
        onClose={() => setIsConfigModalOpen(false)}
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
          <Input
            label="Mô Tả"
            {...configForm.register('description')}
          />
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={() => setIsConfigModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Lưu Thay Đổi"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Pipeline Modal */}
      <Modal
        isOpen={isPipelineModalOpen}
        onClose={() => setIsPipelineModalOpen(false)}
        title="Khởi Chạy AI Pipeline"
      >
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
              {cameras.map((cam) => (
                <option key={cam.id} value={String(cam.id)}>
                  {(cam.camera_name || cam.name) ?? `Camera ${cam.id}`}
                </option>
              ))}
            </select>
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
            <label htmlFor="enable_ocr" className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest">
              Bật Nhận Diện Mã Tàu (OCR)
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={() => setIsPipelineModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Bắt Đầu Xử Lý"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

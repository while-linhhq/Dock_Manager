import { create } from 'zustand';
import type { CameraRead } from '../../../types/api.types';
import { portApi } from '../services/portApi';
import type {
  DetectionVerify,
  DetectionUpdate,
  CameraCreate,
  PortConfigRead,
  PortConfigUpdate,
  PortConfigCreate,
  PipelineStartRequest,
} from '../services/portApi';

interface PortState {
  cameras: CameraRead[];
  configs: PortConfigRead[];
  isLoading: boolean;
  error: string | null;
  fetchCameras: (activeOnly?: boolean) => Promise<void>;
  fetchConfigs: () => Promise<void>;
  verifyDetection: (id: string, data: DetectionVerify) => Promise<void>;
  updateDetection: (id: string, data: DetectionUpdate) => Promise<void>;
  upsertCamera: (id: string | null, data: CameraCreate) => Promise<void>;
  deleteCamera: (id: string | number) => Promise<void>;
  updateConfig: (key: string, data: PortConfigUpdate) => Promise<void>;
  upsertConfig: (key: string | null, data: PortConfigCreate | PortConfigUpdate) => Promise<void>;
  deleteConfig: (key: string) => Promise<void>;
  deleteDetection: (id: string) => Promise<void>;
  startPipeline: (data: PipelineStartRequest) => Promise<void>;
  stopPipeline: () => Promise<void>;
  shutdownServer: () => Promise<number[]>;
}

export const usePortStore = create<PortState>((set, get) => ({
  cameras: [],
  configs: [],
  isLoading: false,
  error: null,
  fetchCameras: async (activeOnly) => {
    set({ isLoading: true, error: null });
    try {
      const cameras = await portApi.getCameras(activeOnly);
      set({ cameras, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch cameras', isLoading: false });
    }
  },
  fetchConfigs: async () => {
    set({ isLoading: true, error: null });
    try {
      const configs = await portApi.getPortConfigs();
      set({ configs, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch configs', isLoading: false });
    }
  },
  // Danh sách nhận diện không còn nằm trong store: `usePagedQuery` ở PortView giữ
  // trang/bộ lọc/sắp xếp và gọi `reload()` sau mỗi mutation để nạp lại ĐÚNG trang
  // đang xem (thay cho việc tải lại toàn bộ như trước).
  verifyDetection: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.verifyDetection(id, data);
      set({ isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to verify detection', isLoading: false });
      throw err;
    }
  },
  updateDetection: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.updateDetection(id, data);
      set({ isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to update detection', isLoading: false });
      throw err;
    }
  },
  upsertCamera: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      if (id) {
        await portApi.updateCamera(id, data);
      } else {
        await portApi.createCamera(data);
      }
      await get().fetchCameras();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save camera', isLoading: false });
      throw err;
    }
  },
  deleteCamera: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.deleteCamera(id);
      await get().fetchCameras();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete camera', isLoading: false });
      throw err;
    }
  },
  updateConfig: async (key, data) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.updatePortConfig(key, data);
      await get().fetchConfigs();
    } catch (err: any) {
      set({ error: err.message || 'Failed to update config', isLoading: false });
      throw err;
    }
  },
  upsertConfig: async (key, data) => {
    set({ isLoading: true, error: null });
    try {
      if (key) {
        await portApi.updatePortConfig(key, data as PortConfigUpdate);
      } else {
        await portApi.createPortConfig(data as PortConfigCreate);
      }
      await get().fetchConfigs();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save config', isLoading: false });
      throw err;
    }
  },
  deleteConfig: async (key) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.deletePortConfig(key);
      await get().fetchConfigs();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete config', isLoading: false });
      throw err;
    }
  },
  deleteDetection: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.deleteDetection(id);
      set({ isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete detection', isLoading: false });
      throw err;
    }
  },
  startPipeline: async (data) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.startPipeline(data);
      window.dispatchEvent(new CustomEvent('pipeline-status-changed'));
      set({ isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to start pipeline', isLoading: false });
      throw err;
    }
  },
  stopPipeline: async () => {
    set({ isLoading: true, error: null });
    try {
      await portApi.stopPipeline();
      window.dispatchEvent(new CustomEvent('pipeline-status-changed'));
      set({ isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to stop pipeline', isLoading: false });
      throw err;
    }
  },
  shutdownServer: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await portApi.shutdownServer();
      window.dispatchEvent(new CustomEvent('pipeline-status-changed'));
      set({ isLoading: false });
      return res.orphan_ocr_killed ?? [];
    } catch (err: unknown) {
      set({
        error: err instanceof Error ? err.message : 'Failed to shutdown server',
        isLoading: false,
      });
      throw err;
    }
  },
}));

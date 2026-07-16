import { create } from 'zustand';
import type { DetectionRead, CameraRead } from '../../../types/api.types';
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
  detections: DetectionRead[];
  cameras: CameraRead[];
  configs: PortConfigRead[];
  isLoading: boolean;
  error: string | null;
  fetchDetections: (skip?: number, limit?: number, vesselId?: string) => Promise<void>;
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
  detections: [],
  cameras: [],
  configs: [],
  isLoading: false,
  error: null,
  fetchDetections: async (skip, limit, vesselId) => {
    set({ isLoading: true, error: null });
    try {
      // If caller passes explicit paging, honor it. Otherwise load ALL detections
      // by paging through the backend so the client table can filter/sort the full set.
      if (skip !== undefined || limit !== undefined) {
        const detections = await portApi.getDetections(skip, limit, vesselId);
        set({ detections, isLoading: false });
        return;
      }
      const pageSize = 500;
      const all: DetectionRead[] = [];
      let offset = 0;
      // Hard ceiling to avoid an infinite loop if the API ever misbehaves.
      const maxPages = 200;
      for (let page = 0; page < maxPages; page += 1) {
        const batch = await portApi.getDetections(offset, pageSize, vesselId);
        all.push(...batch);
        if (batch.length < pageSize) {
          break;
        }
        offset += pageSize;
      }
      set({ detections: all, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch detections', isLoading: false });
    }
  },
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
  verifyDetection: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.verifyDetection(id, data);
      await get().fetchDetections();
    } catch (err: any) {
      set({ error: err.message || 'Failed to verify detection', isLoading: false });
      throw err;
    }
  },
  updateDetection: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      await portApi.updateDetection(id, data);
      await get().fetchDetections();
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
      await get().fetchDetections();
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

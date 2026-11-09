import { create } from 'zustand';
import type { VesselClassification, VesselRead, VesselTypeRead } from '../../../types/api.types';
import { vesselsApi } from '../services/vesselsApi';
import { enrichVesselReferenceCounts } from '../services/enrichVesselReferenceCounts';
import type { VesselCreate, VesselPageRequest, VesselTypeCreate } from '../services/vesselsApi';

interface VesselState {
  vessels: VesselRead[];
  vesselTypes: VesselTypeRead[];
  isLoading: boolean;
  error: string | null;
  fetchVessels: (
    skip?: number,
    limit?: number,
    activeOnly?: boolean,
    classification?: VesselClassification,
  ) => Promise<void>;
  /**
   * Một trang tàu cho `usePagedQuery` — KHÔNG ghi vào danh mục `vessels` (danh
   * mục đó phục vụ dropdown chọn tàu ở trang đơn hàng / hoá đơn, ghi đè bằng
   * một trang sẽ làm mất tàu khỏi dropdown).
   */
  fetchVesselsPage: (
    request: VesselPageRequest,
  ) => Promise<{ items: VesselRead[]; total: number }>;
  fetchVesselTypes: () => Promise<void>;
  upsertVessel: (id: string | null, data: VesselCreate) => Promise<void>;
  upsertVesselType: (id: string | null, data: VesselTypeCreate) => Promise<void>;
  deleteVessel: (id: string) => Promise<void>;
  deleteVesselType: (id: string) => Promise<void>;
}

export const useVesselStore = create<VesselState>((set, get) => ({
  vessels: [],
  vesselTypes: [],
  isLoading: false,
  error: null,
  fetchVessels: async (skip, limit, activeOnly, classification) => {
    set({ isLoading: true, error: null });
    try {
      const vessels = await vesselsApi.getVessels(skip, limit, activeOnly, classification);
      const withCounts = await enrichVesselReferenceCounts(vessels);
      set({ vessels: withCounts, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch vessels', isLoading: false });
    }
  },
  fetchVesselsPage: async (request) => {
    const page = await vesselsApi.getVesselsPage(request);
    return {
      items: await enrichVesselReferenceCounts(page.items),
      total: page.total,
    };
  },
  fetchVesselTypes: async () => {
    set({ isLoading: true, error: null });
    try {
      const vesselTypes = await vesselsApi.getVesselTypes();
      set({ vesselTypes, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch vessel types', isLoading: false });
    }
  },
  upsertVessel: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      if (id) {
        await vesselsApi.updateVessel(id, data);
      } else {
        await vesselsApi.createVessel(data);
      }
      await get().fetchVessels();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save vessel', isLoading: false });
      throw err;
    }
  },
  upsertVesselType: async (id, data) => {
    set({ isLoading: true, error: null });
    try {
      if (id) {
        await vesselsApi.updateVesselType(id, data);
      } else {
        await vesselsApi.createVesselType(data);
      }
      await get().fetchVesselTypes();
    } catch (err: any) {
      set({ error: err.message || 'Failed to save vessel type', isLoading: false });
      throw err;
    }
  },
  deleteVessel: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await vesselsApi.deleteVessel(id);
      await get().fetchVessels();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete vessel', isLoading: false });
      throw err;
    }
  },
  deleteVesselType: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await vesselsApi.deleteVesselType(id);
      await get().fetchVesselTypes();
    } catch (err: any) {
      set({ error: err.message || 'Failed to delete vessel type', isLoading: false });
      throw err;
    }
  },
}));

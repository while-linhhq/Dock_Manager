import { create } from 'zustand';
import type { VesselRead, VesselTypeRead } from '../../../types/api.types';
import { vesselsApi } from '../services/vesselsApi';
import type { VesselCreate, VesselTypeCreate } from '../services/vesselsApi';

interface VesselState {
  vessels: VesselRead[];
  vesselTypes: VesselTypeRead[];
  isLoading: boolean;
  error: string | null;
  fetchVessels: (skip?: number, limit?: number, activeOnly?: boolean) => Promise<void>;
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
  fetchVessels: async (skip, limit, activeOnly) => {
    set({ isLoading: true, error: null });
    try {
      const vessels = await vesselsApi.getVessels(skip, limit, activeOnly);
      set({ vessels, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Failed to fetch vessels', isLoading: false });
    }
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

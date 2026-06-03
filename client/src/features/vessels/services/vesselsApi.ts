import { httpClient } from '../../../services/httpClient';
import type { VesselRead, VesselTypeRead } from '../../../types/api.types';

export type VesselCreate = {
  ship_id: string;
  name: string;
  vessel_type_id: string;
  owner_info?: string;
  is_active?: boolean;
}

function toApiVesselPayload(data: Partial<VesselCreate> & Record<string, unknown>) {
  const vessel_type_id =
    data.vessel_type_id !== undefined && data.vessel_type_id !== ''
      ? Number(data.vessel_type_id)
      : undefined;
  return {
    ship_id: data.ship_id,
    name: data.name,
    vessel_type_id,
    owner: data.owner_info,
    is_active: data.is_active,
  };
}

export type VesselTypeCreate = {
  type_name: string;
  description?: string;
}

export type VesselVisualReference = {
  id: string;
  preview_url?: string | null;
  payload?: {
    filename?: string;
    enrolled_at?: string;
    source?: string;
    ship_id?: string;
    vessel_name?: string;
    preview_uri?: string;
  };
};

export const vesselsApi = {
  getVessels: async (skip: number = 0, limit: number = 100, activeOnly: boolean = false): Promise<VesselRead[]> => {
    return httpClient.get<VesselRead[]>(`/vessels/?skip=${skip}&limit=${limit}&active_only=${activeOnly}`);
  },
  getVessel: async (id: string): Promise<VesselRead> => {
    return httpClient.get<VesselRead>(`/vessels/${id}`);
  },
  createVessel: async (data: VesselCreate): Promise<VesselRead> => {
    return httpClient.post<VesselRead>('/vessels/', toApiVesselPayload(data));
  },
  updateVessel: async (id: string, data: Partial<VesselCreate>): Promise<VesselRead> => {
    return httpClient.put<VesselRead>(`/vessels/${id}`, toApiVesselPayload(data));
  },
  deleteVessel: async (id: string): Promise<void> => {
    return httpClient.delete(`/vessels/${id}`);
  },
  uploadVesselReferenceImages: async (
    id: string,
    files: File[],
  ): Promise<{
    ok: boolean;
    count?: number;
    enrolled?: Array<{ ok: boolean; point_id: string; filename?: string; source: string }>;
    failed?: Array<{ filename: string; detail: string }>;
    point_id?: string;
    source?: string;
  }> => {
    const form = new FormData();
    files.forEach((file) => form.append('images', file));
    return httpClient.post(`/vessels/${id}/visual-enroll`, form);
  },
  getVesselReferenceImages: async (
    id: string,
  ): Promise<{ count: number; items: VesselVisualReference[] }> => {
    return httpClient.get<{ count: number; items: VesselVisualReference[] }>(
      `/vessels/${id}/visual-enroll`,
    );
  },
  deleteVesselReferenceImage: async (id: string, pointId: string): Promise<void> => {
    return httpClient.delete(`/vessels/${id}/visual-enroll/${pointId}`);
  },
  getVesselTypes: async (): Promise<VesselTypeRead[]> => {
    return httpClient.get<VesselTypeRead[]>('/vessel-types/');
  },
  createVesselType: async (data: VesselTypeCreate): Promise<VesselTypeRead> => {
    return httpClient.post<VesselTypeRead>('/vessel-types/', data);
  },
  updateVesselType: async (id: string, data: VesselTypeCreate): Promise<VesselTypeRead> => {
    return httpClient.put<VesselTypeRead>(`/vessel-types/${id}`, data);
  },
  deleteVesselType: async (id: string): Promise<void> => {
    return httpClient.delete(`/vessel-types/${id}`);
  },
};

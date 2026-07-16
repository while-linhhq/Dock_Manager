import { httpClient } from '../../../services/httpClient';
import type { VesselClassification, VesselRead, VesselTypeRead } from '../../../types/api.types';

export type VesselCreate = {
  ship_id: string;
  name: string;
  /** Phân loại cứng; tab tạo tàu quyết định. Mặc định 'unclassified'. */
  classification?: VesselClassification;
  vessel_type_id?: string;
  owner_info?: string;
  length_m?: string;
  registry_expiry?: string;
  is_active?: boolean;
}

function toApiVesselPayload(data: Partial<VesselCreate> & Record<string, unknown>) {
  const vessel_type_id =
    data.classification === 'monthly' && data.vessel_type_id !== undefined && data.vessel_type_id !== ''
      ? Number(data.vessel_type_id)
      : null;
  const length_m =
    data.length_m !== undefined && data.length_m !== '' && data.length_m !== null
      ? Number(data.length_m)
      : undefined;
  const registry_expiry =
    data.registry_expiry !== undefined && data.registry_expiry !== ''
      ? data.registry_expiry
      : undefined;
  return {
    ship_id: data.ship_id,
    name: data.name,
    classification: data.classification,
    vessel_type_id,
    owner: data.owner_info,
    length_m,
    registry_expiry,
    is_active: data.is_active,
  };
}

export type VesselTypeCreate = {
  type_name: string;
  description?: string;
  /** id tàu (tháng) gán cho loại này — gửi kèm create/update. */
  member_vessel_ids?: number[];
}

/** Tàu dùng cho picker gán vào loại (tàu tháng + chưa phân loại). */
export type AssignableVessel = {
  id: number;
  ship_id: string;
  name?: string | null;
  classification: VesselClassification;
  vessel_type_id?: number | null;
};

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
  getVessels: async (
    skip: number = 0,
    limit: number = 100,
    activeOnly: boolean = false,
    classification?: VesselClassification,
  ): Promise<VesselRead[]> => {
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
      active_only: String(activeOnly),
    });
    if (classification) params.set('classification', classification);
    return httpClient.get<VesselRead[]>(`/vessels/?${params.toString()}`);
  },
  getVisualReferenceCounts: async (): Promise<{ counts: Record<string, number> }> => {
    return httpClient.get<{ counts: Record<string, number> }>('/vessels/visual-reference-counts');
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
  getAssignableVessels: async (): Promise<AssignableVessel[]> => {
    return httpClient.get<AssignableVessel[]>('/vessel-types/assignable-vessels');
  },
  getVesselTypeMembers: async (typeId: string): Promise<AssignableVessel[]> => {
    return httpClient.get<AssignableVessel[]>(`/vessel-types/${typeId}/members`);
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

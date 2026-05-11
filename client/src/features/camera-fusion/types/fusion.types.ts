import type { CameraRead } from '../../../types/api.types';

export type FusionMode = 'layout';
export type PipelineMode = 'hybrid' | 'fused';
export type MemberRole = 'base' | 'overlay' | 'tile';

export type CameraGroupMember = {
  id?: number;
  group_id?: number;
  camera_id: number;
  camera?: CameraRead | null;
  role: MemberRole;
  priority: number;
  layout_x: number;
  layout_y: number;
  layout_w?: number | null;
  layout_h?: number | null;
  layout_rotation: number;
  crop_top: number;
  crop_bottom: number;
  crop_left: number;
  crop_right: number;
  enabled: boolean;
};

export type CameraGroup = {
  id: number;
  name: string;
  description?: string | null;
  fusion_mode: FusionMode;
  pipeline_mode: PipelineMode;
  canvas_width: number;
  canvas_height: number;
  is_active: boolean;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
  members: CameraGroupMember[];
};

export type CameraGroupPayload = {
  name: string;
  description?: string | null;
  fusion_mode: FusionMode;
  pipeline_mode: PipelineMode;
  canvas_width: number;
  canvas_height: number;
  is_active: boolean;
  members: CameraGroupMember[];
};

import type { CameraRead } from '../../../types/api.types';

export type FusionMode = 'layout' | 'homography' | 'panorama';
export type MemberRole = 'base' | 'overlay' | 'tile';
export type PointTuple = [number, number];

export type CalibrationPointPair = {
  src: PointTuple;
  dst: PointTuple;
  label?: string | null;
};

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
  homography?: number[][] | null;
  calibration_points?: CalibrationPointPair[] | null;
  enabled: boolean;
};

export type CameraGroup = {
  id: number;
  name: string;
  description?: string | null;
  fusion_mode: FusionMode;
  canvas_width: number;
  canvas_height: number;
  stitch_metadata?: {
    reference_camera_id?: number;
    pair_stats?: PairMatchStat[];
    unmatched_camera_ids?: number[];
    auto_calibrated_at?: string;
  } | null;
  is_active: boolean;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
  members: CameraGroupMember[];
};

export type PairMatchStat = {
  source_camera_id: number;
  target_camera_id: number;
  matches: number;
  inliers: number;
  confidence: number;
};

export type AutoCalibrateResponse = {
  reference_camera_id: number;
  canvas_width: number;
  canvas_height: number;
  pair_stats: PairMatchStat[];
  unmatched_camera_ids: number[];
};

export type CameraGroupPayload = {
  name: string;
  description?: string | null;
  fusion_mode: FusionMode;
  canvas_width: number;
  canvas_height: number;
  is_active: boolean;
  members: CameraGroupMember[];
};

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

export type StitchMetadata = {
  reference_camera_id?: number;
  camera_order?: number[];
  pair_stats?: PairMatchStat[];
  manual_pairs?: ManualPairPointSet[];
  unmatched_camera_ids?: number[];
  auto_calibrated_at?: string;
  manual_calibrated_at?: string;
  blend_mode?: string;
  blend_weights_shape?: [number, number];
  blend_weights?: Record<string, string>;
  exposure_gains?: Record<string, number>;
  [key: string]: unknown;
};

export type CameraGroup = {
  id: number;
  name: string;
  description?: string | null;
  fusion_mode: FusionMode;
  canvas_width: number;
  canvas_height: number;
  stitch_metadata?: StitchMetadata | null;
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
  stitch_metadata?: StitchMetadata | null;
};

export type AutoCalibrateRequest = {
  referenceCameraId?: number | null;
  cameraOrder: number[];
};

export type ManualPairPointSet = {
  source_camera_id: number;
  target_camera_id: number;
  points: CalibrationPointPair[];
};

export type ManualPairCalibrationRequest = {
  reference_camera_id?: number | null;
  camera_order: number[];
  pairs: ManualPairPointSet[];
};

export type ManualPairCalibrationResponse = AutoCalibrateResponse;

export type CameraGroupPayload = {
  name: string;
  description?: string | null;
  fusion_mode: FusionMode;
  canvas_width: number;
  canvas_height: number;
  is_active: boolean;
  members: CameraGroupMember[];
};

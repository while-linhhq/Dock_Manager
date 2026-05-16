export type SeamAnchorLockRequest = {
  group_id?: number;
  camera_ids?: number[];
  force_capture?: boolean;
};

export type SeamAnchorLockedCamera = {
  camera_id: number;
  source: 'live' | 'capture';
  baseline_path: string | null;
  applied_to_runtime: boolean;
};

export type SeamAnchorLockFailure = {
  camera_id: number;
  reason: string;
};

export type SeamAnchorLockResponse = {
  locked: SeamAnchorLockedCamera[];
  failures: SeamAnchorLockFailure[];
  group_id: number | null;
  used_live_buffer: boolean;
};

export type SeamAnchorBbox = [number, number, number, number];

export type SeamAnchorEntry = {
  global_id: string;
  ship_id: string | null;
  track_id: string;
  cam_a_id: number;
  cam_b_id: number | null;
  bbox_a: SeamAnchorBbox;
  bbox_b: SeamAnchorBbox | null;
  first_seen_ts: number;
  last_seen_ts: number;
  anchored_at: number;
  miss_started_at: number | null;
  last_score_a: number;
  last_score_b: number;
};

export type SeamAnchorDebugInfo = {
  bg_subtract_threshold: number;
  camera_order: number[];
  frame_shapes: Record<string, [number, number]>;
};

export type SeamAnchorStateResponse = {
  enabled: boolean;
  group_id?: number | null;
  anchors: SeamAnchorEntry[];
  debug?: SeamAnchorDebugInfo;
  message?: string;
};

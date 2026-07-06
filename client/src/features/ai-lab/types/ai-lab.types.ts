export type LabOcrHit = {
  id: string;
  confidence: number;
  raw_text: string;
};

export type LabOcrResponse = {
  filename: string;
  ocr_device: string | null;
  processing_ms: number;
  image_size: { width: number; height: number };
  matched: boolean;
  ship_ids: LabOcrHit[];
  jpeg_base64: string;
};

export type LabOcrSnapshot = {
  last_id: string;
  last_confidence: number;
  voted_id: string | null;
  attempts: number;
  votes: Record<string, { count: number; total_conf: number }>;
};

export type LabBoatDetection = {
  track_id: string;
  state: string;
  confidence: number;
  box: [number, number, number, number];
  ship_id: string | null;
  ocr?: LabOcrSnapshot | null;
};

export type LabDetectionFrame = {
  frame_index: number;
  time_sec: number;
  jpeg_base64: string;
  boats: LabBoatDetection[];
};

export type LabDetectionResponse = {
  filename: string;
  media_type: 'image' | 'video';
  total_frames: number;
  sampled_frames: number;
  frame_stride?: number;
  ocr_enabled?: boolean;
  ocr_device?: string | null;
  frames: LabDetectionFrame[];
};

export type LabVisualMatch = {
  point_id: string;
  score: number;
  similarity_percent: number;
  ship_id: string;
  vessel_id: number | null;
  vessel_name: string;
  filename: string;
  preview_url: string | null;
};

export type LabVisualShipRank = {
  ship_id: string;
  aggregated_score: number;
  similarity_percent: number;
  hit_count: number;
  point_ids: string[];
  vessel_id: number | null;
  vessel_name: string;
  filename: string;
  preview_url: string | null;
};

export type LabVisualSearchResponse = {
  filename: string;
  has_match: boolean;
  accepted: boolean;
  match: LabVisualMatch | null;
  ranked_ships: LabVisualShipRank[];
  margin: number;
  source: string;
  confidence: number;
};


export type LabGroupCameraFrame = {
  camera_id: number;
  filename: string;
  jpeg_base64: string;
  boats: LabBoatDetection[];
};

export type LabGroupFrame = {
  frame_index: number;
  time_sec: number;
  fused_jpeg_base64?: string | null;
  cameras: LabGroupCameraFrame[];
};

export type LabGroupVideo = {
  camera_id: number;
  filename: string;
  total_frames: number;
  fps: number;
};

export type LabGroupCamResponse = {
  media_type: 'group_video';
  group_id?: number | null;
  group_name?: string | null;
  camera_count: number;
  videos: LabGroupVideo[];
  sampled_frames: number;
  frame_stride: number;
  ocr_enabled?: boolean;
  ocr_device?: string | null;
  frames: LabGroupFrame[];
};

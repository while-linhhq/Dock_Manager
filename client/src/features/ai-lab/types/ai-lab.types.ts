export type LabBoatDetection = {
  track_id: string;
  state: string;
  confidence: number;
  box: [number, number, number, number];
  ship_id: string | null;
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

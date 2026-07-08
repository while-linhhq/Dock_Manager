import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Plus, Power, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import type { PortConfigRead } from '../services/portApi';

/** Legacy frame keys — hidden after migration to second-based port_configs. */
const DEPRECATED_CONFIG_KEYS = new Set([
  'ocr_interval_frames',
  'track_min_hits',
  'track_max_tentative_misses',
  'track_max_lost_frames',
  'training_snapshot_min_ocr_confidence',
  'training_snapshot_min_visual_confidence',
  'visual_margin_threshold',
  'visual_consensus_count',
]);
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

type CategoryId =
  | 'model'
  | 'ocr'
  | 'visual'
  | 'redis'
  | 'qdrant'
  | 'snapshot'
  | 'track'
  | 'record'
  | 'reid'
  | 'seam'
  | 'anchor'
  | 'bg'
  | 'fused'
  | 'threads'
  | 'other';

interface Category {
  id: CategoryId;
  label: string;
  description: string;
  color: string;
}

const CATEGORIES: Category[] = [
  { id: 'model', label: 'Mô hình & Nhận diện', description: 'Tham số YOLO: model, confidence, imgsz, resize, CLAHE', color: 'text-violet-500 bg-violet-500/10 border-violet-500/20' },
  { id: 'ocr', label: 'OCR', description: 'Nhận diện mã tàu, chu kỳ OCR, log audit', color: 'text-blue-500 bg-blue-500/10 border-blue-500/20' },
  { id: 'visual', label: 'Visual ID', description: 'Nhận diện tàu bằng embedding DINOv2 + Qdrant', color: 'text-fuchsia-500 bg-fuchsia-500/10 border-fuchsia-500/20' },
  { id: 'redis', label: 'Redis', description: 'Cache runtime cho visual worker', color: 'text-rose-500 bg-rose-500/10 border-rose-500/20' },
  { id: 'qdrant', label: 'Qdrant', description: 'Vector DB cho tìm kiếm embedding tàu', color: 'text-lime-500 bg-lime-500/10 border-lime-500/20' },
  { id: 'snapshot', label: 'Training Snapshot', description: 'Thu thập crop tàu chất lượng cao để train model', color: 'text-sky-500 bg-sky-500/10 border-sky-500/20' },
  { id: 'track', label: 'Theo dõi (Tracking)', description: 'IoU, thời gian xác nhận/lost (giây), cửa sổ Re-ID', color: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20' },
  { id: 'record', label: 'Ghi Video', description: 'Bật/tắt recording, FPS, thời lượng tối đa', color: 'text-orange-500 bg-orange-500/10 border-orange-500/20' },
  { id: 'reid', label: 'Nhúng Re-ID', description: 'Model embedding, ngưỡng similarity, handoff', color: 'text-cyan-500 bg-cyan-500/10 border-cyan-500/20' },
  { id: 'seam', label: 'Seam / Vùng', description: 'Seam anchor, ROI, tỉ lệ primary/edge zone', color: 'text-pink-500 bg-pink-500/10 border-pink-500/20' },
  { id: 'anchor', label: 'Anchor (định danh neo)', description: 'Resurrect IoU, embedding match, khoảng “grace”', color: 'text-amber-500 bg-amber-500/10 border-amber-500/20' },
  { id: 'bg', label: 'Tách nền (Background)', description: 'Các tham số MOG2: history/variance/threshold', color: 'text-teal-500 bg-teal-500/10 border-teal-500/20' },
  { id: 'fused', label: 'Frame Fused', description: 'Giới hạn kích thước frame tổng hợp multi-camera', color: 'text-indigo-500 bg-indigo-500/10 border-indigo-500/20' },
  { id: 'threads', label: 'CPU Threads', description: 'Giới hạn thread cho torch/paddle/OpenCV để tránh CPU oversubscribe', color: 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20' },
  { id: 'other', label: 'Khác', description: 'Các cấu hình không thuộc nhóm trên', color: 'text-gray-400 bg-gray-500/10 border-gray-500/20' },
];

const KEY_PREFIX_MAP: Record<string, CategoryId> = {
  model_path: 'model',
  device: 'model',
  conf: 'model',
  yolo_imgsz: 'model',
  resize_scale: 'model',
  clahe_clip_limit: 'model',
  clahe_tile_size: 'model',
  clahe_enable_gray_world: 'model',
  primary_zone_ratio: 'seam',
  edge_zone_ratio: 'seam',
  detection_confidence_threshold: 'ocr',
  ship_id_lock_stable_sec: 'ocr',
  enable_ocr: 'ocr',
  ship_id_require_catalog: 'ocr',
  ocr_interval_sec: 'ocr',
  ocr_second_pass_conf_threshold: 'ocr',
  ocr_label_ttl_sec: 'ocr',
  ocr_audit_enable: 'ocr',
  ocr_audit_save_frames: 'ocr',
  save_min_interval_sec: 'ocr',
  enable_visual_id: 'visual',
  visual_id_interval_sec: 'visual',
  visual_min_crop_area: 'visual',
  visual_match_threshold: 'visual',
  visual_no_ocr_match_threshold: 'visual',
  visual_conflict_threshold: 'visual',
  visual_top_k: 'visual',
  visual_model_path: 'visual',
  visual_backbone: 'visual',
  visual_embedding_dim: 'visual',
  visual_batch_size: 'visual',
  visual_device: 'visual',
  redis_url: 'redis',
  redis_key_prefix: 'redis',
  redis_visual_ttl_sec: 'redis',
  qdrant_host: 'qdrant',
  qdrant_port: 'qdrant',
  qdrant_api_key: 'qdrant',
  qdrant_collection: 'qdrant',
  qdrant_vector_size: 'qdrant',
  qdrant_distance: 'qdrant',
  enable_training_snapshot: 'snapshot',
  training_snapshot_interval_sec: 'snapshot',
  training_snapshot_base_dir: 'snapshot',
  training_snapshot_jpeg_quality: 'snapshot',
  track_min_confirm_sec: 'track',
  track_max_tentative_sec: 'track',
  track_max_lost_sec: 'track',
  track_iou_threshold: 'track',
  track_dedup_iomin_threshold: 'track',
  berth_out_grace_sec: 'track',
  track_reid_window_sec: 'track',
  track_reid_max_dist: 'track',
  track_min_berth_duration_sec: 'track',
  berth_merge_gap_sec: 'track',
  detection_merge_window_hours: 'track',
  berth_merge_skip_unknown: 'track',
  sync_tolerance_ms: 'track',
  thread_caps_enabled: 'threads',
  thread_omp_threads: 'threads',
  thread_torch_threads: 'threads',
  thread_cv2_threads: 'threads',
  thread_ocr_omp_threads: 'threads',
  thread_ocr_cv2_threads: 'threads',
  thread: 'threads',
  record_enable: 'record',
  record_max_duration_min: 'record',
  record_no_boat_gap_sec: 'record',
  record_fps: 'record',
  reid_embedding_model_path: 'reid',
  reid_visual_threshold: 'reid',
  reid_handoff_window_sec: 'reid',
  reid_overlap_merge_enabled: 'reid',
  reid_edge_zone_ratio: 'reid',
  reid_embedding_weight: 'reid',
  reid_color_weight: 'reid',
  reid_size_weight: 'reid',
  reid_accept_threshold: 'reid',
  reid_min_margin: 'reid',
  reid_directional_handoff_enabled: 'reid',
  reid_directional_max_transit_sec: 'reid',
  reid_directional_min_transit_sec: 'reid',
  reid_directional_min_velocity_px: 'reid',
  reid_directional_edge_zone_ratio: 'reid',
  reid_directional_embedding_weight: 'reid',
  reid_directional_direction_weight: 'reid',
  reid_directional_time_weight: 'reid',
  reid_directional_accept_threshold: 'reid',
  reid_directional_embedding_floor: 'reid',
  reid_reverse_motion_guard_enabled: 'reid',
  reid_embedding_diversity_max_cos: 'reid',
  seam_anchor_enabled: 'seam',
  seam_roi_width_ratio: 'seam',
  seam_proximity_px: 'seam',
  bg_subtract_threshold: 'bg',
  bg_model_history: 'bg',
  bg_var_threshold: 'bg',
  bg_min_seed_frames: 'bg',
  fused_frame_max_width: 'fused',
  fused_frame_max_height: 'fused',
  anchor_iou_resurrect_threshold: 'anchor',
  anchor_embedding_match_enabled: 'anchor',
  anchor_embedding_sim_threshold: 'anchor',
  anchor_revalidation_sec: 'anchor',
  anchor_departed_grace_sec: 'anchor',
  anchor_max_duration_sec: 'anchor',
  anchor_db_update_debounce_sec: 'anchor',
  anchor_min_stationary_sec: 'anchor',
  anchor_color_hsv_tolerance_h: 'anchor',
};

function getCategoryId(key: string): CategoryId {
  if (key in KEY_PREFIX_MAP) return KEY_PREFIX_MAP[key];
  for (const prefix of ['anchor_', 'seam_', 'reid_', 'record_', 'track_', 'thread_', 'ocr_', 'bg_', 'fused_', 'visual_', 'redis_', 'qdrant_', 'training_snapshot_', 'enable_training_snapshot']) {
    if (key.startsWith(prefix)) return KEY_PREFIX_MAP[prefix.replace('_', '')] ?? 'other';
  }
  return 'other';
}

const KEY_VI_DESCRIPTION: Partial<Record<string, string>> = {
  port_name: 'Tên hiển thị của cảng.',
  detection_confidence_threshold: 'Ngưỡng tổng confidence OCR pool tối thiểu để kết quả OCR được chấp nhận là hợp lệ.',
  ship_id_lock_stable_sec: 'Thời gian (giây) mã tàu phải ổn định liên tục trước khi bị khóa (lock). 0 = tắt lock.',
  invoice_tax_rate: 'Thuế mặc định cho hóa đơn (ví dụ 0.1 = 10%).',
  invoice_due_days: 'Số ngày đến hạn hóa đơn.',

  model_path: 'Đường dẫn file model YOLO.',
  device: 'Thiết bị suy luận: `0` (GPU) hoặc `cpu` (CPU).',
  conf: 'Ngưỡng confidence của YOLO detection.',
  yolo_imgsz:
    'Kích thước input YOLO (letterbox, ví dụ 640 hoặc 960). Nên khớp với imgsz lúc fine-tune; restart pipeline sau khi đổi.',
  resize_scale: 'Tỉ lệ resize frame cho overlay/preview (không ảnh hưởng YOLO imgsz).',
  clahe_clip_limit: 'Thông số CLAHE (giới hạn độ tương phản).',
  clahe_tile_size: 'Thông số CLAHE (kích thước tile).',
  clahe_enable_gray_world: 'Bật cân bằng trắng gray-world trước CLAHE. Đây là bước xử lý ảnh NẶNG NHẤT chạy mỗi frame (kể cả khi không có tàu). Tắt để test xem YOLO còn detect tốt không — tắt giúp giảm tải CPU đáng kể. Restart pipeline sau khi đổi.',

  thread_caps_enabled: 'Bật giới hạn thread CPU cho torch/paddle/OpenCV/OpenBLAS. Tắt = dùng mặc định thư viện, dễ oversubscribe. Restart server sau khi đổi.',
  thread_omp_threads: 'Số thread OMP/MKL/OpenBLAS/NumExpr cho process chính. Khuyến nghị 4 trên máy 16 thread.',
  thread_torch_threads: 'Số thread CPU của torch trong process chính. Khuyến nghị 4.',
  thread_cv2_threads: 'Số thread OpenCV trong process chính. Khuyến nghị 2.',
  thread_ocr_omp_threads: 'Số thread OMP/MKL/OpenBLAS/torch cho OCR subprocess. Khuyến nghị 3.',
  thread_ocr_cv2_threads: 'Số thread OpenCV cho OCR subprocess. Khuyến nghị 2.',

  enable_ocr: 'Bật/tắt OCR toàn cục.',
  ocr_interval_sec: 'Khoảng thời gian (giây) giữa các lần OCR.',
  ocr_second_pass_conf_threshold: 'Ngưỡng confidence để bỏ qua OCR pass 2 (CLAHE). 0.85 = nếu pass 1 đủ tự tin thì không chạy pass 2. <=0 = luôn chạy cả hai pass.',
  ocr_label_ttl_sec: 'Thời gian hiển thị nhãn OCR trên UI (giây).',
  ocr_audit_enable: 'Bật/tắt audit logging cho OCR.',
  ocr_audit_save_frames: 'Lưu frame đầy đủ phục vụ OCR audit.',
  save_min_interval_sec: 'Khoảng thời gian tối thiểu giữa các lần lưu ảnh detection (giây).',

  enable_visual_id: 'Bật/tắt nhận diện tàu bằng đặc trưng sâu (manual enrollment + vector search).',
  visual_id_interval_sec: 'Khoảng thời gian (giây) giữa các lần visual-id trên track CONFIRMED.',
  visual_min_crop_area: 'Diện tích crop tối thiểu (pixel) để chạy trích đặc trưng.',
  visual_match_threshold:
    'Ngưỡng similarity (0–1) khi đã có OCR: lọc Qdrant + điều kiện embedding thắng OCR khi conflict.',
  visual_no_ocr_match_threshold:
    'Ngưỡng similarity (0–1) chấp nhận mã tàu từ embedding khi OCR không có kết quả.',
  visual_conflict_threshold:
    'Ngưỡng similarity tối thiểu để embedding ghi đè OCR khi hai phương pháp cho kết quả khác nhau.',
  visual_top_k: 'Số ứng viên gần nhất trả về từ vector search.',
  visual_model_path: 'Đường dẫn model TorchScript (để trống = DINOv2 timm mặc định).',
  visual_backbone: 'Tên backbone timm (mặc định `vit_base_patch14_dinov2`).',
  visual_embedding_dim: 'Kích thước vector embedding đầu ra.',
  visual_batch_size: 'Batch size cho visual embedding worker.',
  visual_device: 'Thiết bị suy luận visual (`0`, `cuda:0`, `cpu`).',

  redis_url: 'URL kết nối Redis dùng cho runtime cache.',
  redis_key_prefix: 'Prefix key trên Redis để tách namespace dự án.',
  redis_visual_ttl_sec: 'TTL (giây) cho cache visual-id runtime.',

  qdrant_host: 'Host Qdrant.',
  qdrant_port: 'Port HTTP API Qdrant.',
  qdrant_api_key: 'API key Qdrant (để trống nếu local không auth).',
  qdrant_collection: 'Tên collection lưu embedding tàu.',
  qdrant_vector_size: 'Số chiều vector embedding.',
  qdrant_distance: 'Metric khoảng cách vector: COSINE / DOT / EUCLID.',

  enable_training_snapshot: 'Bật/tắt thu thập crop tàu để train model (lưu vào server/snapshot).',
  training_snapshot_interval_sec: 'Chu kỳ (giây) chụp và lưu snapshot mỗi camera.',
  training_snapshot_base_dir: 'Thư mục gốc (tương đối server/ hoặc đường dẫn tuyệt đối).',
  training_snapshot_jpeg_quality: 'Chất lượng JPEG (50–100) cho ảnh crop.',

  track_min_confirm_sec: 'Thời gian (giây) trước khi TENTATIVE thành CONFIRMED.',
  track_max_tentative_sec: 'Thời gian tối đa (giây) không match trước khi xóa tentative track.',
  track_max_lost_sec: 'Thời gian tối đa (giây) ở LOST trước khi xóa track.',
  track_iou_threshold: 'Ngưỡng IoU để ghép detections vào cùng track.',
  track_dedup_iomin_threshold:
    'Lọc bbox nhiễu trùng cho cùng một tàu: nếu 2 box chồng nhau với IoMin (giao / diện tích box nhỏ hơn) ≥ ngưỡng này thì bỏ box confidence thấp trước khi vào tracker (bắt trường hợp box lồng nhau mà NMS bỏ sót). 0 = tắt. Gợi ý 0.7–0.85.',
  track_reid_window_sec: 'Cửa sổ thời gian (giây) để Re-ID.',
  berth_out_grace_sec:
    'Ân hạn (giây) trước khi chốt tín hiệu OUT. Khi tàu vượt ra ngoài vùng neo, hệ thống chưa coi là RA ngay: OUT chỉ được xác nhận nếu tàu ở NGOÀI vùng liên tục ≥ ngưỡng này. Nếu trong thời gian ân hạn tàu vào lại vùng (đang căn góc, lùi neo) thì OUT bị hủy (unlock), berth_out không bị chốt sai → tránh tính sai thời gian neo đậu và chi phí. 0 = tắt (chốt OUT ngay khi vượt ngưỡng, như cũ). Gợi ý 15–60s tùy thời gian tàu thường maneuver.',
  track_reid_max_dist: 'Khoảng cách tối đa dùng cho Re-ID không gian.',
  track_min_berth_duration_sec:
    'Thời gian neo đậu tối thiểu (giây) để track được tính là detection, kể cả UNKNOWN. Dùng berth_out−berth_in, fallback dwell (last_seen−first_seen). Track ngắn hơn ngưỡng bị bỏ qua hoàn toàn (không lưu, không gửi Zalo). 0 = tắt lọc.',
  berth_merge_gap_sec:
    'Ngưỡng khoảng TRỐNG (giây) để gộp 2 detection cùng tàu thành 1 lượt neo. Gap = berth_in(lượt sau) − berth_out(lượt trước). Gap < ngưỡng: track bị đứt rồi nối lại trong cùng một lượt → GỘP (giữ berth_in sớm nhất, berth_out muộn nhất). Gap ≥ ngưỡng: tàu đã rời bến thật rồi mới quay lại → giữ 2 lượt RIÊNG (không mất detection). Dựa trên đồ thị gap thực tế: track-chết-nối-lại ≤30 phút, rời-thật-quay-lại 40–60 phút → mặc định 1800 (30 phút) nằm đúng đáy thung lũng. Tăng nếu tàu hay đứt track lâu; giảm nếu tàu quay lại nhanh bị gộp oan. 0 = tắt gộp theo gap (chỉ còn gộp khi 2 cửa sổ THẬT SỰ chồng lấn).',
  detection_merge_window_hours:
    'Bán kính (giờ) lưới lọc ỨNG VIÊN thô khi tìm detection cùng tàu để xét gộp. Chỉ giới hạn phạm vi query cho rẻ, KHÔNG tự quyết định gộp (việc gộp do berth_merge_gap_sec + chồng lấn quyết). Phải RỘNG hơn ngưỡng gộp; hệ thống tự nới rộng theo berth_merge_gap_sec nếu cần. Mặc định 2 giờ là đủ cho mọi lượt neo trong ngày.',
  berth_merge_skip_unknown:
    'BẬT (true) = KHÔNG gộp các detection UNKNOWN (tàu chưa xác nhận danh tính). Lý do: mọi tàu UNKNOWN đều trỏ về CÙNG một vessel "UNKNOWN", nên nếu gộp theo vessel_id sẽ trộn nhiều con tàu khác nhau thành một lượt sai. Giữ riêng từng detection UNKNOWN cho tới khi Zalo bot xác nhận mã tàu — lúc reassign sang vessel thật, hệ tự động chạy coalesce để gộp lại các mảnh cùng lượt của đúng tàu đó. TẮT (false) = gộp cả UNKNOWN (KHÔNG khuyến nghị, dễ trộn nhầm tàu).',
  sync_tolerance_ms:
    'Sai số tối đa giữa các camera trong cùng batch (ms). Tăng nếu RTSP chậm; giảm nếu cần khớp chặt hơn.',

  record_enable: 'Bật/tắt ghi video cho detections.',
  record_max_duration_min: 'Thời lượng ghi video tối đa (phút).',
  record_no_boat_gap_sec: 'Thời gian chờ sau khi tàu rời để dừng ghi (giây).',
  record_fps: 'FPS cho pipeline/ghi video.',

  reid_embedding_model_path: 'Đường dẫn model dùng để tạo embedding Re-ID.',
  reid_visual_threshold: 'Ngưỡng hiển thị/quality cho embedding Re-ID.',
  reid_handoff_window_sec: 'Cửa sổ handoff (giây) khi chuyển track/Re-ID.',
  reid_overlap_merge_enabled: 'Bật merge khi tàu thấy đồng thời trên 2 camera kề (overlap FOV).',
  reid_edge_zone_ratio: 'Bề rộng vùng overlap (tỉ lệ width) để xét merge cross-camera.',
  reid_embedding_weight: 'Trọng số embedding trong fusion score merge.',
  reid_color_weight: 'Trọng số HSV similarity trong fusion score merge.',
  reid_size_weight: 'Trọng số tỉ lệ kích thước box trong fusion score merge.',
  reid_accept_threshold: 'Ngưỡng tổng score mềm để chấp nhận merge.',
  reid_min_margin: 'Chênh score tối thiểu so với candidate #2 (chống nhầm).',
  reid_directional_handoff_enabled: 'Bật handoff tuần tự khi tàu rời cam này sang cam kề (không cần OCR).',
  reid_directional_max_transit_sec: 'Thời gian tối đa (giây) tàu di chuyển giữa 2 cam kề để coi là handoff hợp lệ.',
  reid_directional_min_transit_sec: 'Dung sai âm (giây): xuất hiện sớm hơn = concurrent (để overlap merge xử lý).',
  reid_directional_min_velocity_px: 'Vận tốc ngang tối thiểu (px/giây) để xác định hướng di chuyển rõ ràng.',
  reid_directional_edge_zone_ratio: 'Bề rộng vùng biên (tỉ lệ width) tàu phải xuất hiện ở cam nhận.',
  reid_directional_embedding_weight: 'Trọng số embedding trong score handoff hướng.',
  reid_directional_direction_weight: 'Trọng số khớp hướng di chuyển trong score handoff.',
  reid_directional_time_weight: 'Trọng số hợp lý thời gian trong score handoff.',
  reid_directional_accept_threshold: 'Ngưỡng tổng score để chấp nhận handoff hướng.',
  reid_directional_embedding_floor: 'Sàn embedding cosine: dưới ngưỡng này không merge dù hướng/thời gian khớp.',
  reid_reverse_motion_guard_enabled: 'Chặn tạo IN giả khi tàu lùi ra chạm lại vùng cam trước (đã có OUT).',
  reid_embedding_diversity_max_cos: 'Trần đa dạng buffer embedding: bỏ vector có cosine >= mức này so với vector kề trước (mặc định 0.98). 1.0 = tắt gate (giữ hành vi cũ).',

  seam_anchor_enabled: 'Bật seam anchor để giữ ID khi tàu neo ở ranh giới 2 camera.',
  seam_roi_width_ratio: 'Tỉ lệ bề rộng vùng ROI cho seam (theo width camera kề).',
  seam_proximity_px: 'Khoảng cách (px) từ bbox tới cạnh để coi là có anchor.',
  primary_zone_ratio: 'Tỉ lệ vùng primary khi phân vùng seam/zone.',
  edge_zone_ratio: 'Tỉ lệ vùng edge khi phân vùng seam/zone.',

  bg_subtract_threshold: 'Ngưỡng tỉ lệ foreground để coi seam là OCCUPIED.',
  bg_model_history: 'history của MOG2 background model.',
  bg_var_threshold: 'varThreshold của MOG2.',
  bg_min_seed_frames: 'Số frame seed trước khi background model sẵn sàng.',

  fused_frame_max_width: 'Giới hạn chiều rộng frame fused.',
  fused_frame_max_height: 'Giới hạn chiều cao frame fused.',

  anchor_iou_resurrect_threshold: 'IoU tối thiểu để resurrect anchor khi YOLO detect lại.',
  anchor_embedding_match_enabled: 'Bật so khớp embedding khi re-validate / resurrect.',
  anchor_embedding_sim_threshold: 'Cosine similarity tối thiểu cho embedding match.',
  anchor_revalidation_sec: 'Chu kỳ re-validate appearance (giây).',
  anchor_departed_grace_sec: 'Khoảng “grace” trước khi coi tàu đã rời (giây).',
  anchor_max_duration_sec: 'Thời gian tối đa giữ anchor (giây) để tránh kẹt vô hạn.',
  anchor_db_update_debounce_sec: 'Debounce cập nhật last_seen vào DB (giây).',
  anchor_min_stationary_sec: 'Thời gian tàu STATIC tối thiểu trước khi anchor được tạo.',
  anchor_color_hsv_tolerance_h: 'Dung sai Hue (độ) khi so màu re-validate anchor.',
};

export type PortConfigsSectionProps = {
  cfgKeyQ: string;
  setCfgKeyQ: (v: string) => void;
  cfgValQ: string;
  setCfgValQ: (v: string) => void;
  resetCfgFilters: () => void;
  cfgFilterCount: number;
  onOpenAddConfig: () => void;
  filteredConfigs: PortConfigRead[];
  configs: PortConfigRead[];
  onEditConfig: (cfg: PortConfigRead) => void;
  onDeleteConfig: (key: string) => void;
  onToggleConfig: (key: string, value: string, description: string) => void;
  onShutdownServer: () => void;
};

/** Recognize boolean-valued configs so they render as a toggle, not free text. */
const BOOL_VALUES = new Set(['true', 'false']);
const isBoolValue = (value: string): boolean =>
  BOOL_VALUES.has((value ?? '').trim().toLowerCase());

export const PortConfigsSection: React.FC<PortConfigsSectionProps> = ({
  cfgKeyQ,
  setCfgKeyQ,
  cfgValQ,
  setCfgValQ,
  resetCfgFilters,
  cfgFilterCount,
  onOpenAddConfig,
  filteredConfigs,
  configs,
  onEditConfig,
  onDeleteConfig,
  onToggleConfig,
  onShutdownServer,
}) => {
  const [collapsedCategories, setCollapsedCategories] = useState<Set<CategoryId>>(new Set());

  const toggleCategory = (id: CategoryId) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const visibleConfigs = React.useMemo(
    () => filteredConfigs.filter((cfg) => !DEPRECATED_CONFIG_KEYS.has(cfg.key)),
    [filteredConfigs],
  );

  const grouped = React.useMemo(() => {
    const map = new Map<CategoryId, PortConfigRead[]>();
    for (const cfg of visibleConfigs) {
      const catId = getCategoryId(cfg.key);
      if (!map.has(catId)) map.set(catId, []);
      map.get(catId)!.push(cfg);
    }
    // Stable ordering by key so a row keeps its position after an update.
    // Without this, the server may return configs in a different order after
    // each save (by id/updated_at), making the edited row jump around.
    for (const items of map.values()) {
      items.sort((a, b) => a.key.localeCompare(b.key));
    }
    return map;
  }, [visibleConfigs]);

  const activeCategories = CATEGORIES.filter((cat) => grouped.has(cat.id));

  return (
    <div className="space-y-4">
      <TableFilterPanel
        title="Bộ lọc cấu hình"
        onReset={resetCfgFilters}
        activeCount={cfgFilterCount}
      >
        <FilterField label="Key">
          <input
            type="text"
            value={cfgKeyQ}
            onChange={(e) => setCfgKeyQ(e.target.value)}
            placeholder="Chứa..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Giá trị / mô tả">
          <input
            type="text"
            value={cfgValQ}
            onChange={(e) => setCfgValQ(e.target.value)}
            placeholder="Chứa..."
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
          Cấu Hình Cảng
        </h3>
        <Button
          type="button"
          onClick={onOpenAddConfig}
          className="bg-blue-600 hover:bg-blue-700 text-white"
        >
          <Plus className="w-4 h-4 mr-2" />
          Thêm Config
        </Button>
      </div>

      {visibleConfigs.length === 0 ? (
        <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl p-12 text-center text-gray-500 text-xs uppercase font-mono">
          {configs.length === 0 ? 'Chưa có cấu hình' : 'Không có mục khớp bộ lọc'}
        </div>
      ) : (
        <div className="space-y-3">
          {activeCategories.map((cat) => {
            const items = grouped.get(cat.id) ?? [];
            const isCollapsed = collapsedCategories.has(cat.id);
            return (
              <div
                key={cat.id}
                className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => toggleCategory(cat.id)}
                  className="w-full flex items-center justify-between p-4 hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors text-left"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        'inline-flex items-center px-2.5 py-0.5 rounded-full border text-[10px] font-bold uppercase tracking-wider',
                        cat.color,
                      )}
                    >
                      {cat.label}
                    </span>
                    <span className="text-[10px] text-gray-400 dark:text-gray-500 hidden sm:inline">
                      {cat.description}
                    </span>
                    <span className="text-[10px] font-mono text-gray-400 ml-1">
                      ({items.length})
                    </span>
                  </div>
                  {isCollapsed ? (
                    <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
                  )}
                </button>

                {!isCollapsed && (
                  <div className="divide-y divide-gray-100 dark:divide-white/5 border-t border-gray-100 dark:border-white/5">
                    {items.map((cfg) => (
                      <div
                        key={cfg.key}
                        className="px-4 py-3 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-gray-50 dark:hover:bg-white/[0.01] transition-colors"
                      >
                        <div>
                          <p className="text-xs font-bold text-gray-900 dark:text-white uppercase font-mono">
                            {cfg.key}
                          </p>
                          {(KEY_VI_DESCRIPTION[cfg.key] ?? cfg.description) && (
                            <p className="text-[10px] text-gray-500 uppercase tracking-widest mt-0.5">
                              {KEY_VI_DESCRIPTION[cfg.key] ?? cfg.description}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-4 shrink-0">
                          {isBoolValue(cfg.value) ? (
                            (() => {
                              const on = cfg.value.trim().toLowerCase() === 'true';
                              return (
                                <button
                                  type="button"
                                  onClick={() =>
                                    onToggleConfig(
                                      cfg.key,
                                      on ? 'false' : 'true',
                                      cfg.description ?? '',
                                    )
                                  }
                                  role="switch"
                                  aria-checked={on}
                                  className={cn(
                                    'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                                    on ? 'bg-emerald-500' : 'bg-gray-300 dark:bg-white/10',
                                  )}
                                >
                                  <span
                                    className={cn(
                                      'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                                      on ? 'translate-x-6' : 'translate-x-1',
                                    )}
                                  />
                                </button>
                              );
                            })()
                          ) : (
                            <>
                              <span className="px-3 py-1.5 bg-gray-100 dark:bg-white/5 rounded-lg text-xs font-mono text-blue-500 font-bold max-w-[200px] truncate">
                                {cfg.value}
                              </span>
                              <button
                                type="button"
                                onClick={() => onEditConfig(cfg)}
                                className="text-[10px] font-bold text-blue-600 hover:text-blue-500 uppercase tracking-widest"
                              >
                                Thay Đổi
                              </button>
                            </>
                          )}
                          <button
                            type="button"
                            onClick={() => onDeleteConfig(cfg.key)}
                            className="text-[10px] font-bold text-red-600 hover:text-red-500 uppercase tracking-widest inline-flex items-center gap-1"
                          >
                            <Trash2 className="w-3 h-3" />
                            Xóa
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="bg-white dark:bg-[#121214] border border-red-200 dark:border-red-500/20 rounded-2xl shadow-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <p className="text-xs font-bold text-red-600 dark:text-red-400 uppercase tracking-widest">
            Ngắt Server
          </p>
          <p className="text-[10px] text-gray-500 uppercase tracking-widest mt-0.5">
            Dừng pipeline, kill orphan OCR đang giữ VRAM, rồi tắt tiến trình server. Cần khởi động lại thủ công.
          </p>
        </div>
        <Button
          type="button"
          onClick={onShutdownServer}
          className="bg-red-600 hover:bg-red-700 text-white shrink-0"
        >
          <Power className="w-4 h-4 mr-2" />
          Ngắt Server
        </Button>
      </div>
    </div>
  );
};

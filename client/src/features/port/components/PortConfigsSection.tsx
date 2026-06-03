import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react';
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
  | 'other';

interface Category {
  id: CategoryId;
  label: string;
  description: string;
  color: string;
}

const CATEGORIES: Category[] = [
  { id: 'model', label: 'Mô hình & Nhận diện', description: 'Tham số YOLO: model, confidence, resize, CLAHE', color: 'text-violet-500 bg-violet-500/10 border-violet-500/20' },
  { id: 'ocr', label: 'OCR', description: 'Nhận diện mã tàu, chu kỳ OCR, log audit', color: 'text-blue-500 bg-blue-500/10 border-blue-500/20' },
  { id: 'visual', label: 'Visual ID', description: 'Nhận diện tàu bằng đặc trưng sâu (ViT)', color: 'text-fuchsia-500 bg-fuchsia-500/10 border-fuchsia-500/20' },
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
  { id: 'other', label: 'Khác', description: 'Các cấu hình không thuộc nhóm trên', color: 'text-gray-400 bg-gray-500/10 border-gray-500/20' },
];

const KEY_PREFIX_MAP: Record<string, CategoryId> = {
  model_path: 'model',
  device: 'model',
  conf: 'model',
  resize_scale: 'model',
  clahe_clip_limit: 'model',
  clahe_tile_size: 'model',
  primary_zone_ratio: 'seam',
  edge_zone_ratio: 'seam',
  enable_ocr: 'ocr',
  ocr_interval_sec: 'ocr',
  ocr_label_ttl_sec: 'ocr',
  ocr_audit_enable: 'ocr',
  ocr_audit_save_frames: 'ocr',
  save_min_interval_sec: 'ocr',
  enable_visual_id: 'visual',
  visual_id_interval_sec: 'visual',
  visual_min_crop_area: 'visual',
  visual_match_threshold: 'visual',
  visual_margin_threshold: 'visual',
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
  track_reid_window_sec: 'track',
  track_reid_max_dist: 'track',
  sync_tolerance_ms: 'track',
  record_enable: 'record',
  record_max_duration_min: 'record',
  record_no_boat_gap_sec: 'record',
  record_fps: 'record',
  reid_embedding_model_path: 'reid',
  reid_visual_threshold: 'reid',
  reid_handoff_window_sec: 'reid',
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
  for (const prefix of ['anchor_', 'seam_', 'reid_', 'record_', 'track_', 'ocr_', 'bg_', 'fused_', 'visual_', 'redis_', 'qdrant_', 'training_snapshot_', 'enable_training_snapshot']) {
    if (key.startsWith(prefix)) return KEY_PREFIX_MAP[prefix.replace('_', '')] ?? 'other';
  }
  return 'other';
}

const KEY_VI_DESCRIPTION: Partial<Record<string, string>> = {
  port_name: 'Tên hiển thị của cảng.',
  detection_confidence_threshold: 'Ngưỡng OCR confidence để tự động chấp nhận (auto-accept).',
  invoice_tax_rate: 'Thuế mặc định cho hóa đơn (ví dụ 0.1 = 10%).',
  invoice_due_days: 'Số ngày đến hạn hóa đơn.',

  model_path: 'Đường dẫn file model YOLO.',
  device: 'Thiết bị suy luận: `0` (GPU) hoặc `cpu` (CPU).',
  conf: 'Ngưỡng confidence của YOLO detection.',
  resize_scale: 'Tỉ lệ resize frame trước khi xử lý.',
  clahe_clip_limit: 'Thông số CLAHE (giới hạn độ tương phản).',
  clahe_tile_size: 'Thông số CLAHE (kích thước tile).',

  enable_ocr: 'Bật/tắt OCR toàn cục.',
  ocr_interval_sec: 'Khoảng thời gian (giây) giữa các lần OCR.',
  ocr_label_ttl_sec: 'Thời gian hiển thị nhãn OCR trên UI (giây).',
  ocr_audit_enable: 'Bật/tắt audit logging cho OCR.',
  ocr_audit_save_frames: 'Lưu frame đầy đủ phục vụ OCR audit.',
  save_min_interval_sec: 'Khoảng thời gian tối thiểu giữa các lần lưu ảnh detection (giây).',

  enable_visual_id: 'Bật/tắt nhận diện tàu bằng đặc trưng sâu (manual enrollment + vector search).',
  visual_id_interval_sec: 'Khoảng thời gian (giây) giữa các lần visual-id trên track CONFIRMED.',
  visual_min_crop_area: 'Diện tích crop tối thiểu (pixel) để chạy trích đặc trưng.',
  visual_match_threshold: 'Ngưỡng điểm similarity để chấp nhận kết quả visual-id.',
  visual_margin_threshold: 'Chênh lệch tối thiểu top1-top2 để tránh match mơ hồ.',
  visual_top_k: 'Số ứng viên gần nhất trả về từ vector search.',
  visual_model_path: 'Đường dẫn model TorchScript ViT (để trống sẽ dùng backbone mặc định).',
  visual_backbone: 'Tên backbone cho extractor (ví dụ `vit_base_patch16_224`).',
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
  track_reid_window_sec: 'Cửa sổ thời gian (giây) để Re-ID.',
  track_reid_max_dist: 'Khoảng cách tối đa dùng cho Re-ID không gian.',
  sync_tolerance_ms:
    'Sai số tối đa giữa các camera trong cùng batch (ms). Tăng nếu RTSP chậm; giảm nếu cần khớp chặt hơn.',

  record_enable: 'Bật/tắt ghi video cho detections.',
  record_max_duration_min: 'Thời lượng ghi video tối đa (phút).',
  record_no_boat_gap_sec: 'Thời gian chờ sau khi tàu rời để dừng ghi (giây).',
  record_fps: 'FPS cho pipeline/ghi video.',

  reid_embedding_model_path: 'Đường dẫn model dùng để tạo embedding Re-ID.',
  reid_visual_threshold: 'Ngưỡng hiển thị/quality cho embedding Re-ID.',
  reid_handoff_window_sec: 'Cửa sổ handoff (giây) khi chuyển track/Re-ID.',

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
};

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
    </div>
  );
};

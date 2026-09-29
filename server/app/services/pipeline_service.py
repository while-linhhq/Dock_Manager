from __future__ import annotations
import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import datetime
import mimetypes

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.models.detection import Detection
from app.models.detection_media import DetectionMedia
from app.repositories import vessel_repo, detection_repo, order_repo, port_log_repo
from app.repositories.detection_media_repository import detection_media_repo
from app.repositories.port_config_repository import port_config_repo
from app.schemas import VesselCreate, DetectionCreate, PortLogCreate
from app.core.config import settings
from app.services.storage.minio_layout import final_image_key, final_video_key, staging_video_key
from app.services.storage.s3_service import (
    copy_object_same_bucket,
    parse_minio_uri,
    put_bytes,
    put_file,
    remove_object,
)
from app.utils.ai.rtsp_capture import configure_rtsp_decode, nvdec_status
from app.services.ship_id_utils import is_unknown_ship_id

from app.utils.ai.gpu_bootstrap import init_cuda_library_path
from app.services.ai.background_model import BackgroundModelConfig, BackgroundModelRegistry
from app.services.ai.boat_tracker import BoatTracker, TrackState
from app.services.ai.cross_camera_reid import CrossCameraReIdManager
from app.services.ai.handoff_matcher import OverlapMergeConfig
from app.services.ai.directional_handoff import DirectionalHandoffConfig
from app.services.ai.embedding_extractor import EmbeddingExtractor
from app.services.ai.frame_reader import FrameReaderThread
from app.services.ai.frame_stats import FrameStats
from app.services.ai.group_frame_hub import GroupFrameHub
from app.services.ai.ocr_worker import OcrWorkerThread
from app.services.ai.per_camera_pipeline import PerCameraPipeline, PerCameraPipelineConfig
from app.services.ai.ship_id_rule_engine import get_rule_engine
from app.services.ai.training_snapshot_collector import (
    TrainingSnapshotCollector,
    TrainingSnapshotConfig,
)
from app.services.ai.identity_fusion import IdentityFusion
from app.services.ai.ship_id_catalog import ShipIdCatalog
from app.services.ai.runtime_cache_redis import RuntimeCacheRedis
from app.services.ai.seam_anchor_verifier import SeamAnchorConfig, SeamAnchorVerifier
from app.services.ai.vector_store_qdrant import QdrantVectorStore
from app.services.ai.visual_embedding_factory import get_visual_embedding_extractor
from app.services.ai.visual_embedding_extractor import VisualEmbeddingExtractor
from app.services.ai.visual_id_worker import VisualIdWorkerThread
from app.utils.ai.ship_id_recognizer import create_ship_id_recognizer
from app.services.ai.track_media_collector import TrackMediaCollector
from app.services.ai.track_video_registry import RecordedVideo, TrackVideoRegistry
from app.services.ai.video_recorder import VideoRecorderThread
from app.utils.ai.gpu_probe import log_gpu_runtime_status
from app.utils.ai.yolo_detector import load_yolo_detector
from app.services.ai.yolo_worker import YoloWorkerThread
from app.services import pipeline_preview
from app.utils.ai.pipeline_utils import put_queue_drop_oldest
from app.utils.port_timing_config import resolve_positive_seconds

init_cuda_library_path('pre')


@dataclass(frozen=True)
class _MediaSampleJob:
  """Async best-shot sampling — keeps GroupFrameHub coordinator off JPEG encode."""

  frame: Any
  tracks: tuple[Any, ...]
  camera_id: int | None = None
  update_fused: bool = True

_log = logging.getLogger("app.services.pipeline")

# Resolve runtime temp paths regardless of process cwd (upload / VideoWriter must agree).
_SERVER_ROOT = Path(__file__).resolve().parents[2]

def _guess_content_type(p: Path) -> str:
    ct, _ = mimetypes.guess_type(str(p))
    return ct or 'application/octet-stream'


def _safe_key_segment(raw: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in raw)


def _make_minio_key(*segments: str) -> str:
    prefix = str(getattr(settings, 'MINIO_MEDIA_PREFIX', '') or '').strip().strip('/')
    core = '/'.join(_safe_key_segment(str(segment).strip()) for segment in segments if str(segment).strip())
    return f'{prefix}/{core}' if prefix else core


def _upload_file_to_minio(*, local_path: str, object_key: str) -> str:
    """
    Upload a local runtime file to MinIO and return minio:// URI.
    """
    p = Path(str(local_path)).resolve()
    if not p.exists():
        raise FileNotFoundError(str(p))
    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or '').strip() or 'media'
    put_file(
        local_path=str(p),
        bucket=bucket,
        object_key=object_key,
        content_type=_guess_content_type(p),
    )
    return f's3://{bucket}/{object_key}'


def _upload_bytes_to_minio(*, data: bytes, object_key: str, content_type: str) -> str:
    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or '').strip() or 'media'
    put_bytes(
        data=data,
        bucket=bucket,
        object_key=object_key,
        content_type=content_type,
    )
    return f's3://{bucket}/{object_key}'


class PipelineService:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._reader: FrameReaderThread | None = None
        self._group_frame_hub: GroupFrameHub | None = None
        self._yolo_worker: YoloWorkerThread | None = None
        self._ocr_worker: OcrWorkerThread | None = None
        self._ocr_recognizer: Any = None
        self._visual_worker: VisualIdWorkerThread | None = None
        self._video_worker: VideoRecorderThread | None = None
        self._single_video_worker: VideoRecorderThread | None = None
        self._per_camera_pipelines: list[PerCameraPipeline] = []
        self._reid_manager: CrossCameraReIdManager | None = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=5)
        self._result_queue: queue.Queue = queue.Queue(maxsize=10)
        self._ocr_queue: queue.Queue = queue.Queue(maxsize=10)
        self._visual_queue: queue.Queue = queue.Queue(maxsize=10)
        self._video_queue: queue.Queue = queue.Queue(maxsize=30)
        self._single_video_queue: queue.Queue = queue.Queue(maxsize=30)
        self.ocr_cache: dict[str, Any] = {}
        self.ocr_lock = threading.Lock()
        # Outside data-docker/ (Docker-owned root) — writable by dev user without sudo
        self._runtime_media_base = _SERVER_ROOT / 'app' / 'runtime-media'
        self._media_collector = TrackMediaCollector()
        self._video_registry = TrackVideoRegistry()
        self._latest_fused_lock = threading.Lock()
        self._latest_fused_bgr: Any = None
        self._frame_stats = FrameStats()
        self._active_detect_scale: float = float(settings.DETECT_SCALE)
        self._media_sample_queue: queue.Queue[_MediaSampleJob | None] = queue.Queue(maxsize=5)
        self._media_sample_thread: threading.Thread | None = None
        self._primary_record_camera_id: int | None = None
        self._detector: Any = None
        self._detector_lock = threading.Lock()
        self._detector_signature: tuple[str, str, float] | None = None
        self._boat_tracker: BoatTracker = BoatTracker()
        self._bg_registry: BackgroundModelRegistry | None = None
        self._seam_anchor_verifier: SeamAnchorVerifier | None = None
        self._active_group_id: int | None = None
        self._db: Session | None = None
        self._gpu_status: dict[str, Any] | None = None
        self._runtime_cache: RuntimeCacheRedis | None = None
        self._vector_store: QdrantVectorStore | None = None
        self._identity_fusion: IdentityFusion | None = None
        self._visual_extractor: VisualEmbeddingExtractor | None = None
        self._ship_id_catalog = ShipIdCatalog(
            enabled=bool(getattr(settings, 'SHIP_ID_REQUIRE_CATALOG', False)),
        )

    @staticmethod
    def _configure_dashboard_preview(runtime_cfg: dict[str, Any]) -> None:
        pipeline_preview.set_target_fps(float(runtime_cfg['record_fps']))
        # Preserve group-camera fused canvas detail. The dashboard renderer already
        # fits the image to the visible panel, so server-side downscale should not
        # make wide group previews smaller than the configured fused width.
        preview_max_width = max(
            int(getattr(settings, 'PREVIEW_MAX_WIDTH', 1280)),
            int(runtime_cfg.get('fused_frame_max_width', 0) or 0),
        )
        pipeline_preview.set_max_width(preview_max_width)

    def _init_visual_stack(self, runtime_cfg: dict[str, Any]) -> None:
        self._runtime_cache = RuntimeCacheRedis(
            url=runtime_cfg['redis_url'],
            key_prefix=runtime_cfg['redis_key_prefix'],
            default_ttl_sec=runtime_cfg['redis_visual_ttl_sec'],
        )
        self._vector_store = QdrantVectorStore(
            host=runtime_cfg['qdrant_host'],
            port=runtime_cfg['qdrant_port'],
            api_key=runtime_cfg['qdrant_api_key'] or None,
            collection_name=runtime_cfg['qdrant_collection'],
            vector_size=runtime_cfg['qdrant_vector_size'],
            distance=runtime_cfg['qdrant_distance'],
        )
        self._ship_id_catalog.set_vector_store(self._vector_store)
        self._ship_id_catalog.set_enabled(bool(runtime_cfg['ship_id_require_catalog']))
        self._identity_fusion = IdentityFusion(
            match_threshold=runtime_cfg['visual_match_threshold'],
            no_ocr_match_threshold=runtime_cfg['visual_no_ocr_match_threshold'],
            conflict_threshold=runtime_cfg['visual_conflict_threshold'],
            catalog_is_known=self._ship_id_catalog.is_known,
        )
        self._visual_extractor = get_visual_embedding_extractor()

    def _reset_runtime_queues(self) -> None:
        self._frame_queue = queue.Queue(maxsize=5)
        self._result_queue = queue.Queue(maxsize=10)
        self._ocr_queue = queue.Queue(maxsize=10)
        self._visual_queue = queue.Queue(maxsize=10)
        self._video_queue = queue.Queue(maxsize=30)
        self._single_video_queue = queue.Queue(maxsize=30)
        self._media_sample_queue = queue.Queue(maxsize=5)
        self._video_registry.clear()

    @staticmethod
    def _to_bool(raw: str, default: bool) -> bool:
        value = (raw or '').strip().lower()
        if value in ('1', 'true', 'yes', 'y', 'on'):
            return True
        if value in ('0', 'false', 'no', 'n', 'off'):
            return False
        return default

    @staticmethod
    def _to_int(raw: str, default: int) -> int:
        try:
            return int(str(raw).strip())
        except Exception:
            return default

    @staticmethod
    def _to_float(raw: str, default: float) -> float:
        try:
            return float(str(raw).strip())
        except Exception:
            return default

    @staticmethod
    def _optional_positive_float(cfg_map: dict[str, str], key: str, default: float | None) -> float | None:
        raw = cfg_map.get(key)
        if raw is None or str(raw).strip() == '':
            return default
        try:
            value = float(str(raw).strip())
        except Exception:
            return default
        return value if value > 0 else default

    @staticmethod
    def _tracker_kwargs(runtime_cfg: dict[str, Any], *, on_track_removed) -> dict[str, Any]:
        return {
            'min_hits': 1,
            'max_tentative_misses': 1,
            'max_lost_frames': 1,
            'iou_threshold': runtime_cfg['track_iou_threshold'],
            'reid_window_sec': runtime_cfg['track_reid_window_sec'],
            'reid_max_centroid_dist': runtime_cfg['track_reid_max_dist'],
            'on_track_removed': on_track_removed,
            'min_confirm_sec': runtime_cfg['track_min_confirm_sec'],
            'max_tentative_sec': runtime_cfg['track_max_tentative_sec'],
            'max_lost_sec': runtime_cfg['track_max_lost_sec'],
            'visual_match_threshold': runtime_cfg['visual_match_threshold'],
            'visual_no_ocr_match_threshold': runtime_cfg['visual_no_ocr_match_threshold'],
            'visual_conflict_threshold': runtime_cfg['visual_conflict_threshold'],
        }

    def _load_runtime_config(self) -> dict[str, Any]:
        db = SessionLocal()
        try:
            cfg_rows = port_config_repo.get_all(db)
            cfg_map = {row.key: row.value for row in cfg_rows}
        except Exception:
            _log.exception('Failed to load port_configs, fallback to env settings')
            cfg_map = {}
        finally:
            db.close()

        def _s(key: str, default: str) -> str:
            value = cfg_map.get(key)
            return str(value).strip() if value is not None else default

        record_fps = (
            float(rf)
            if (rf := self._to_float(cfg_map.get('record_fps', ''), float(settings.RECORD_FPS))) > 0
            else float(settings.RECORD_FPS)
        )

        return {
            'model_path': _s('model_path', settings.MODEL_PATH),
            'device': _s('device', settings.DEVICE),
            'conf': self._to_float(cfg_map.get('conf', ''), float(settings.CONF)),
            'yolo_imgsz': max(
                32,
                self._to_int(cfg_map.get('yolo_imgsz', ''), int(settings.YOLO_IMGSZ)),
            ),
            'enable_ocr': self._to_bool(cfg_map.get('enable_ocr', ''), bool(settings.ENABLE_OCR)),
            'ship_id_require_catalog': self._to_bool(
                cfg_map.get('ship_id_require_catalog', ''),
                bool(getattr(settings, 'SHIP_ID_REQUIRE_CATALOG', False)),
            ),
            'ocr_label_ttl_sec': self._to_float(
                cfg_map.get('ocr_label_ttl_sec', ''),
                float(settings.OCR_LABEL_TTL_SEC),
            ),
            'ocr_audit_enable': self._to_bool(
                cfg_map.get('ocr_audit_enable', ''),
                bool(settings.OCR_AUDIT_ENABLE),
            ),
            'track_iou_threshold': self._to_float(
                cfg_map.get('track_iou_threshold', ''),
                float(settings.TRACK_IOU_THRESHOLD),
            ),
            'track_dedup_iomin_threshold': self._to_float(
                cfg_map.get('track_dedup_iomin_threshold', ''),
                float(settings.TRACK_DEDUP_IOMIN_THRESHOLD),
            ),
            'berth_out_grace_sec': self._to_float(
                cfg_map.get('berth_out_grace_sec', ''),
                float(settings.BERTH_OUT_GRACE_SEC),
            ),
            'track_reid_window_sec': self._to_float(
                cfg_map.get('track_reid_window_sec', ''),
                float(settings.TRACK_REID_WINDOW_SEC),
            ),
            'track_reid_max_dist': self._to_float(
                cfg_map.get('track_reid_max_dist', ''),
                float(settings.TRACK_REID_MAX_DIST),
            ),
            'resize_scale': self._to_float(cfg_map.get('resize_scale', ''), float(settings.RESIZE_SCALE)),
            'save_min_interval_sec': self._to_float(
                cfg_map.get('save_min_interval_sec', ''),
                float(settings.SAVE_MIN_INTERVAL_SEC),
            ),
            'ocr_audit_save_frames': self._to_bool(
                cfg_map.get('ocr_audit_save_frames', ''),
                bool(settings.OCR_AUDIT_SAVE_FRAMES),
            ),
            'record_enable': self._to_bool(cfg_map.get('record_enable', ''), bool(settings.RECORD_ENABLE)),
            'record_max_duration_min': max(
                1,
                self._to_int(cfg_map.get('record_max_duration_min', ''), int(settings.RECORD_MAX_DURATION_MIN)),
            ),
            'record_no_boat_gap_sec': max(
                1,
                self._to_int(cfg_map.get('record_no_boat_gap_sec', ''), int(settings.RECORD_NO_BOAT_GAP_SEC)),
            ),
            'record_fps': record_fps,
            'sync_tolerance_ms': max(
                0,
                self._to_int(cfg_map.get('sync_tolerance_ms', ''), 1200),
            ),
            'sync_camera_offsets_ms': cfg_map.get('sync_camera_offsets_ms', '') or '',
            'reid_embedding_model_path': _s(
                'reid_embedding_model_path',
                settings.REID_EMBEDDING_MODEL_PATH,
            ),
            'reid_visual_threshold': self._to_float(
                cfg_map.get('reid_visual_threshold', ''),
                float(settings.REID_VISUAL_THRESHOLD),
            ),
            'reid_handoff_window_sec': self._to_float(
                cfg_map.get('reid_handoff_window_sec', ''),
                float(settings.REID_HANDOFF_WINDOW_SEC),
            ),
            'primary_zone_ratio': self._to_float(
                cfg_map.get('primary_zone_ratio', ''),
                float(settings.PRIMARY_ZONE_RATIO),
            ),
            'edge_zone_ratio': self._to_float(
                cfg_map.get('edge_zone_ratio', ''),
                float(settings.EDGE_ZONE_RATIO),
            ),
            'reid_overlap_merge_enabled': self._to_bool(
                cfg_map.get('reid_overlap_merge_enabled', ''),
                bool(settings.REID_OVERLAP_MERGE_ENABLED),
            ),
            'reid_edge_zone_ratio': self._to_float(
                cfg_map.get('reid_edge_zone_ratio', ''),
                float(settings.REID_EDGE_ZONE_RATIO),
            ),
            'reid_embedding_weight': self._to_float(
                cfg_map.get('reid_embedding_weight', ''),
                float(settings.REID_EMBEDDING_WEIGHT),
            ),
            'reid_color_weight': self._to_float(
                cfg_map.get('reid_color_weight', ''),
                float(settings.REID_COLOR_WEIGHT),
            ),
            'reid_size_weight': self._to_float(
                cfg_map.get('reid_size_weight', ''),
                float(settings.REID_SIZE_WEIGHT),
            ),
            'reid_accept_threshold': self._to_float(
                cfg_map.get('reid_accept_threshold', ''),
                float(settings.REID_ACCEPT_THRESHOLD),
            ),
            'reid_min_margin': self._to_float(
                cfg_map.get('reid_min_margin', ''),
                float(settings.REID_MIN_MARGIN),
            ),
            'reid_directional_handoff_enabled': self._to_bool(
                cfg_map.get('reid_directional_handoff_enabled', ''),
                bool(settings.REID_DIRECTIONAL_HANDOFF_ENABLED),
            ),
            'reid_directional_max_transit_sec': self._to_float(
                cfg_map.get('reid_directional_max_transit_sec', ''),
                float(settings.REID_DIRECTIONAL_MAX_TRANSIT_SEC),
            ),
            'reid_directional_min_transit_sec': self._to_float(
                cfg_map.get('reid_directional_min_transit_sec', ''),
                float(settings.REID_DIRECTIONAL_MIN_TRANSIT_SEC),
            ),
            'reid_directional_min_velocity_px': self._to_float(
                cfg_map.get('reid_directional_min_velocity_px', ''),
                float(settings.REID_DIRECTIONAL_MIN_VELOCITY_PX),
            ),
            'reid_directional_edge_zone_ratio': self._to_float(
                cfg_map.get('reid_directional_edge_zone_ratio', ''),
                float(settings.REID_DIRECTIONAL_EDGE_ZONE_RATIO),
            ),
            'reid_directional_embedding_weight': self._to_float(
                cfg_map.get('reid_directional_embedding_weight', ''),
                float(settings.REID_DIRECTIONAL_EMBEDDING_WEIGHT),
            ),
            'reid_directional_direction_weight': self._to_float(
                cfg_map.get('reid_directional_direction_weight', ''),
                float(settings.REID_DIRECTIONAL_DIRECTION_WEIGHT),
            ),
            'reid_directional_time_weight': self._to_float(
                cfg_map.get('reid_directional_time_weight', ''),
                float(settings.REID_DIRECTIONAL_TIME_WEIGHT),
            ),
            'reid_directional_accept_threshold': self._to_float(
                cfg_map.get('reid_directional_accept_threshold', ''),
                float(settings.REID_DIRECTIONAL_ACCEPT_THRESHOLD),
            ),
            'reid_directional_embedding_floor': self._to_float(
                cfg_map.get('reid_directional_embedding_floor', ''),
                float(settings.REID_DIRECTIONAL_EMBEDDING_FLOOR),
            ),
            'reid_reverse_motion_guard_enabled': self._to_bool(
                cfg_map.get('reid_reverse_motion_guard_enabled', ''),
                bool(settings.REID_REVERSE_MOTION_GUARD_ENABLED),
            ),
            'reid_embedding_diversity_max_cos': self._to_float(
                cfg_map.get('reid_embedding_diversity_max_cos', ''),
                float(settings.REID_EMBEDDING_DIVERSITY_MAX_COS),
            ),
            'clahe_clip_limit': self._to_float(
                cfg_map.get('clahe_clip_limit', ''),
                float(settings.CLAHE_CLIP_LIMIT),
            ),
            'clahe_tile_size': max(
                2,
                self._to_int(cfg_map.get('clahe_tile_size', ''), int(settings.CLAHE_TILE_SIZE)),
            ),
            'clahe_enable_gray_world': self._to_bool(
                cfg_map.get('clahe_enable_gray_world', ''),
                bool(settings.CLAHE_ENABLE_GRAY_WORLD),
            ),
            'clahe_fast': self._to_bool(
                cfg_map.get('clahe_fast', ''),
                bool(settings.CLAHE_FAST),
            ),
            'detect_scale': max(
                0.1,
                min(
                    1.0,
                    self._to_float(
                        cfg_map.get('detect_scale', ''),
                        float(settings.DETECT_SCALE),
                    ),
                ),
            ),
            'crop_pad_ratio': max(
                0.0,
                min(
                    0.5,
                    self._to_float(
                        cfg_map.get('crop_pad_ratio', ''),
                        float(settings.CROP_PAD_RATIO),
                    ),
                ),
            ),
            'fused_frame_max_width': max(
                320,
                self._to_int(
                    cfg_map.get('fused_frame_max_width', ''),
                    int(settings.FUSED_FRAME_MAX_WIDTH),
                ),
            ),
            'fused_frame_max_height': max(
                180,
                self._to_int(
                    cfg_map.get('fused_frame_max_height', ''),
                    int(settings.FUSED_FRAME_MAX_HEIGHT),
                ),
            ),
            'seam_anchor_enabled': self._to_bool(
                cfg_map.get('seam_anchor_enabled', ''),
                bool(settings.SEAM_ANCHOR_ENABLED),
            ),
            'seam_roi_width_ratio': self._to_float(
                cfg_map.get('seam_roi_width_ratio', ''),
                float(settings.SEAM_ROI_WIDTH_RATIO),
            ),
            'seam_proximity_px': max(
                1,
                self._to_int(cfg_map.get('seam_proximity_px', ''), int(settings.SEAM_PROXIMITY_PX)),
            ),
            'bg_subtract_threshold': self._to_float(
                cfg_map.get('bg_subtract_threshold', ''),
                float(settings.BG_SUBTRACT_THRESHOLD),
            ),
            'bg_model_history': max(
                10,
                self._to_int(cfg_map.get('bg_model_history', ''), int(settings.BG_MODEL_HISTORY)),
            ),
            'bg_var_threshold': self._to_float(
                cfg_map.get('bg_var_threshold', ''),
                float(settings.BG_VAR_THRESHOLD),
            ),
            'bg_min_seed_frames': max(
                1,
                self._to_int(cfg_map.get('bg_min_seed_frames', ''), int(settings.BG_MIN_SEED_FRAMES)),
            ),
            'anchor_iou_resurrect_threshold': self._to_float(
                cfg_map.get('anchor_iou_resurrect_threshold', ''),
                float(settings.ANCHOR_IOU_RESURRECT_THRESHOLD),
            ),
            'anchor_embedding_match_enabled': self._to_bool(
                cfg_map.get('anchor_embedding_match_enabled', ''),
                bool(settings.ANCHOR_EMBEDDING_MATCH_ENABLED),
            ),
            'anchor_embedding_sim_threshold': self._to_float(
                cfg_map.get('anchor_embedding_sim_threshold', ''),
                float(settings.ANCHOR_EMBEDDING_SIM_THRESHOLD),
            ),
            'anchor_revalidation_sec': self._to_float(
                cfg_map.get('anchor_revalidation_sec', ''),
                float(settings.ANCHOR_REVALIDATION_SEC),
            ),
            'anchor_departed_grace_sec': self._to_float(
                cfg_map.get('anchor_departed_grace_sec', ''),
                float(settings.ANCHOR_DEPARTED_GRACE_SEC),
            ),
            'anchor_max_duration_sec': self._to_float(
                cfg_map.get('anchor_max_duration_sec', ''),
                float(settings.ANCHOR_MAX_DURATION_SEC),
            ),
            'anchor_db_update_debounce_sec': self._to_float(
                cfg_map.get('anchor_db_update_debounce_sec', ''),
                float(settings.ANCHOR_DB_UPDATE_DEBOUNCE_SEC),
            ),
            'anchor_min_stationary_sec': self._to_float(
                cfg_map.get('anchor_min_stationary_sec', ''),
                float(settings.ANCHOR_MIN_STATIONARY_SEC),
            ),
            'anchor_color_hsv_tolerance_h': self._to_int(
                cfg_map.get('anchor_color_hsv_tolerance_h', ''),
                int(settings.ANCHOR_COLOR_HSV_TOLERANCE_H),
            ),
            'ocr_interval_sec': resolve_positive_seconds(
                cfg_map,
                sec_key='ocr_interval_sec',
                legacy_frame_key='ocr_interval_frames',
                default_sec=float(settings.OCR_INTERVAL_SEC),
                fps=record_fps,
            ),
            'enable_visual_id': self._to_bool(
                cfg_map.get('enable_visual_id', ''),
                bool(settings.ENABLE_VISUAL_ID),
            ),
            'visual_id_interval_sec': resolve_positive_seconds(
                cfg_map,
                sec_key='visual_id_interval_sec',
                legacy_frame_key='visual_id_interval_frames',
                default_sec=float(settings.VISUAL_ID_INTERVAL_SEC),
                fps=record_fps,
            ),
            'ship_id_lock_stable_sec': max(
                0.0,
                self._to_float(
                    cfg_map.get('ship_id_lock_stable_sec', ''),
                    float(settings.SHIP_ID_LOCK_STABLE_SEC),
                ),
            ),
            'visual_min_crop_area': max(
                256,
                self._to_int(cfg_map.get('visual_min_crop_area', ''), int(settings.VISUAL_MIN_CROP_AREA)),
            ),
            'visual_match_threshold': self._to_float(
                cfg_map.get('visual_match_threshold', ''),
                float(settings.VISUAL_MATCH_THRESHOLD),
            ),
            'visual_no_ocr_match_threshold': self._to_float(
                cfg_map.get('visual_no_ocr_match_threshold', ''),
                float(settings.VISUAL_NO_OCR_MATCH_THRESHOLD),
            ),
            'visual_conflict_threshold': self._to_float(
                cfg_map.get('visual_conflict_threshold', ''),
                0.96,
            ),
            'detection_confidence_threshold': self._to_float(
                cfg_map.get('detection_confidence_threshold', ''),
                0.0,
            ),
            'ocr_confidence_threshold': self._to_float(
                cfg_map.get('ocr_confidence_threshold', ''),
                float(settings.OCR_CONFIDENCE_THRESHOLD),
            ),
            'visual_top_k': max(
                1,
                self._to_int(cfg_map.get('visual_top_k', ''), int(settings.VISUAL_TOP_K)),
            ),
            'visual_model_path': _s('visual_model_path', settings.VISUAL_MODEL_PATH),
            'visual_backbone': _s('visual_backbone', settings.VISUAL_BACKBONE),
            'visual_embedding_dim': max(
                64,
                self._to_int(cfg_map.get('visual_embedding_dim', ''), int(settings.VISUAL_EMBEDDING_DIM)),
            ),
            'visual_batch_size': max(
                1,
                self._to_int(cfg_map.get('visual_batch_size', ''), int(settings.VISUAL_BATCH_SIZE)),
            ),
            'visual_device': _s('visual_device', settings.VISUAL_DEVICE),
            'redis_url': _s('redis_url', settings.REDIS_URL),
            'redis_key_prefix': _s('redis_key_prefix', settings.REDIS_KEY_PREFIX),
            'redis_visual_ttl_sec': max(
                10,
                self._to_int(cfg_map.get('redis_visual_ttl_sec', ''), int(settings.REDIS_VISUAL_TTL_SEC)),
            ),
            'qdrant_host': _s('qdrant_host', settings.QDRANT_HOST),
            'qdrant_port': max(
                1,
                self._to_int(cfg_map.get('qdrant_port', ''), int(settings.QDRANT_PORT)),
            ),
            'qdrant_api_key': _s('qdrant_api_key', settings.QDRANT_API_KEY),
            'qdrant_collection': _s('qdrant_collection', settings.QDRANT_COLLECTION),
            'qdrant_vector_size': max(
                1,
                self._to_int(cfg_map.get('qdrant_vector_size', ''), int(settings.QDRANT_VECTOR_SIZE)),
            ),
            'qdrant_distance': _s('qdrant_distance', settings.QDRANT_DISTANCE),
            'enable_training_snapshot': self._to_bool(
                cfg_map.get('enable_training_snapshot', ''),
                bool(settings.ENABLE_TRAINING_SNAPSHOT),
            ),
            'training_snapshot_interval_sec': resolve_positive_seconds(
                cfg_map,
                sec_key='training_snapshot_interval_sec',
                legacy_frame_key='training_snapshot_interval_frames',
                default_sec=float(settings.TRAINING_SNAPSHOT_INTERVAL_SEC),
                fps=record_fps,
            ),
            'training_snapshot_base_dir': _s(
                'training_snapshot_base_dir',
                settings.TRAINING_SNAPSHOT_BASE_DIR,
            ),
            'training_snapshot_jpeg_quality': max(
                50,
                min(
                    100,
                    self._to_int(
                        cfg_map.get('training_snapshot_jpeg_quality', ''),
                        int(settings.TRAINING_SNAPSHOT_JPEG_QUALITY),
                    ),
                ),
            ),
            'track_min_confirm_sec': resolve_positive_seconds(
                cfg_map,
                sec_key='track_min_confirm_sec',
                legacy_frame_key='track_min_hits',
                default_sec=float(settings.TRACK_MIN_CONFIRM_SEC),
                fps=record_fps,
            ),
            'track_max_tentative_sec': resolve_positive_seconds(
                cfg_map,
                sec_key='track_max_tentative_sec',
                legacy_frame_key='track_max_tentative_misses',
                default_sec=float(settings.TRACK_MAX_TENTATIVE_SEC),
                fps=record_fps,
            ),
            'track_max_lost_sec': resolve_positive_seconds(
                cfg_map,
                sec_key='track_max_lost_sec',
                legacy_frame_key='track_max_lost_frames',
                default_sec=float(settings.TRACK_MAX_LOST_SEC),
                fps=record_fps,
            ),
            'rtsp_nvdec_enabled': self._to_bool(
                cfg_map.get('rtsp_nvdec_enabled', ''),
                bool(settings.RTSP_NVDEC_ENABLED),
            ),
            'ffmpeg_path': _s('ffmpeg_path', settings.FFMPEG_PATH),
            'rtsp_transport': _s('rtsp_transport', settings.RTSP_TRANSPORT) or 'tcp',
        }

    @staticmethod
    def _apply_rtsp_decode_config(runtime_cfg: dict[str, Any]) -> None:
        configure_rtsp_decode(
            use_nvdec=bool(runtime_cfg.get('rtsp_nvdec_enabled')),
            ffmpeg_path=str(runtime_cfg.get('ffmpeg_path') or ''),
            rtsp_transport=str(runtime_cfg.get('rtsp_transport') or 'tcp'),
            hwaccel=str(settings.RTSP_NVDEC_HWACCEL or 'cuda'),
            output_scale=1.0,
        )
        _log.info('RTSP decode: %s', nvdec_status())

    @staticmethod
    def _warmup_gst_probe_cache(enabled_members: list[Any]) -> None:
        """Pre-populate GStreamer codec probe cache before launching per-camera pipelines.
        Probes one camera per unique host so all subsequent camera opens are instant."""
        try:
            from app.utils.ai.rtsp_capture import GStreamerNvdecCapture

            if not getattr(settings, 'RTSP_GST_NVDEC_ENABLED', False):
                return
            if not GStreamerNvdecCapture.available():
                return

            import urllib.parse
            seen_hosts: set[str] = set()
            for member in enabled_members:
                camera = getattr(member, 'camera', None)
                if camera is None:
                    continue
                url = getattr(camera, 'rtsp_url', '') or ''
                if not url:
                    continue
                host = urllib.parse.urlparse(url).hostname or ''
                if not host or host in seen_hosts:
                    continue
                seen_hosts.add(host)
                # Probe one URL per host — result caches for all other cameras on same host.
                _log.debug('GStreamer warmup probe for host %s (%s)', host, url[:30])
                GStreamerNvdecCapture._probe_codec_via_rtspsrc(url, None, None, 'tcp')
        except Exception as exc:
            _log.warning('GStreamer warmup probe error: %s', exc)

    @property
    def is_running(self) -> bool:
        single_running = self._reader is not None and self._reader.is_alive()
        hybrid_running = any(pipeline.is_alive() for pipeline in self._per_camera_pipelines)
        hub_running = self._group_frame_hub is not None and self._group_frame_hub.is_alive()
        return single_running or hub_running or hybrid_running

    @property
    def active_group_id(self) -> int | None:
        return self._active_group_id

    @property
    def seam_anchor_verifier(self) -> SeamAnchorVerifier | None:
        return self._seam_anchor_verifier

    @property
    def bg_registry(self) -> BackgroundModelRegistry | None:
        return self._bg_registry

    def get_synchronized_frames(
        self,
        camera_ids: list[int],
        *,
        timeout_sec: float = 2.0,
    ) -> dict[int, Any] | None:
        """Return one aligned BGR frame per camera (same time window)."""
        if self._group_frame_hub is None:
            return None
        ids = [int(camera_id) for camera_id in camera_ids]
        if not ids:
            return None
        try:
            from app.utils.ai.frame_quality import is_usable_bgr_frame

            batch = self._group_frame_hub.get_last_aligned_batch(ids, copy_frames=True)
            if batch is None:
                batch = self._group_frame_hub.wait_aligned_batch(
                    ids,
                    timeout_sec=timeout_sec,
                )
            if batch is None:
                return None
            frames: dict[int, Any] = {}
            for camera_id, timed in batch.items():
                frame = timed.frame
                if frame is not None and is_usable_bgr_frame(frame):
                    frames[int(camera_id)] = frame
            if len(frames) != len(ids):
                return None
            return frames
        except Exception:
            _log.exception('get_synchronized_frames failed')
            return None

    def get_latest_camera_frame(self, camera_id: int):
        frames = self.get_synchronized_frames([int(camera_id)], timeout_sec=0.8)
        if frames is not None:
            return frames.get(int(camera_id))
        if self._group_frame_hub is None:
            return None
        try:
            from app.utils.ai.frame_quality import is_usable_bgr_frame

            snapshot = self._group_frame_hub.frame_buffer.snapshot(copy_frames=True)
        except Exception:
            _log.exception('get_latest_camera_frame: snapshot failed')
            return None
        timed = snapshot.get(int(camera_id))
        if timed is None:
            return None
        frame = timed.frame
        if frame is not None and is_usable_bgr_frame(frame):
            return frame
        return None

    @staticmethod
    def _utc_staging_day() -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime('%d-%m-%Y')

    def _lookup_track_ids(self, track_id: str) -> list[str]:
        if self._reid_manager is not None:
            return self._reid_manager.resolve_lookup_track_ids(str(track_id))
        return [str(track_id)]

    def _start_media_sample_worker(self) -> None:
        if self._media_sample_thread is not None and self._media_sample_thread.is_alive():
            return
        self._media_sample_thread = threading.Thread(
            target=self._media_sample_loop,
            daemon=True,
            name='MediaSampleWorker',
        )
        self._media_sample_thread.start()

    def _stop_media_sample_worker(self) -> None:
        try:
            self._media_sample_queue.put_nowait(None)
        except queue.Full:
            pass
        if self._media_sample_thread is not None:
            self._media_sample_thread.join(timeout=3.0)
        self._media_sample_thread = None

    def _media_sample_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._media_sample_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if job is None:
                self._media_sample_queue.task_done()
                break
            try:
                self._apply_media_sample(job)
            except Exception:
                _log.exception('Media sample worker failed')
            finally:
                self._media_sample_queue.task_done()

    def _apply_media_sample(self, job: _MediaSampleJob) -> None:
        frame = job.frame
        if frame is None or getattr(frame, 'size', 0) == 0:
            return
        ts = time.time()
        for t in job.tracks:
            if getattr(t, 'state', None) != TrackState.CONFIRMED:
                continue
            tid = str(t.track_id)
            if job.update_fused:
                self._media_collector.update_latest_fused(tid, frame, ts)
                continue
            cam = int(
                job.camera_id
                if job.camera_id is not None
                else getattr(t, 'camera_id', None) or 0
            )
            if cam > 0:
                self._media_collector.update_latest_single(tid, cam, frame, ts)

    def frame_stats_payload(self) -> dict[str, Any]:
        """Số frame đã xử lý + fps theo camera (khoá chuỗi để JSON hoá được)."""
        stats = getattr(self, '_frame_stats', None)
        if stats is None:
            return {'frames_processed': {}, 'fps_per_camera': {}}
        return {
            'frames_processed': {str(key): int(value) for key, value in stats.totals().items()},
            'fps_per_camera': {
                str(key): round(float(value), 2) for key, value in stats.snapshot().items()
            },
            'process_ms_per_frame': {
                str(key): round(float(value), 1) for key, value in stats.ms_snapshot().items()
            },
        }

    def _enqueue_media_sample(
        self,
        frame: Any,
        tracks: list[Any],
        *,
        camera_id: int | None = None,
        update_fused: bool = True,
        mirror_latest_fused: bool = False,
    ) -> None:
        if frame is None or getattr(frame, 'size', 0) == 0:
            return
        if mirror_latest_fused:
            with self._latest_fused_lock:
                self._latest_fused_bgr = frame.copy()
        confirmed = tuple(t for t in tracks if getattr(t, 'state', None) == TrackState.CONFIRMED)
        if not confirmed:
            return
        job = _MediaSampleJob(
            frame=frame.copy(),
            tracks=confirmed,
            camera_id=camera_id,
            update_fused=update_fused,
        )
        put_queue_drop_oldest(self._media_sample_queue, job)

    def _recording_fused_media_sample(self, fused: Any, tracks: list[Any]) -> None:
        self._enqueue_media_sample(
            fused,
            tracks,
            update_fused=True,
            mirror_latest_fused=True,
        )

    def _recording_single_media_sample(
        self,
        camera_id: int,
        overlay: Any,
        tracks: list[Any],
    ) -> None:
        self._enqueue_media_sample(
            overlay,
            tracks,
            camera_id=int(camera_id),
            update_fused=False,
        )

    def _recording_yolo_single_overlay(self, overlay: Any, tracks: list[Any]) -> None:
        self._enqueue_media_sample(
            overlay,
            tracks,
            update_fused=True,
            mirror_latest_fused=True,
        )

    def _on_ocr_track_media(
        self,
        track_id: str,
        frame: Any,
        ocr_conf: float,
        ship_id: str,
        camera_id: int | None,
    ) -> None:
        # Comparison images are now captured at berth IN/OUT crossings
        # (see _recording_boundary_media_sample), not on OCR best-shot.
        # Retained as a no-op so the OCR worker callback contract is unchanged.
        return

    def _recording_boundary_media_sample(
        self,
        camera_id: int,
        overlay: Any,
        tracks: list[Any],
        crossings: list[tuple[str, str]],
    ) -> None:
        """Capture single + fused overlay at each berth IN/OUT crossing.

        `overlay` is the single-camera overlay frame for this camera at the
        crossing instant; the fused counterpart is the latest fused overlay
        mirrored into _latest_fused_bgr (same instant, within one frame).
        """
        if overlay is None or getattr(overlay, 'size', 0) == 0:
            return
        confirmed_ids = {
            str(t.track_id)
            for t in tracks
            if getattr(t, 'state', None) == TrackState.CONFIRMED
        }
        # Always refresh latest-frame fallback for confirmed tracks on this camera.
        ts = time.time()
        fused = None
        with self._latest_fused_lock:
            if self._latest_fused_bgr is not None:
                fused = self._latest_fused_bgr.copy()
        for tid in confirmed_ids:
            self._media_collector.update_latest_single(tid, int(camera_id), overlay, ts)
            if fused is not None:
                self._media_collector.update_latest_fused(tid, fused, ts)
        if not crossings:
            return
        single_copy = overlay.copy()
        for track_id, direction in crossings:
            if str(track_id) not in confirmed_ids:
                continue
            self._media_collector.set_boundary_overlay(
                str(track_id),
                direction,
                int(camera_id),
                single_copy,
                fused,
            )

    def _promote_staging_video(
        self,
        src_uri: str,
        day_key: str,
        detection_id: int,
        dest_fname: str | None = None,
    ) -> str:
        """
        Copy staging object → detections/{day}/{id}/videos/{dest_fname} then remove staging.
        dest_fname lets callers inject track_id into the final filename.
        On failure returns src_uri (staging kept for retry/debug).
        """
        ref = parse_minio_uri(src_uri)
        if ref is None:
            return src_uri
        fname = dest_fname or ref.object_key.rsplit('/', 1)[-1]
        dest_key = final_video_key(day_key, int(detection_id), fname)
        if ref.object_key == dest_key:
            return src_uri
        if 'detections/staging/' not in ref.object_key:
            try:
                copy_object_same_bucket(
                    bucket=ref.bucket,
                    src_key=ref.object_key,
                    dest_key=dest_key,
                )
                _log.info('Copied finalized video → %s', dest_key)
                return f's3://{ref.bucket}/{dest_key}'
            except Exception:
                _log.exception('Failed to copy finalized video to detection layout')
                return src_uri
        try:
            copy_object_same_bucket(
                bucket=ref.bucket,
                src_key=ref.object_key,
                dest_key=dest_key,
            )
            remove_object(bucket=ref.bucket, object_key=ref.object_key)
            _log.info(
                'MinIO promoted video s3://%s/%s (staging removed)',
                ref.bucket,
                dest_key,
            )
            return f's3://{ref.bucket}/{dest_key}'
        except RuntimeError as exc:
            if 'Cloudflare 524' in str(exc):
                _log.warning(
                    'Keeping staging video because MinIO server-side copy is denied: %s',
                    ref.object_key,
                )
            else:
                _log.exception('Failed to promote staging video to detection layout')
            return src_uri
        except Exception:
            _log.exception('Failed to promote staging video to detection layout')
            return src_uri

    def _upload_captured_image(
        self,
        track_id: str | None,
        media_type: str,
        image_bgr,
        filename: str,
        remember_for_detection: bool,
    ) -> None:
        """
        Legacy OCR capture hook. Final images use TrackMediaCollector →
        detections/{DD-MM-YYYY}/{detection_id}/images/ on persist (no staging OCR tree).
        """
        _ = (track_id, media_type, image_bgr, filename, remember_for_detection)
        return

    def _upload_recorded_video(
        self,
        local_path: str,
        track_ids: frozenset[str] = frozenset(),
        started_at: float = 0.0,
        ended_at: float = 0.0,
    ) -> None:
        path = Path(local_path)
        if not path.exists():
            return

        day = self._utc_staging_day()
        fname = path.name
        if not fname.startswith('fused_'):
            fname = f'fused_{fname}'
        object_key = staging_video_key(day, fname)
        uploaded = False
        uri: str | None = None
        size = 0
        try:
            uri = _upload_file_to_minio(local_path=str(path), object_key=object_key)
            size = path.stat().st_size
            record = RecordedVideo(
                uri=uri,
                size=size,
                created_at=time.time(),
                started_at=float(started_at) or time.time(),
                ended_at=float(ended_at) or time.time(),
                track_ids=track_ids,
            )
            self._video_registry.register_fused(record)
            uploaded = True
            _log.info(
                'MinIO staging fused video s3://%s/%s tracks=%s',
                settings.MINIO_BUCKET,
                object_key,
                sorted(track_ids),
            )
            self._late_attach_videos(track_ids, record, fused=True)
        except Exception:
            _log.exception('Failed to upload recorded video to MinIO: %s', str(path))
        finally:
            if uploaded:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    _log.warning('Failed to remove runtime video temp file: %s', str(path))
            else:
                _log.warning(
                    'Keeping local recording after failed or skipped MinIO upload: %s',
                    str(path),
                )

    def _upload_recorded_single_video(
        self,
        local_path: str,
        camera_id: int,
        track_ids: frozenset[str] = frozenset(),
        started_at: float = 0.0,
        ended_at: float = 0.0,
    ) -> None:
        path = Path(local_path)
        if not path.exists():
            return

        day = self._utc_staging_day()
        fname = path.name
        prefix = f'single_{int(camera_id)}_'
        if not fname.startswith(prefix):
            fname = f'{prefix}{fname}'
        object_key = staging_video_key(day, fname)
        uploaded = False
        try:
            uri = _upload_file_to_minio(local_path=str(path), object_key=object_key)
            size = path.stat().st_size
            record = RecordedVideo(
                uri=uri,
                size=size,
                created_at=time.time(),
                started_at=float(started_at) or time.time(),
                ended_at=float(ended_at) or time.time(),
                track_ids=track_ids,
            )
            self._video_registry.register_single(record)
            uploaded = True
            _log.info(
                'MinIO staging single video s3://%s/%s tracks=%s',
                settings.MINIO_BUCKET,
                object_key,
                sorted(track_ids),
            )
            self._late_attach_videos(track_ids, record, fused=False)
        except Exception:
            _log.exception(
                'Failed to upload single-camera recorded video to MinIO: %s',
                str(path),
            )
        finally:
            if uploaded:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    _log.warning('Failed to remove runtime single-video temp file: %s', str(path))
            else:
                _log.warning(
                    'Keeping local single-camera recording after failed MinIO upload: %s',
                    str(path),
                )

    def _late_attach_videos(
        self,
        track_ids: frozenset[str],
        record: RecordedVideo,
        *,
        fused: bool,
    ) -> None:
        """If detection was persisted before upload finished, attach video now."""
        if not track_ids:
            return
        db = SessionLocal()
        try:
            seen_det: set[int] = set()
            for tid in track_ids:
                for lookup_id in self._lookup_track_ids(str(tid)):
                    det = detection_repo.get_by_track_id(db, lookup_id)
                    if det is None or det.id in seen_det:
                        continue
                    seen_det.add(det.id)
                    if fused:
                        if det.video_path:
                            continue
                    else:
                        has_single = (
                            db.query(DetectionMedia)
                            .filter(
                                DetectionMedia.detection_id == det.id,
                                DetectionMedia.media_type == 'video',
                                DetectionMedia.file_path.like('%/single_%'),
                            )
                            .first()
                            is not None
                        )
                        if has_single:
                            continue
                    self._attach_video_to_detection(db, det, record, fused=fused)
        except Exception:
            _log.exception('Late video attach failed for tracks=%s', sorted(track_ids))
        finally:
            db.close()

    def _attach_video_to_detection(
        self,
        db: Session,
        det: Detection,
        record: RecordedVideo,
        *,
        fused: bool,
    ) -> None:
        safe_t = _safe_key_segment(str(det.track_id))
        start_dt = det.start_time
        if start_dt is None:
            return
        day_bucket = start_dt.strftime('%d-%m-%Y')

        if fused:
            raw_fname = record.uri.rsplit('/', 1)[-1]
            ts_part = raw_fname[len('fused_'):] if raw_fname.startswith('fused_') else raw_fname
            dest_fname = f'fused_{safe_t}_{ts_part}'
            video_uri = self._promote_staging_video(
                record.uri,
                day_bucket,
                det.id,
                dest_fname=dest_fname,
            )
            exists = (
                db.query(DetectionMedia)
                .filter(
                    DetectionMedia.detection_id == det.id,
                    DetectionMedia.media_type == 'video',
                    DetectionMedia.file_path == video_uri,
                )
                .first()
                is not None
            )
            if not exists:
                detection_media_repo.create(
                    db,
                    {
                        'detection_id': det.id,
                        'media_type': 'video',
                        'file_path': video_uri,
                        'file_size': record.size,
                    },
                )
            det_row = db.query(Detection).filter(Detection.id == det.id).first()
            if det_row is not None and not det_row.video_path:
                det_row.video_path = video_uri
                db.add(det_row)
            db.commit()
            return

        raw_fname = record.uri.rsplit('/', 1)[-1]
        if raw_fname.startswith('single_'):
            parts = raw_fname[len('single_'):]
            first_under = parts.find('_')
            if first_under != -1:
                cam_prefix = parts[:first_under]
                ts_part = parts[first_under + 1:]
                dest_fname = f'single_{cam_prefix}_{safe_t}_{ts_part}'
            else:
                dest_fname = f'single_{safe_t}_{parts}'
        else:
            dest_fname = f'single_{safe_t}_{raw_fname}'
        single_uri = self._promote_staging_video(
            record.uri,
            day_bucket,
            det.id,
            dest_fname=dest_fname,
        )
        exists_single = (
            db.query(DetectionMedia)
            .filter(
                DetectionMedia.detection_id == det.id,
                DetectionMedia.media_type == 'video',
                DetectionMedia.file_path == single_uri,
            )
            .first()
            is not None
        )
        if not exists_single:
            detection_media_repo.create(
                db,
                {
                    'detection_id': det.id,
                    'media_type': 'video',
                    'file_path': single_uri,
                    'file_size': record.size,
                },
            )
        db.commit()

    def _persist_track_removed(self, db: Session, tb: Any, hist: list[tuple[str, float]]) -> None:
        """Persist finalized track to DB tables: vessel, detection, and port_log."""
        det_id_for_invoice: int | None = None
        try:
            ship_id = (tb.ship_id or "UNKNOWN").strip().upper()
            start_dt_utc = datetime.datetime.fromtimestamp(tb.first_seen_ts, tz=datetime.timezone.utc)
            end_dt_utc = datetime.datetime.fromtimestamp(tb.last_seen_ts, tz=datetime.timezone.utc)
            berth_in_dt = (
                datetime.datetime.fromtimestamp(tb.berth_in_ts, tz=datetime.timezone.utc)
                if getattr(tb, 'berth_in_ts', None)
                else None
            )
            berth_out_dt = (
                datetime.datetime.fromtimestamp(tb.berth_out_ts, tz=datetime.timezone.utc)
                if getattr(tb, 'berth_out_ts', None)
                else None
            )
            # Phương án C — OUT suy diễn: track có berth_in nhưng thiếu berth_out
            # crossing (track đứt trong zone, OUT không kịp emit) thì suy ra OUT =
            # last_seen (end_dt_utc) — mốc frame cuối cùng còn thấy tàu. end_dt_utc
            # đã là thời điểm rời gần đúng, KHÔNG chứa độ trễ finalize (reid+handoff),
            # vì last_seen_ts chỉ cập nhật ở frame khớp cuối. Đánh dấu nguồn để phân
            # biệt với OUT crossing thật (billing/report có thể lọc/duyệt lại).
            berth_out_source = 'crossing' if berth_out_dt is not None else None
            # Phương án A1 — IN suy diễn (đối xứng với OUT suy diễn ở dưới): track
            # CÓ danh tính (ship_id thật hoặc OCR đọc được biển trong hist) nhưng
            # thiếu berth_in crossing — do track sinh ra đã nằm trong berth_zone
            # (seed-inside, boundary_crossing.py cố tình KHÔNG phát 'in' để tránh
            # berth_in giả trên camera handoff), hoặc không camera nào bắt được
            # cảnh băng line1→line2 lúc vào — thì suy ra berth_in = first_seen
            # (start_dt_utc), mốc đầu tiên camera này thấy tàu. Đánh dấu nguồn
            # 'inferred' để billing/report phân biệt với 'in' crossing thật (giống
            # berth_out_source='last_seen'). KHÔNG suy cho track vô danh (UNKNOWN,
            # không OCR) để tránh làm nặng phân mảnh: mỗi mảnh vô danh không có
            # arrival thật sẽ thành 1 detection giả. Nếu sau đó có 'in' crossing
            # thật đến qua ReID merge, _attach_track (earliest-wins) vẫn ghi đè.
            berth_in_source = 'crossing' if berth_in_dt is not None else None
            _has_known_id = not is_unknown_ship_id(ship_id)
            _has_ocr_id = any(
                not is_unknown_ship_id(str(candidate or '').strip().upper())
                for candidate, _confidence in (hist or [])
            )
            if (
                berth_in_dt is None
                and start_dt_utc is not None
                and (_has_known_id or _has_ocr_id)
            ):
                berth_in_dt = start_dt_utc
                berth_in_source = 'inferred'
                _log.info(
                    'Inferred IN for track=%s ship=%s: berth_in=first_seen=%s '
                    '(no IN crossing, track seeded inside zone / late handoff)',
                    tb.track_id,
                    ship_id,
                    berth_in_dt,
                )
            if (
                berth_out_dt is None
                and berth_in_dt is not None
                and end_dt_utc is not None
                and end_dt_utc > berth_in_dt
            ):
                berth_out_dt = end_dt_utc
                berth_out_source = 'last_seen'
                _log.info(
                    'Inferred OUT for track=%s ship=%s: berth_out=last_seen=%s '
                    '(no OUT crossing, track dropped in zone)',
                    tb.track_id,
                    ship_id,
                    berth_out_dt,
                )

            min_berth_sec = self._min_berth_duration_sec(db)
            if min_berth_sec > 0:
                # Yêu cầu có thời lượng neo đậu thực sự: phải đủ cả berth_in và
                # berth_out (thật hoặc suy diễn). Track không có berth_in, hoặc không
                # suy diễn được berth_out (thiếu cả last_seen) → bỏ qua, kể cả UNKNOWN.
                if berth_in_dt is None or berth_out_dt is None:
                    _log.info(
                        'Skip persist track=%s ship=%s: no berth duration (in=%s out=%s), '
                        'min_berth=%.1fs',
                        tb.track_id,
                        ship_id,
                        berth_in_dt,
                        berth_out_dt,
                        min_berth_sec,
                    )
                    return
                dwell_sec = (berth_out_dt - berth_in_dt).total_seconds()
                if dwell_sec < min_berth_sec:
                    _log.info(
                        'Skip persist track=%s ship=%s: berth dwell=%.1fs < min_berth=%.1fs '
                        '(out_source=%s)',
                        tb.track_id,
                        ship_id,
                        dwell_sec,
                        min_berth_sec,
                        berth_out_source,
                    )
                    return
            cam_id = int(getattr(tb, 'camera_id', 0) or 0)
            has_known_ship_id = not is_unknown_ship_id(ship_id)
            has_ocr_evidence = any(
                not is_unknown_ship_id(str(candidate or '').strip().upper())
                for candidate, _confidence in (hist or [])
            )
            if (
                self._camera_has_boundary(cam_id)
                and berth_in_dt is None
                and not (has_known_ship_id or has_ocr_evidence)
            ):
                _log.debug(
                    'Skip persist track=%s camera=%s: no valid berth IN and no OCR identity',
                    tb.track_id,
                    cam_id,
                )
                return
            day_bucket = start_dt_utc.strftime('%d-%m-%Y')
            safe_t = _safe_key_segment(str(tb.track_id))

            vessel = vessel_repo.get_by_ship_id_normalized(db, ship_id)
            if not vessel:
                vessel = vessel_repo.create(db, VesselCreate(ship_id=ship_id))
            else:
                vessel_repo.update_last_seen(db, vessel.id)

            lookup_ids = self._lookup_track_ids(str(tb.track_id))
            snap = self._media_collector.pop_any(lookup_ids)
            fused_video = self._video_registry.take_for_any_track_ids(
                lookup_ids,
                float(tb.first_seen_ts),
                float(tb.last_seen_ts),
                fused=True,
            )
            single_video = self._video_registry.take_for_any_track_ids(
                lookup_ids,
                float(tb.first_seen_ts),
                float(tb.last_seen_ts),
                fused=False,
            )

            try:
                det = detection_repo.create(
                    db,
                    DetectionCreate(
                        vessel_id=vessel.id,
                        track_id=tb.track_id,
                        start_time=start_dt_utc,
                        end_time=end_dt_utc,
                        berth_in_time=berth_in_dt,
                        berth_out_time=berth_out_dt,
                        berth_out_source=berth_out_source,
                        berth_in_source=berth_in_source,
                        video_path=None,
                        audit_image_path=None,
                        ocr_results=[{'id': h[0], 'conf': h[1]} for h in hist],
                        confidence=tb.conf,
                    ),
                )
            except IntegrityError:
                db.rollback()
                det = detection_repo.get_by_track_id(db, str(tb.track_id))
                if det is None:
                    raise

            det_id_for_invoice = det.id
            _log.info(
                'PERSIST detection id=%s ship_id=%s track=%s berth_in=%s berth_out=%s(%s) votes=%d',
                det.id,
                ship_id,
                tb.track_id,
                berth_in_dt.isoformat() if berth_in_dt else '-',
                berth_out_dt.isoformat() if berth_out_dt else '-',
                berth_out_source or '-',
                len(hist),
            )

            video_uri: str | None = None
            if fused_video is not None:
                raw_fname = fused_video.uri.rsplit('/', 1)[-1]
                ts_part = raw_fname[len('fused_'):] if raw_fname.startswith('fused_') else raw_fname
                fused_dest = f'fused_{safe_t}_{ts_part}'
                video_uri = self._promote_staging_video(
                    fused_video.uri,
                    day_bucket,
                    det.id,
                    dest_fname=fused_dest,
                )

            single_video_uri: str | None = None
            if single_video is not None:
                raw_fname = single_video.uri.rsplit('/', 1)[-1]
                if raw_fname.startswith('single_'):
                    parts = raw_fname[len('single_'):]
                    first_under = parts.find('_')
                    if first_under != -1:
                        cam_prefix = parts[:first_under]
                        ts_part = parts[first_under + 1:]
                        single_dest = f'single_{cam_prefix}_{safe_t}_{ts_part}'
                    else:
                        single_dest = f'single_{safe_t}_{parts}'
                else:
                    single_dest = f'single_{safe_t}_{raw_fname}'
                single_video_uri = self._promote_staging_video(
                    single_video.uri,
                    day_bucket,
                    det.id,
                    dest_fname=single_dest,
                )

            audit_uri: str | None = None
            single_image_uri: str | None = None
            if snap is not None:
                from app.services.ai.track_media_collector import encode_jpeg_bgr

                # OUT fallback: a track that never emitted a clean OUT crossing
                # (e.g. still moored at finalize) uses the latest overlay frame of
                # the detection as its OUT image. No best-shot fallback.
                single_out_jpeg = snap.single_overlay_out_jpeg
                single_out_cam = snap.single_overlay_out_camera_id
                if single_out_jpeg is None and snap.single_latest_frame is not None:
                    single_out_jpeg = encode_jpeg_bgr(snap.single_latest_frame)
                    single_out_cam = snap.single_latest_camera_id
                fused_out_jpeg = snap.fused_overlay_out_jpeg
                if fused_out_jpeg is None and snap.fused_latest_frame is not None:
                    fused_out_jpeg = encode_jpeg_bgr(snap.fused_latest_frame)

                cam_in = snap.single_overlay_in_camera_id if snap.single_overlay_in_camera_id is not None else 0
                cam_out = single_out_cam if single_out_cam is not None else 0
                uploads: list[tuple[bytes | None, str]] = [
                    (snap.single_overlay_in_jpeg, f'single_overlay_in_{cam_in}_{safe_t}.jpg'),
                    (single_out_jpeg, f'single_overlay_out_{cam_out}_{safe_t}.jpg'),
                    (snap.fused_overlay_in_jpeg, f'fused_overlay_in_{safe_t}.jpg'),
                    (fused_out_jpeg, f'fused_overlay_out_{safe_t}.jpg'),
                ]
                for jpeg_bytes, fname in uploads:
                    if not jpeg_bytes:
                        continue
                    object_key = final_image_key(day_bucket, int(det.id), fname)
                    uri = _upload_bytes_to_minio(
                        data=jpeg_bytes,
                        object_key=object_key,
                        content_type='image/jpeg',
                    )
                    _log.info(
                        'MinIO final image s3://%s/%s detection_id=%s',
                        settings.MINIO_BUCKET,
                        object_key,
                        det.id,
                    )
                    if audit_uri is None:
                        audit_uri = uri
                    if fname.startswith('single_overlay_in_'):
                        single_image_uri = uri
                    detection_media_repo.create(
                        db,
                        {
                            'detection_id': det.id,
                            'media_type': 'image',
                            'file_path': uri,
                            'file_size': len(jpeg_bytes),
                        },
                    )

            if video_uri:
                exists = (
                    db.query(DetectionMedia)
                    .filter(
                        DetectionMedia.detection_id == det.id,
                        DetectionMedia.media_type == 'video',
                        DetectionMedia.file_path == video_uri,
                    )
                    .first()
                    is not None
                )
                if not exists:
                    detection_media_repo.create(
                        db,
                        {
                            'detection_id': det.id,
                            'media_type': 'video',
                            'file_path': video_uri,
                            'file_size': fused_video.size if fused_video else None,
                        },
                    )

            if single_video_uri:
                exists_single = (
                    db.query(DetectionMedia)
                    .filter(
                        DetectionMedia.detection_id == det.id,
                        DetectionMedia.media_type == 'video',
                        DetectionMedia.file_path == single_video_uri,
                    )
                    .first()
                    is not None
                )
                if not exists_single:
                    detection_media_repo.create(
                        db,
                        {
                            'detection_id': det.id,
                            'media_type': 'video',
                            'file_path': single_video_uri,
                            'file_size': single_video.size if single_video else None,
                        },
                    )

            det_row = db.query(Detection).filter(Detection.id == det.id).first()
            if det_row is not None:
                det_row.video_path = video_uri
                det_row.audit_image_path = audit_uri
                db.add(det_row)
                db.commit()

            # 3. Tự động hoàn thành đơn hàng nếu có
            pending_order = order_repo.get_pending_by_vessel(db, vessel.id)
            if pending_order:
                order_repo.complete_order(db, pending_order.id)
                _log.info(f"Auto-completed order {pending_order.order_number} for vessel {ship_id}")

            # 4. Lưu Port Log tổng hợp (phục vụ export Excel)
            today_logs = port_log_repo.get_logs_by_date(db, datetime.date.today())
            next_seq = len(today_logs) + 1
            
            vote_summary: dict[str, Any] = {}
            for sid, conf in hist:
                if sid not in vote_summary:
                    vote_summary[sid] = {"count": 0, "total_conf": 0.0}
                vote_summary[sid]["count"] += 1
                vote_summary[sid]["total_conf"] += conf

            evidence_summary = getattr(tb, 'ship_id_evidence_summary', None)
            if evidence_summary:
                vote_summary['_evidence'] = evidence_summary

            port_log_repo.create(db, PortLogCreate(
                seq=next_seq,
                ships_completed_today=next_seq,
                logged_at=datetime.datetime.now(datetime.timezone.utc),
                track_id=tb.track_id,
                voted_ship_id=ship_id,
                first_seen_at=start_dt_utc,
                last_seen_at=end_dt_utc,
                confidence=tb.conf,
                ocr_attempts=len(hist),
                vote_summary=vote_summary
            ))

            # Zalo notify: (1) tàu UNKNOWN → xác nhận danh tính như cũ;
            # (2) tàu nhận diện bằng EMBEDDING mà KHÔNG có OCR → gửi xác nhận
            #     kết quả embedding (OK / SET mã mới / SKIP giữ nguyên).
            decision_source = str(getattr(tb, 'ship_id_decision_source', '') or '')
            notify_kind: str | None = None
            if settings.ZALO_ENABLED and det_id_for_invoice is not None:
                if is_unknown_ship_id(ship_id):
                    notify_kind = 'unknown'
                elif decision_source == 'embedding' and not has_ocr_evidence:
                    notify_kind = 'embedding_confirm'

            if notify_kind is not None:
                from app.repositories.camera_repository import camera_repo
                from app.services import zalo_service

                camera_name = ''
                cam_id = getattr(tb, 'camera_id', None)
                if cam_id is not None:
                    cam = camera_repo.get(db, int(cam_id))
                    if cam is not None:
                        camera_name = str(cam.camera_name or f'Camera {cam.id}')

                zalo_service.schedule_unknown_detection_notify(
                    detection_id=int(det_id_for_invoice),
                    image_minio_path=single_image_uri or audit_uri,
                    video_minio_path=single_video_uri or video_uri,
                    expect_video=bool(single_video_uri or video_uri),
                    camera_name=camera_name,
                    start_time=start_dt_utc,
                    kind=notify_kind,
                )
        except Exception:
            db.rollback()
            raise

        if det_id_for_invoice is not None:
            try:
                from app.services.detection_merge_service import absorb_contained

                det_id_for_invoice = absorb_contained(db, det_id_for_invoice)
            except Exception:
                _log.exception(
                    'detection_merge failed for detection_id=%s',
                    det_id_for_invoice,
                )
            try:
                from app.services.detection_invoice_service import ensure_ai_invoice_for_detection

                ensure_ai_invoice_for_detection(det_id_for_invoice)
                _log.info('INVOICE ensured for detection id=%s', det_id_for_invoice)
            except Exception:
                _log.exception(
                    'AI invoice creation failed for detection_id=%s',
                    det_id_for_invoice,
                )

            # Cảnh báo Zalo nghiệp vụ: quá hạn đăng kiểm, ngoài giờ, quá thời gian/lượt.
            try:
                from app.services.registry_expiry_alert_service import (
                    schedule_berthing_alerts,
                )

                schedule_berthing_alerts(det_id_for_invoice)
            except Exception:
                _log.exception(
                    'berthing alert scheduling failed for detection_id=%s',
                    det_id_for_invoice,
                )

    def _on_track_removed_db(self, tb: Any, hist: list[tuple[str, float]]):
        """Callback khi một tàu rời khỏi khung hình, lưu vào DB."""
        db = SessionLocal()
        try:
            self._persist_track_removed(db, tb, hist)
        finally:
            db.close()

    def start(self, source: str, enable_ocr: bool | None = None) -> None:
        if self.is_running:
            _log.warning("Pipeline is already running")
            return

        self._gpu_status = log_gpu_runtime_status('pipeline_start_single')
        self._stop.clear()
        self._reset_runtime_queues()
        pipeline_preview.clear()
        runtime_cfg = self._load_runtime_config()
        # Chế độ 1 camera cổ điển chạy qua YoloWorkerThread — đường đó không thu nhỏ frame
        # nên báo đúng là 1.0 dù cấu hình có đặt detect_scale.
        self._active_detect_scale = 1.0
        self._frame_stats.reset()
        self._apply_rtsp_decode_config(runtime_cfg)

        # Load detector if not loaded
        detector_sig = (
            runtime_cfg['model_path'],
            runtime_cfg['device'],
            float(runtime_cfg['conf']),
            int(runtime_cfg['yolo_imgsz']),
        )
        if self._detector is None or self._detector_signature != detector_sig:
            self._detector, _ = load_yolo_detector(
                runtime_cfg['model_path'],
                runtime_cfg['device'],
                runtime_cfg['conf'],
                imgsz=int(runtime_cfg['yolo_imgsz']),
            )
            self._detector_signature = detector_sig

        # Use settings for all params
        ocr_active = enable_ocr if enable_ocr is not None else runtime_cfg['enable_ocr']
        ocr_label_ttl = runtime_cfg['ocr_label_ttl_sec']
        
        db_cb = self._on_track_removed_db
        
        def combined_on_removed(tb, hist):
            db_cb(tb, hist)

        self._boat_tracker = BoatTracker(
            **self._tracker_kwargs(runtime_cfg, on_track_removed=combined_on_removed),
        )
        self._start_media_sample_worker()

        # Đồng bộ FPS: reader @ record_fps; preview từ reader (mượt), YOLO ghi đè khi xong.
        try:
            self._configure_dashboard_preview(runtime_cfg)
        except Exception:
            pass

        def _push_reader_preview(frame) -> None:
            try:
                pipeline_preview.push_bgr_frame(frame)
            except Exception:
                pass

        self._reader = FrameReaderThread(
            source,
            self._frame_queue,
            self._stop,
            target_fps=runtime_cfg['record_fps'],
            on_frame_emitted=_push_reader_preview,
        )
        self._yolo_worker = YoloWorkerThread(
            self._detector, self._boat_tracker, self._frame_queue, self._result_queue,
            self._ocr_queue, self._video_queue, self._stop, ocr_active,
            ocr_interval_sec=runtime_cfg['ocr_interval_sec'],
            ocr_cache=self.ocr_cache, ocr_lock=self.ocr_lock, ocr_label_ttl=ocr_label_ttl,
            record_overlay_resize_scale=runtime_cfg['resize_scale'],
            enable_preview_stream=True,
            on_overlay_media_sample=self._recording_yolo_single_overlay,
            ship_id_lock_stable_sec=float(runtime_cfg['ship_id_lock_stable_sec']),
            catalog_is_known=self._ship_id_catalog.is_known,
        )

        if ocr_active:
            recognizer = create_ship_id_recognizer(rule_engine=get_rule_engine())
            self._ocr_recognizer = recognizer
            self._ocr_worker = OcrWorkerThread(
                recognizer, self._ocr_queue, self.ocr_cache, self.ocr_lock, self._stop,
                ocr_label_ttl, runtime_cfg['save_min_interval_sec'],
                boat_tracker=self._boat_tracker,
                runs_base=str(self._runtime_media_base / 'detect'),
                save_ocr_audit_frames=runtime_cfg['ocr_audit_save_frames'],
                on_image_captured=self._upload_captured_image,
                on_ocr_track_media=self._on_ocr_track_media,
                is_known_ship_id=self._ship_id_catalog.is_known,
            )

        if runtime_cfg['record_enable']:
            self._video_worker = VideoRecorderThread(
                self._video_queue, self._stop,
                max_duration_sec=runtime_cfg['record_max_duration_min'] * 60,
                gap_sec=runtime_cfg['record_no_boat_gap_sec'],
                record_fps=runtime_cfg['record_fps'],
                runs_base=str(self._runtime_media_base / 'detect'),
                on_video_saved=self._upload_recorded_video,
            )
            self._video_worker.start()

        self._reader.start()
        self._yolo_worker.start()
        if self._ocr_worker:
            self._ocr_worker.start()
            ocr_device = getattr(self._ocr_recognizer, 'device', 'in-process')
            _log.info('OCR enabled device=%s', ocr_device)
            
        _log.info(f"Pipeline started with source: {source}")

    @staticmethod
    def _resolve_group_camera_order(group: Any, enabled_members: list[Any]) -> list[int]:
        ordered: list[int] = []
        for member in sorted(
            enabled_members,
            key=lambda item: (
                int(getattr(item, 'priority', 0) or 0),
                int(item.camera_id),
            ),
        ):
            camera_key = int(member.camera_id)
            if camera_key not in ordered:
                ordered.append(camera_key)
        return ordered

    def _build_seam_anchor(
        self,
        *,
        camera_order: list[int],
        runtime_cfg: dict[str, Any],
        group_id: int | None,
        embedding_extractor: EmbeddingExtractor | None,
        on_release: Any,
    ) -> tuple[BackgroundModelRegistry | None, SeamAnchorVerifier | None]:
        if not runtime_cfg.get('seam_anchor_enabled', True) or len(camera_order) < 2:
            return None, None

        from app.repositories.anchored_identity_repository import anchored_identity_repo
        from app.services.ai import seam_anchor_baseline

        bg_cfg = BackgroundModelConfig(
            history=int(runtime_cfg['bg_model_history']),
            var_threshold=float(runtime_cfg['bg_var_threshold']),
            min_seed_frames=int(runtime_cfg['bg_min_seed_frames']),
        )
        bg_registry = BackgroundModelRegistry(bg_cfg)
        for camera_id in camera_order:
            model = bg_registry.ensure(int(camera_id))
            baseline = seam_anchor_baseline.load_baseline(group_id, int(camera_id))
            if baseline is not None:
                model.lock_from_frame(baseline)
                _log.info(
                    'seam_anchor: restored baseline for camera_id=%s group_id=%s',
                    camera_id,
                    group_id,
                )

        anchor_cfg = SeamAnchorConfig(
            enabled=True,
            seam_roi_width_ratio=float(runtime_cfg['seam_roi_width_ratio']),
            seam_proximity_px=int(runtime_cfg['seam_proximity_px']),
            bg_subtract_threshold=float(runtime_cfg['bg_subtract_threshold']),
            iou_resurrect_threshold=float(runtime_cfg['anchor_iou_resurrect_threshold']),
            embedding_match_enabled=bool(runtime_cfg['anchor_embedding_match_enabled']),
            embedding_sim_threshold=float(runtime_cfg['anchor_embedding_sim_threshold']),
            revalidation_sec=float(runtime_cfg['anchor_revalidation_sec']),
            departed_grace_sec=float(runtime_cfg['anchor_departed_grace_sec']),
            max_duration_sec=float(runtime_cfg['anchor_max_duration_sec']),
            db_update_debounce_sec=float(runtime_cfg['anchor_db_update_debounce_sec']),
            min_stationary_sec=float(runtime_cfg['anchor_min_stationary_sec']),
            color_hsv_tolerance_h=int(runtime_cfg['anchor_color_hsv_tolerance_h']),
        )
        verifier = SeamAnchorVerifier(
            bg_registry=bg_registry,
            camera_order=camera_order,
            config=anchor_cfg,
            on_release=on_release,
            embedding_extractor=embedding_extractor,
            anchored_repo=anchored_identity_repo,
            group_id=group_id,
        )
        verifier.restore_from_db()
        if self._reid_manager is not None:
            self._reid_manager.sync_restored_anchors(verifier.states_snapshot())
        return bg_registry, verifier

    @staticmethod
    def _load_camera_json_configs(
        camera_ids: list[int],
    ) -> tuple[dict[int, dict | None], dict[int, dict | None]]:
        from app.repositories.camera_repository import camera_repo

        boundary_by_camera: dict[int, dict | None] = {}
        detection_by_camera: dict[int, dict | None] = {}
        db = SessionLocal()
        try:
            for camera_id in camera_ids:
                cam = camera_repo.get(db, int(camera_id))
                boundary_by_camera[int(camera_id)] = (
                    cam.boundary_lines if cam is not None else None
                )
                detection_by_camera[int(camera_id)] = (
                    cam.detection_settings if cam is not None else None
                )
        finally:
            db.close()
        return boundary_by_camera, detection_by_camera

    def _is_track_identity_locked(self, camera_id: int, track_id: str) -> bool:
        camera_key = int(camera_id)
        track_key = str(track_id)
        for pipeline in self._per_camera_pipelines:
            if int(pipeline.config.camera_id) != camera_key:
                continue
            return pipeline._tracker.is_track_identity_locked(track_key)
        return self._boat_tracker.is_track_identity_locked(track_key)

    def _start_group_hybrid(
        self,
        group: Any,
        enabled_members: list[Any],
        runtime_cfg: dict[str, Any],
        ocr_active: bool,
        combined_on_removed,
    ) -> None:
        camera_order = self._resolve_group_camera_order(group, enabled_members)
        self._primary_record_camera_id = int(camera_order[0]) if camera_order else None
        record_enabled = bool(runtime_cfg['record_enable'])
        multi_cam = len(camera_order) > 1
        members_by_camera_id = {int(member.camera_id): member for member in enabled_members}
        ordered_members = [members_by_camera_id[camera_id] for camera_id in camera_order]
        boundary_by_camera, detection_by_camera = self._load_camera_json_configs(camera_order)
        self._reid_manager = CrossCameraReIdManager(
            camera_order=camera_order,
            visual_threshold=runtime_cfg['reid_visual_threshold'],
            handoff_window_sec=runtime_cfg['reid_handoff_window_sec'],
            primary_zone_ratio=runtime_cfg['primary_zone_ratio'],
            edge_zone_ratio=runtime_cfg['edge_zone_ratio'],
            on_global_track_removed=combined_on_removed,
            ship_id_catalog=self._ship_id_catalog,
            overlap_merge_config=OverlapMergeConfig(
                enabled=bool(runtime_cfg['reid_overlap_merge_enabled']),
                edge_zone_ratio=float(runtime_cfg['reid_edge_zone_ratio']),
                embedding_weight=float(runtime_cfg['reid_embedding_weight']),
                color_weight=float(runtime_cfg['reid_color_weight']),
                size_weight=float(runtime_cfg['reid_size_weight']),
                accept_threshold=float(runtime_cfg['reid_accept_threshold']),
                min_margin=float(runtime_cfg['reid_min_margin']),
            ),
            directional_handoff_config=DirectionalHandoffConfig(
                enabled=bool(runtime_cfg['reid_directional_handoff_enabled']),
                max_transit_sec=float(runtime_cfg['reid_directional_max_transit_sec']),
                min_transit_sec=float(runtime_cfg['reid_directional_min_transit_sec']),
                min_velocity_px=float(runtime_cfg['reid_directional_min_velocity_px']),
                edge_zone_ratio=float(runtime_cfg['reid_directional_edge_zone_ratio']),
                embedding_weight=float(runtime_cfg['reid_directional_embedding_weight']),
                direction_weight=float(runtime_cfg['reid_directional_direction_weight']),
                time_weight=float(runtime_cfg['reid_directional_time_weight']),
                accept_threshold=float(runtime_cfg['reid_directional_accept_threshold']),
                embedding_floor=float(runtime_cfg['reid_directional_embedding_floor']),
            ),
            reverse_motion_guard_enabled=bool(
                runtime_cfg['reid_reverse_motion_guard_enabled']
            ),
            embedding_diversity_max_cos=float(
                runtime_cfg['reid_embedding_diversity_max_cos']
            ),
        )
        # Feed camera layout geometry (layout_x per camera) so the directional
        # handoff matcher knows which camera sits left/right of which.
        try:
            layout_x_by_camera = {
                int(member.camera_id): float(getattr(member, 'layout_x', 0) or 0)
                for member in ordered_members
            }
            self._reid_manager.set_camera_layout(layout_x_by_camera)
        except Exception:
            _log.exception('reid: failed to set camera layout geometry')
        embedding_extractor = EmbeddingExtractor(
            model_path=runtime_cfg['reid_embedding_model_path'] or None,
            device=runtime_cfg['device'],
            use_visual_model=bool(runtime_cfg['enable_visual_id']),
            visual_model_path=runtime_cfg['visual_model_path'] or None,
            visual_backbone=runtime_cfg['visual_backbone'],
            visual_embedding_dim=runtime_cfg['visual_embedding_dim'],
            visual_device=runtime_cfg['visual_device'] or runtime_cfg['device'],
        )

        reid_manager = self._reid_manager
        self._bg_registry, self._seam_anchor_verifier = self._build_seam_anchor(
            camera_order=camera_order,
            runtime_cfg=runtime_cfg,
            group_id=int(getattr(group, 'id', 0) or 0) or None,
            embedding_extractor=embedding_extractor,
            on_release=reid_manager.handle_anchor_release,
        )
        if self._seam_anchor_verifier is not None:
            self._reid_manager.set_seam_anchor_verifier(self._seam_anchor_verifier)

        visual_enabled = bool(runtime_cfg['enable_visual_id'])
        if visual_enabled:
            self._init_visual_stack(runtime_cfg)
            if self._visual_extractor is not None and self._identity_fusion is not None:
                self._visual_queue = queue.Queue(maxsize=max(20, len(camera_order) * 8))
                self._visual_worker = VisualIdWorkerThread(
                    worker_name='visual-id-worker',
                    visual_queue=self._visual_queue,
                    extractor=self._visual_extractor,
                    vector_store=self._vector_store,
                    runtime_cache=self._runtime_cache,
                    identity_fusion=self._identity_fusion,
                    stop_event=self._stop,
                    top_k=runtime_cfg['visual_top_k'],
                    min_crop_area=runtime_cfg['visual_min_crop_area'],
                    ocr_score_threshold=runtime_cfg['visual_match_threshold'],
                    no_ocr_score_threshold=runtime_cfg['visual_no_ocr_match_threshold'],
                    ship_id_catalog=self._ship_id_catalog,
                )
                self._visual_worker.start()

        self._start_media_sample_worker()

        try:
            self._configure_dashboard_preview(runtime_cfg)
        except Exception:
            pass

        if record_enabled:
            self._video_worker = VideoRecorderThread(
                self._video_queue,
                self._stop,
                max_duration_sec=runtime_cfg['record_max_duration_min'] * 60,
                gap_sec=runtime_cfg['record_no_boat_gap_sec'],
                record_fps=runtime_cfg['record_fps'],
                runs_base=str(self._runtime_media_base / 'detect'),
                on_video_saved=self._upload_recorded_video,
            )
            self._video_worker.start()

        if record_enabled and multi_cam and self._primary_record_camera_id is not None:
            primary_cam = self._primary_record_camera_id
            self._single_video_worker = VideoRecorderThread(
                self._single_video_queue,
                self._stop,
                max_duration_sec=runtime_cfg['record_max_duration_min'] * 60,
                gap_sec=runtime_cfg['record_no_boat_gap_sec'],
                record_fps=runtime_cfg['record_fps'],
                runs_base=str(self._runtime_media_base / 'detect'),
                on_video_saved=(
                    lambda p, ids, s, e, cid=primary_cam: self._upload_recorded_single_video(
                        p, cid, ids, s, e
                    )
                ),
                exclusive_single_track=True,
            )
            self._single_video_worker.start()

        if ocr_active:
            recognizer = create_ship_id_recognizer(rule_engine=get_rule_engine())
            self._ocr_recognizer = recognizer
            self._ocr_queue = queue.Queue(maxsize=max(20, len(camera_order) * 8))
            self._ocr_worker = OcrWorkerThread(
                recognizer,
                self._ocr_queue,
                self.ocr_cache,
                self.ocr_lock,
                self._stop,
                runtime_cfg['ocr_label_ttl_sec'],
                runtime_cfg['save_min_interval_sec'],
                runs_base=str(self._runtime_media_base / 'detect'),
                save_ocr_audit_frames=runtime_cfg['ocr_audit_save_frames'],
                on_image_captured=self._upload_captured_image,
                on_ocr_track_media=self._on_ocr_track_media,
                is_known_ship_id=self._ship_id_catalog.is_known,
            )
            self._ocr_worker.start()
            ocr_device = getattr(self._ocr_recognizer, 'device', 'in-process')
            _log.info('OCR enabled device=%s', ocr_device)

        self._group_frame_hub = GroupFrameHub(
            group=group,
            enabled_members=enabled_members,
            runtime_cfg=runtime_cfg,
            stop_event=self._stop,
            video_queue=self._video_queue if runtime_cfg['record_enable'] else None,
            distribute_per_camera=True,
            bg_registry=self._bg_registry,
            seam_anchor_verifier=self._seam_anchor_verifier,
            on_fused_media_sample=self._recording_fused_media_sample,
            ocr_cache=self.ocr_cache,
            ocr_lock=self.ocr_lock,
            ocr_label_ttl_sec=runtime_cfg['ocr_label_ttl_sec'],
            boundary_by_camera=boundary_by_camera,
        )

        self._per_camera_pipelines = []
        snapshot_enabled = bool(runtime_cfg['enable_training_snapshot'])
        training_snapshot_collector: TrainingSnapshotCollector | None = None
        if snapshot_enabled:
            snap_rel = str(runtime_cfg['training_snapshot_base_dir'] or 'snapshot').strip()
            snap_base = Path(snap_rel) if Path(snap_rel).is_absolute() else _SERVER_ROOT / snap_rel
            training_snapshot_collector = TrainingSnapshotCollector(
                TrainingSnapshotConfig(
                    enabled=True,
                    interval_sec=float(runtime_cfg['training_snapshot_interval_sec']),
                    base_dir=snap_base,
                    jpeg_quality=int(runtime_cfg['training_snapshot_jpeg_quality']),
                )
            )
            _log.info(
                'Training snapshot collector enabled base_dir=%s (yolo: %s/yolo) interval_sec=%s',
                snap_base,
                snap_base,
                runtime_cfg['training_snapshot_interval_sec'],
            )

        primary = self._primary_record_camera_id
        for member in ordered_members:
            camera_id = int(member.camera_id)
            single_cam_q = (
                self._single_video_queue
                if (
                    record_enabled
                    and multi_cam
                    and primary is not None
                    and camera_id == primary
                )
                else None
            )
            pipeline_config = PerCameraPipelineConfig(
                camera_id=camera_id,
                source=member.camera.rtsp_url,
                record_fps=runtime_cfg['record_fps'],
                enable_ocr=ocr_active,
                ocr_interval_sec=runtime_cfg['ocr_interval_sec'],
                ocr_label_ttl_sec=runtime_cfg['ocr_label_ttl_sec'],
                save_min_interval_sec=runtime_cfg['save_min_interval_sec'],
                ocr_audit_save_frames=runtime_cfg['ocr_audit_save_frames'],
                resize_scale=runtime_cfg['resize_scale'],
                track_iou_threshold=runtime_cfg['track_iou_threshold'],
                track_dedup_iomin_threshold=runtime_cfg['track_dedup_iomin_threshold'],
                berth_out_grace_sec=runtime_cfg['berth_out_grace_sec'],
                track_reid_window_sec=runtime_cfg['track_reid_window_sec'],
                track_reid_max_dist=runtime_cfg['track_reid_max_dist'],
                track_min_confirm_sec=runtime_cfg['track_min_confirm_sec'],
                track_max_tentative_sec=runtime_cfg['track_max_tentative_sec'],
                track_max_lost_sec=runtime_cfg['track_max_lost_sec'],
                clahe_clip_limit=runtime_cfg['clahe_clip_limit'],
                clahe_tile_size=runtime_cfg['clahe_tile_size'],
                clahe_enable_gray_world=runtime_cfg['clahe_enable_gray_world'],
                clahe_fast=runtime_cfg['clahe_fast'],
                detect_scale=runtime_cfg['detect_scale'],
                crop_pad_ratio=runtime_cfg['crop_pad_ratio'],
                edge_zone_ratio=runtime_cfg['edge_zone_ratio'],
                enable_visual_id=visual_enabled,
                visual_interval_sec=runtime_cfg['visual_id_interval_sec'],
                visual_min_crop_area=runtime_cfg['visual_min_crop_area'],
                enable_training_snapshot=snapshot_enabled,
                training_snapshot_interval_sec=runtime_cfg['training_snapshot_interval_sec'],
                enable_preview_stream=False,
                boundary_lines=boundary_by_camera.get(camera_id),
                detection_settings=detection_by_camera.get(camera_id),
                ship_id_lock_stable_sec=float(runtime_cfg['ship_id_lock_stable_sec']),
                visual_match_threshold=runtime_cfg['visual_match_threshold'],
                visual_no_ocr_match_threshold=runtime_cfg['visual_no_ocr_match_threshold'],
                visual_conflict_threshold=runtime_cfg['visual_conflict_threshold'],
                ocr_confidence_threshold=runtime_cfg['ocr_confidence_threshold'],
            )
            self._per_camera_pipelines.append(
                PerCameraPipeline(
                    config=pipeline_config,
                    detector=self._detector,
                    detector_lock=self._detector_lock,
                    reid_manager=self._reid_manager,
                    embedding_extractor=embedding_extractor,
                    video_queue=None,
                    stop_event=self._stop,
                    ocr_cache=self.ocr_cache,
                    ocr_lock=self.ocr_lock,
                    runs_base=str(self._runtime_media_base / 'detect'),
                    on_image_captured=self._upload_captured_image,
                    on_overlay_media_sample=self._recording_single_media_sample,
                    on_boundary_media_sample=self._recording_boundary_media_sample,
                    input_frame_queue=self._group_frame_hub.queue_for_camera(camera_id),
                    shared_ocr_queue=self._ocr_queue if ocr_active else None,
                    shared_visual_queue=self._visual_queue if visual_enabled else None,
                    single_camera_video_queue=single_cam_q,
                    training_snapshot_collector=training_snapshot_collector,
                    rule_engine=get_rule_engine(),
                    ship_id_catalog=self._ship_id_catalog,
                    frame_stats=self._frame_stats,
                )
            )

        self._group_frame_hub.set_track_providers(
            [
                pipeline.latest_tracks_for_overlay
                for pipeline in self._per_camera_pipelines
            ]
        )
        self._reid_manager.set_is_track_identity_locked(self._is_track_identity_locked)
        self._group_frame_hub.start()
        for pipeline in self._per_camera_pipelines:
            pipeline.start()

        _log.info(
            'Hybrid pipeline started with camera_group_id=%s camera_order=%s record_fps=%s single_record_camera_id=%s embedding_backend=%s',
            group.id,
            camera_order,
            runtime_cfg['record_fps'],
            self._primary_record_camera_id
            if record_enabled and multi_cam
            else None,
            embedding_extractor.backend,
        )
        if visual_enabled and self._visual_extractor is not None:
            _log.info(
                'Visual ID enabled backend=%s qdrant_healthy=%s redis_healthy=%s',
                self._visual_extractor.backend,
                self._vector_store.healthy if self._vector_store is not None else False,
                self._runtime_cache.healthy if self._runtime_cache is not None else False,
            )

    def start_group(self, group: Any, enable_ocr: bool | None = None) -> None:
        if self.is_running:
            _log.warning('Pipeline is already running')
            return

        self._gpu_status = log_gpu_runtime_status('pipeline_start_group')
        enabled_members = [
            member
            for member in group.members
            if bool(member.enabled) and getattr(member, 'camera', None) is not None
        ]
        if not enabled_members:
            raise ValueError('Camera group has no enabled cameras')

        self._stop.clear()
        self._reset_runtime_queues()
        pipeline_preview.clear()
        runtime_cfg = self._load_runtime_config()
        self._active_detect_scale = float(runtime_cfg['detect_scale'])
        self._frame_stats.reset()
        self._apply_rtsp_decode_config(runtime_cfg)

        # Pre-warm GStreamer codec probe cache so per-camera pipelines open
        # via GStreamer NVDEC (GPU BGR convert) instead of FFmpeg (CPU scale).
        self._warmup_gst_probe_cache(enabled_members)

        detector_sig = (
            runtime_cfg['model_path'],
            runtime_cfg['device'],
            float(runtime_cfg['conf']),
            int(runtime_cfg['yolo_imgsz']),
        )
        if self._detector is None or self._detector_signature != detector_sig:
            self._detector, _ = load_yolo_detector(
                runtime_cfg['model_path'],
                runtime_cfg['device'],
                runtime_cfg['conf'],
                imgsz=int(runtime_cfg['yolo_imgsz']),
            )
            self._detector_signature = detector_sig

        ocr_active = enable_ocr if enable_ocr is not None else runtime_cfg['enable_ocr']
        ocr_label_ttl = runtime_cfg['ocr_label_ttl_sec']

        def combined_on_removed(tb, hist):
            self._on_track_removed_db(tb, hist)

        pipeline_mode = str(getattr(group, 'pipeline_mode', 'hybrid') or 'hybrid').lower()
        if pipeline_mode not in {'hybrid', 'fused'}:
            pipeline_mode = 'hybrid'

        self._active_group_id = int(getattr(group, 'id', 0) or 0) or None

        if pipeline_mode == 'hybrid':
            self._start_group_hybrid(
                group,
                enabled_members,
                runtime_cfg,
                ocr_active,
                combined_on_removed,
            )
            return

        self._boat_tracker = BoatTracker(
            **self._tracker_kwargs(runtime_cfg, on_track_removed=combined_on_removed),
        )
        self._start_media_sample_worker()

        fused_camera_order = self._resolve_group_camera_order(group, enabled_members)
        fused_boundary_by_camera, _ = self._load_camera_json_configs(fused_camera_order)

        self._group_frame_hub = GroupFrameHub(
            group=group,
            enabled_members=enabled_members,
            runtime_cfg=runtime_cfg,
            stop_event=self._stop,
            video_queue=self._video_queue if runtime_cfg['record_enable'] else None,
            yolo_frame_queue=self._frame_queue,
            distribute_per_camera=False,
            on_fused_media_sample=self._recording_fused_media_sample,
            ocr_cache=self.ocr_cache,
            ocr_lock=self.ocr_lock,
            ocr_label_ttl_sec=runtime_cfg['ocr_label_ttl_sec'],
            boundary_by_camera=fused_boundary_by_camera,
        )
        self._group_frame_hub.set_track_providers([self._boat_tracker.confirmed_boats])
        if self._reid_manager is not None:
            self._reid_manager.set_is_track_identity_locked(self._is_track_identity_locked)
        try:
            self._configure_dashboard_preview(runtime_cfg)
        except Exception:
            pass

        self._yolo_worker = YoloWorkerThread(
            self._detector,
            self._boat_tracker,
            self._frame_queue,
            self._result_queue,
            self._ocr_queue,
            None,
            self._stop,
            ocr_active,
            ocr_interval_sec=runtime_cfg['ocr_interval_sec'],
            ocr_cache=self.ocr_cache,
            ocr_lock=self.ocr_lock,
            ocr_label_ttl=ocr_label_ttl,
            record_overlay_resize_scale=runtime_cfg['resize_scale'],
            enable_preview_stream=False,
            ship_id_lock_stable_sec=float(runtime_cfg['ship_id_lock_stable_sec']),
            catalog_is_known=self._ship_id_catalog.is_known,
        )

        if ocr_active:
            recognizer = create_ship_id_recognizer(rule_engine=get_rule_engine())
            self._ocr_recognizer = recognizer
            self._ocr_worker = OcrWorkerThread(
                recognizer,
                self._ocr_queue,
                self.ocr_cache,
                self.ocr_lock,
                self._stop,
                ocr_label_ttl,
                runtime_cfg['save_min_interval_sec'],
                boat_tracker=self._boat_tracker,
                runs_base=str(self._runtime_media_base / 'detect'),
                save_ocr_audit_frames=runtime_cfg['ocr_audit_save_frames'],
                on_image_captured=self._upload_captured_image,
                on_ocr_track_media=self._on_ocr_track_media,
                is_known_ship_id=self._ship_id_catalog.is_known,
            )

        if runtime_cfg['record_enable']:
            self._video_worker = VideoRecorderThread(
                self._video_queue,
                self._stop,
                max_duration_sec=runtime_cfg['record_max_duration_min'] * 60,
                gap_sec=runtime_cfg['record_no_boat_gap_sec'],
                record_fps=runtime_cfg['record_fps'],
                runs_base=str(self._runtime_media_base / 'detect'),
                on_video_saved=self._upload_recorded_video,
            )
            self._video_worker.start()

        self._group_frame_hub.start()
        self._yolo_worker.start()
        if self._ocr_worker:
            self._ocr_worker.start()
            ocr_device = getattr(self._ocr_recognizer, 'device', 'in-process')
            _log.info('OCR enabled device=%s', ocr_device)

        _log.info(
            'Pipeline started with camera_group_id=%s cameras=%s',
            group.id,
            [int(member.camera_id) for member in enabled_members],
        )

    def stop(self) -> None:
        self._stop.set()
        if self._reader:
            self._reader.join(timeout=2.0)
        if self._group_frame_hub:
            self._group_frame_hub.join(timeout=2.0)
        if self._yolo_worker:
            self._yolo_worker.join(timeout=2.0)
        if self._ocr_worker:
            self._ocr_worker.join(timeout=2.0)
        if self._ocr_recognizer is not None:
            try:
                close_fn = getattr(self._ocr_recognizer, 'close', None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                _log.exception('Failed to close OCR recognizer')
            self._ocr_recognizer = None
        if self._visual_worker:
            self._visual_worker.join(timeout=2.0)
        if self._video_worker:
            self._video_worker.join(timeout=2.0)
            self._video_worker.shutdown_finalize()
        if self._single_video_worker:
            self._single_video_worker.join(timeout=2.0)
            self._single_video_worker.shutdown_finalize()
        for pipeline in self._per_camera_pipelines:
            pipeline.join(timeout=2.0)
        self._stop_media_sample_worker()
        
        # Final flush
        for pipeline in self._per_camera_pipelines:
            pipeline.flush_shutdown_logs()
        if self._reid_manager is not None:
            self._reid_manager.flush_all()
        if self._boat_tracker:
            self._boat_tracker.flush_shutdown_logs()
            
        self._reader = self._yolo_worker = self._ocr_worker = self._video_worker = None
        self._visual_worker = None
        self._single_video_worker = None
        self._group_frame_hub = None
        self._per_camera_pipelines = []
        self._reid_manager = None
        self._seam_anchor_verifier = None
        self._bg_registry = None
        self._runtime_cache = None
        self._vector_store = None
        self._identity_fusion = None
        self._visual_extractor = None
        self._active_group_id = None
        pipeline_preview.clear()
        self._gpu_status = None
        _log.info("Pipeline stopped")

    @property
    def gpu_status(self) -> dict[str, Any] | None:
        return self._gpu_status

    @property
    def active_detect_scale(self) -> float:
        """Tỉ lệ frame đưa vào detector đang chạy (1.0 = nguyên frame)."""
        return float(getattr(self, '_active_detect_scale', settings.DETECT_SCALE))

    def test_video_sync(
        self,
        source: str,
        enable_ocr: bool = True,
        save_to_db: bool = True,
    ) -> list[dict]:
        """
        Process a video file synchronously and return all detections.
        Used for testing and batch processing.
        """
        import cv2
        results = []
        
        # Load detector if not loaded
        if self._detector is None:
            self._detector, _ = load_yolo_detector(
                settings.MODEL_PATH, 
                settings.DEVICE, 
                settings.CONF, 
                [8]
            )

        def on_removed_test(tb, hist):
            if save_to_db:
                db = SessionLocal()
                try:
                    self._persist_track_removed(db, tb, hist)
                finally:
                    db.close()

            vote_summary = {}
            for sid, conf in hist:
                if sid not in vote_summary:
                    vote_summary[sid] = {"count": 0, "total_conf": 0.0}
                vote_summary[sid]["count"] += 1
                vote_summary[sid]["total_conf"] += conf
            
            voted_id = None
            if vote_summary:
                voted_id = max(vote_summary, key=lambda k: vote_summary[k]["total_conf"])

            results.append({
                "track_id": tb.track_id,
                "voted_ship_id": voted_id,
                "confidence": float(tb.conf),
                "first_seen": datetime.datetime.fromtimestamp(
                    tb.first_seen_ts, tz=datetime.timezone.utc
                ).isoformat(),
                "last_seen": datetime.datetime.fromtimestamp(
                    tb.last_seen_ts, tz=datetime.timezone.utc
                ).isoformat(),
                "ocr_attempts": len(hist),
                "vote_summary": vote_summary
            })

        tracker = BoatTracker(
            min_hits=1,
            max_tentative_misses=1,
            max_lost_frames=1,
            iou_threshold=settings.TRACK_IOU_THRESHOLD,
            reid_window_sec=settings.TRACK_REID_WINDOW_SEC,
            reid_max_centroid_dist=settings.TRACK_REID_MAX_DIST,
            on_track_removed=on_removed_test,
            min_confirm_sec=float(settings.TRACK_MIN_CONFIRM_SEC),
            max_tentative_sec=float(settings.TRACK_MAX_TENTATIVE_SEC),
            max_lost_sec=float(settings.TRACK_MAX_LOST_SEC),
        )
        ocr_interval_sec = float(settings.OCR_INTERVAL_SEC)
        last_ocr_ts = 0.0

        recognizer = create_ship_id_recognizer(rule_engine=get_rule_engine()) if enable_ocr else None
        
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise Exception(f"Could not open video source: {source}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            if frame_count % 100 == 0:
                print(f"Test API: Processed {frame_count} frames...", flush=True)
            if total_frames > 0 and frame_count >= total_frames:
                break
            
            now = time.time()
            
            # YOLO Detection
            boxes_list, det_confs = self._detector.predict_boxes(frame)
            tracked_boats = tracker.update(boxes_list, det_confs, ts=now)
            
            # OCR if enabled
            if enable_ocr and recognizer and (now - last_ocr_ts >= ocr_interval_sec):
                last_ocr_ts = now
                confirmed = [tb for tb in tracked_boats if tb.state == "CONFIRMED"]
                for tb in confirmed:
                    h, w = frame.shape[:2]
                    from app.utils.ai.pipeline_utils import clamp_box
                    x1, y1, x2, y2 = clamp_box(tb.box, w, h)
                    crop = frame[y1:y2, x1:x2]
                    if crop.size > 0:
                        ocr_res = recognizer.recognize_bgr(crop)
                        if ocr_res:
                            tracker.add_ocr_vote(tb.track_id, ocr_res[0]["id"], float(ocr_res[0]["confidence"]))

        cap.release()
        print(
            f"Test API finished: processed {frame_count}/{total_frames if total_frames > 0 else 'unknown'} frames.",
            flush=True,
        )
        tracker.flush_shutdown_logs()
        return results

    def _min_berth_duration_sec(self, db: Session) -> float:
        """Min neo-đậu dwell (giây) để track được lưu detection. Đọc live từ
        port_configs (key track_min_berth_duration_sec), fallback settings."""
        try:
            row = port_config_repo.get_by_key(db, 'track_min_berth_duration_sec')
            raw = str(row.value) if row is not None and row.value is not None else ''
        except Exception:
            raw = ''
        return self._to_float(
            raw,
            float(getattr(settings, 'TRACK_MIN_BERTH_DURATION_SEC', 0.0)),
        )

    def _camera_has_boundary(self, camera_id: int) -> bool:
        """True when camera has active boundary config with a valid berth_zone polygon."""
        if camera_id <= 0:
            return False
        from app.services.ai.boundary_crossing import BoundaryConfig

        for pipeline in self._per_camera_pipelines:
            if int(pipeline.config.camera_id) != int(camera_id):
                continue
            if pipeline._boundary_tracker is None:
                return False
            return BoundaryConfig.from_dict(pipeline.config.boundary_lines) is not None
        return False

    def update_camera_boundary_lines(self, camera_id: int, payload: dict | None) -> None:
        camera_key = int(camera_id)
        if self._group_frame_hub is not None:
            self._group_frame_hub.update_boundary_lines(camera_key, payload)
        for pipeline in self._per_camera_pipelines:
            if int(pipeline.config.camera_id) == camera_key:
                pipeline.update_boundary_lines(payload)
                break

    def update_camera_detection_settings(self, camera_id: int, payload: dict | None) -> None:
        camera_key = int(camera_id)
        for pipeline in self._per_camera_pipelines:
            if int(pipeline.config.camera_id) == camera_key:
                pipeline.update_detection_settings(payload)
                break


pipeline_service = PipelineService()

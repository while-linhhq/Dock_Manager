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

import cv2
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
from app.services.storage.minio_service import (
    copy_object_same_bucket,
    parse_minio_uri,
    put_bytes,
    put_file,
    remove_object,
)

from app.utils.ai.gpu_bootstrap import init_windows_cuda_path
from app.services.ai.background_model import BackgroundModelConfig, BackgroundModelRegistry
from app.services.ai.boat_tracker import BoatTracker, TrackState
from app.services.ai.cross_camera_reid import CrossCameraReIdManager
from app.services.ai.embedding_extractor import EmbeddingExtractor
from app.services.ai.frame_reader import FrameReaderThread
from app.services.ai.group_frame_hub import GroupFrameHub
from app.services.ai.ocr_worker import OcrWorkerThread
from app.services.ai.per_camera_pipeline import PerCameraPipeline, PerCameraPipelineConfig
from app.services.ai.seam_anchor_verifier import SeamAnchorConfig, SeamAnchorVerifier
from app.utils.ai.ship_id_recognizer import ShipIdRecognizer
from app.services.ai.track_media_collector import TrackMediaCollector
from app.services.ai.track_video_registry import RecordedVideo, TrackVideoRegistry
from app.services.ai.video_recorder import VideoRecorderThread
from app.utils.ai.gpu_probe import log_gpu_runtime_status
from app.utils.ai.yolo_detector import load_yolo_detector
from app.services.ai.yolo_worker import YoloWorkerThread
from app.services import pipeline_preview
from app.utils.ai.pipeline_utils import put_queue_drop_oldest

init_windows_cuda_path("pre")


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
    return f'minio://{bucket}/{object_key}'


def _upload_bytes_to_minio(*, data: bytes, object_key: str, content_type: str) -> str:
    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or '').strip() or 'media'
    put_bytes(
        data=data,
        bucket=bucket,
        object_key=object_key,
        content_type=content_type,
    )
    return f'minio://{bucket}/{object_key}'


class PipelineService:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._reader: FrameReaderThread | None = None
        self._group_frame_hub: GroupFrameHub | None = None
        self._yolo_worker: YoloWorkerThread | None = None
        self._ocr_worker: OcrWorkerThread | None = None
        self._video_worker: VideoRecorderThread | None = None
        self._single_video_worker: VideoRecorderThread | None = None
        self._per_camera_pipelines: list[PerCameraPipeline] = []
        self._reid_manager: CrossCameraReIdManager | None = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=5)
        self._result_queue: queue.Queue = queue.Queue(maxsize=10)
        self._ocr_queue: queue.Queue = queue.Queue(maxsize=10)
        self._video_queue: queue.Queue = queue.Queue(maxsize=30)
        self._single_video_queue: queue.Queue = queue.Queue(maxsize=30)
        self.ocr_cache: dict[str, Any] = {}
        self.ocr_lock = threading.Lock()
        self._runtime_media_base = _SERVER_ROOT / 'app' / 'data-docker' / 'runtime-media'
        self._media_collector = TrackMediaCollector()
        self._video_registry = TrackVideoRegistry()
        self._latest_fused_lock = threading.Lock()
        self._latest_fused_bgr: Any = None
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

    @staticmethod
    def _configure_dashboard_preview(runtime_cfg: dict[str, Any]) -> None:
        pipeline_preview.set_target_fps(float(runtime_cfg['record_fps']))
        pipeline_preview.set_max_width(int(getattr(settings, 'PREVIEW_MAX_WIDTH', 1280)))

    def _reset_runtime_queues(self) -> None:
        self._frame_queue = queue.Queue(maxsize=5)
        self._result_queue = queue.Queue(maxsize=10)
        self._ocr_queue = queue.Queue(maxsize=10)
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
            'min_hits': runtime_cfg['track_min_hits'],
            'max_tentative_misses': runtime_cfg['track_max_tentative_misses'],
            'max_lost_frames': runtime_cfg['track_max_lost_frames'],
            'iou_threshold': runtime_cfg['track_iou_threshold'],
            'reid_window_sec': runtime_cfg['track_reid_window_sec'],
            'reid_max_centroid_dist': runtime_cfg['track_reid_max_dist'],
            'on_track_removed': on_track_removed,
            'min_confirm_sec': runtime_cfg.get('track_min_confirm_sec'),
            'max_tentative_sec': runtime_cfg.get('track_max_tentative_sec'),
            'max_lost_sec': runtime_cfg.get('track_max_lost_sec'),
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

        return {
            'model_path': _s('model_path', settings.MODEL_PATH),
            'device': _s('device', settings.DEVICE),
            'conf': self._to_float(cfg_map.get('conf', ''), float(settings.CONF)),
            'enable_ocr': self._to_bool(cfg_map.get('enable_ocr', ''), bool(settings.ENABLE_OCR)),
            'ocr_interval_frames': max(
                1,
                self._to_int(cfg_map.get('ocr_interval_frames', ''), int(settings.OCR_INTERVAL_FRAMES)),
            ),
            'ocr_interval_sec': self._optional_positive_float(
                cfg_map,
                'ocr_interval_sec',
                getattr(settings, 'OCR_INTERVAL_SEC', None),
            ),
            'track_min_confirm_sec': self._optional_positive_float(
                cfg_map,
                'track_min_confirm_sec',
                getattr(settings, 'TRACK_MIN_CONFIRM_SEC', None),
            ),
            'track_max_tentative_sec': self._optional_positive_float(
                cfg_map,
                'track_max_tentative_sec',
                getattr(settings, 'TRACK_MAX_TENTATIVE_SEC', None),
            ),
            'track_max_lost_sec': self._optional_positive_float(
                cfg_map,
                'track_max_lost_sec',
                getattr(settings, 'TRACK_MAX_LOST_SEC', None),
            ),
            'ocr_label_ttl_sec': self._to_float(
                cfg_map.get('ocr_label_ttl_sec', ''),
                float(settings.OCR_LABEL_TTL_SEC),
            ),
            'ocr_audit_enable': self._to_bool(
                cfg_map.get('ocr_audit_enable', ''),
                bool(settings.OCR_AUDIT_ENABLE),
            ),
            'track_min_hits': max(
                1,
                self._to_int(cfg_map.get('track_min_hits', ''), int(settings.TRACK_MIN_HITS)),
            ),
            'track_max_tentative_misses': max(
                1,
                self._to_int(
                    cfg_map.get('track_max_tentative_misses', ''),
                    int(settings.TRACK_MAX_TENTATIVE_MISSES),
                ),
            ),
            'track_max_lost_frames': max(
                1,
                self._to_int(cfg_map.get('track_max_lost_frames', ''), int(settings.TRACK_MAX_LOST_FRAMES)),
            ),
            'track_iou_threshold': self._to_float(
                cfg_map.get('track_iou_threshold', ''),
                float(settings.TRACK_IOU_THRESHOLD),
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
            'record_fps': (
                float(rf)
                if (rf := self._to_float(cfg_map.get('record_fps', ''), float(settings.RECORD_FPS))) > 0
                else float(settings.RECORD_FPS)
            ),
            'sync_tolerance_ms': max(
                0,
                self._to_int(cfg_map.get('sync_tolerance_ms', ''), 400),
            ),
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
            'clahe_clip_limit': self._to_float(
                cfg_map.get('clahe_clip_limit', ''),
                float(settings.CLAHE_CLIP_LIMIT),
            ),
            'clahe_tile_size': max(
                2,
                self._to_int(cfg_map.get('clahe_tile_size', ''), int(settings.CLAHE_TILE_SIZE)),
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
        }

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

    def get_latest_camera_frame(self, camera_id: int):
        if self._group_frame_hub is None:
            return None
        try:
            snapshot = self._group_frame_hub.frame_buffer.snapshot(copy_frames=True)
        except Exception:
            _log.exception('get_latest_camera_frame: snapshot failed')
            return None
        timed = snapshot.get(int(camera_id))
        return timed.frame if timed is not None else None

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
        for t in job.tracks:
            if getattr(t, 'state', None) != TrackState.CONFIRMED:
                continue
            tid = str(t.track_id)
            conf = float(t.conf)
            if job.update_fused:
                self._media_collector.update_fused_detection(tid, conf, frame)
            cam = int(job.camera_id if job.camera_id is not None else getattr(t, 'camera_id', None) or 0)
            self._media_collector.update_single_detection(tid, conf, cam, frame)

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
        fused = None
        with self._latest_fused_lock:
            if self._latest_fused_bgr is not None:
                fused = self._latest_fused_bgr.copy()
        self._media_collector.update_ocr(
            track_id,
            ocr_conf,
            ship_id,
            frame,
            fused if fused is not None else frame,
            camera_id,
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
                return f'minio://{ref.bucket}/{dest_key}'
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
            return f'minio://{ref.bucket}/{dest_key}'
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
            if snap is not None:
                cam_det = snap.single_best_camera_id if snap.single_best_camera_id is not None else 0
                cam_ocr = snap.single_best_ocr_camera_id if snap.single_best_ocr_camera_id is not None else 0
                uploads: list[tuple[bytes | None, str]] = [
                    (snap.fused_best_detection_jpeg, f'fused_best_detection_{safe_t}.jpg'),
                    (snap.fused_best_ocr_jpeg, f'fused_best_ocr_{safe_t}.jpg'),
                    (snap.single_best_detection_jpeg, f'single_best_detection_{cam_det}_{safe_t}.jpg'),
                    (snap.single_best_ocr_jpeg, f'single_best_ocr_{cam_ocr}_{safe_t}.jpg'),
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
            
            vote_summary = {}
            for sid, conf in hist:
                if sid not in vote_summary:
                    vote_summary[sid] = {"count": 0, "total_conf": 0.0}
                vote_summary[sid]["count"] += 1
                vote_summary[sid]["total_conf"] += conf

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
        except Exception:
            db.rollback()
            raise

        if det_id_for_invoice is not None:
            try:
                from app.services.detection_invoice_service import ensure_ai_invoice_for_detection

                ensure_ai_invoice_for_detection(det_id_for_invoice)
            except Exception:
                _log.exception(
                    'AI invoice creation failed for detection_id=%s',
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

        # Load detector if not loaded
        detector_sig = (
            runtime_cfg['model_path'],
            runtime_cfg['device'],
            float(runtime_cfg['conf']),
        )
        if self._detector is None or self._detector_signature != detector_sig:
            # COCO class id 8 = boat
            self._detector, _ = load_yolo_detector(
                runtime_cfg['model_path'],
                runtime_cfg['device'],
                runtime_cfg['conf'],
                [8],
            )
            self._detector_signature = detector_sig

        # Use settings for all params
        ocr_active = enable_ocr if enable_ocr is not None else runtime_cfg['enable_ocr']
        ocr_interval = runtime_cfg['ocr_interval_frames']
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
            self._ocr_queue, self._video_queue, self._stop, ocr_interval, ocr_active,
            ocr_interval_sec=runtime_cfg.get('ocr_interval_sec'),
            ocr_cache=self.ocr_cache, ocr_lock=self.ocr_lock, ocr_label_ttl=ocr_label_ttl,
            record_overlay_resize_scale=runtime_cfg['resize_scale'],
            enable_preview_stream=True,
            on_overlay_media_sample=self._recording_yolo_single_overlay,
        )

        if ocr_active:
            recognizer = ShipIdRecognizer()
            self._ocr_worker = OcrWorkerThread(
                recognizer, self._ocr_queue, self.ocr_cache, self.ocr_lock, self._stop,
                ocr_label_ttl, runtime_cfg['save_min_interval_sec'],
                boat_tracker=self._boat_tracker,
                runs_base=str(self._runtime_media_base / 'detect'),
                save_ocr_audit_frames=runtime_cfg['ocr_audit_save_frames'],
                on_image_captured=self._upload_captured_image,
                on_ocr_track_media=self._on_ocr_track_media,
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
        self._reid_manager = CrossCameraReIdManager(
            camera_order=camera_order,
            visual_threshold=runtime_cfg['reid_visual_threshold'],
            handoff_window_sec=runtime_cfg['reid_handoff_window_sec'],
            primary_zone_ratio=runtime_cfg['primary_zone_ratio'],
            edge_zone_ratio=runtime_cfg['edge_zone_ratio'],
            on_global_track_removed=combined_on_removed,
        )
        embedding_extractor = EmbeddingExtractor(
            model_path=runtime_cfg['reid_embedding_model_path'] or None,
            device=runtime_cfg['device'],
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
            recognizer = ShipIdRecognizer()
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
            )
            self._ocr_worker.start()

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
        )

        self._per_camera_pipelines = []
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
                ocr_interval_frames=runtime_cfg['ocr_interval_frames'],
                ocr_label_ttl_sec=runtime_cfg['ocr_label_ttl_sec'],
                save_min_interval_sec=runtime_cfg['save_min_interval_sec'],
                ocr_audit_save_frames=runtime_cfg['ocr_audit_save_frames'],
                resize_scale=runtime_cfg['resize_scale'],
                track_min_hits=runtime_cfg['track_min_hits'],
                track_max_tentative_misses=runtime_cfg['track_max_tentative_misses'],
                track_max_lost_frames=runtime_cfg['track_max_lost_frames'],
                track_iou_threshold=runtime_cfg['track_iou_threshold'],
                track_reid_window_sec=runtime_cfg['track_reid_window_sec'],
                track_reid_max_dist=runtime_cfg['track_reid_max_dist'],
                track_min_confirm_sec=runtime_cfg.get('track_min_confirm_sec'),
                track_max_tentative_sec=runtime_cfg.get('track_max_tentative_sec'),
                track_max_lost_sec=runtime_cfg.get('track_max_lost_sec'),
                ocr_interval_sec=runtime_cfg.get('ocr_interval_sec'),
                clahe_clip_limit=runtime_cfg['clahe_clip_limit'],
                clahe_tile_size=runtime_cfg['clahe_tile_size'],
                edge_zone_ratio=runtime_cfg['edge_zone_ratio'],
                enable_preview_stream=False,
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
                    input_frame_queue=self._group_frame_hub.queue_for_camera(camera_id),
                    shared_ocr_queue=self._ocr_queue if ocr_active else None,
                    single_camera_video_queue=single_cam_q,
                )
            )

        self._group_frame_hub.set_track_providers(
            [pipeline.tracker.all_active for pipeline in self._per_camera_pipelines]
        )
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

        detector_sig = (
            runtime_cfg['model_path'],
            runtime_cfg['device'],
            float(runtime_cfg['conf']),
        )
        if self._detector is None or self._detector_signature != detector_sig:
            self._detector, _ = load_yolo_detector(
                runtime_cfg['model_path'],
                runtime_cfg['device'],
                runtime_cfg['conf'],
                [8],
            )
            self._detector_signature = detector_sig

        ocr_active = enable_ocr if enable_ocr is not None else runtime_cfg['enable_ocr']
        ocr_interval = runtime_cfg['ocr_interval_frames']
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

        self._group_frame_hub = GroupFrameHub(
            group=group,
            enabled_members=enabled_members,
            runtime_cfg=runtime_cfg,
            stop_event=self._stop,
            video_queue=self._video_queue if runtime_cfg['record_enable'] else None,
            yolo_frame_queue=self._frame_queue,
            distribute_per_camera=False,
            on_fused_media_sample=self._recording_fused_media_sample,
        )
        self._group_frame_hub.set_track_providers([self._boat_tracker.confirmed_boats])
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
            ocr_interval,
            ocr_active,
            ocr_interval_sec=runtime_cfg.get('ocr_interval_sec'),
            ocr_cache=self.ocr_cache,
            ocr_lock=self.ocr_lock,
            ocr_label_ttl=ocr_label_ttl,
            record_overlay_resize_scale=runtime_cfg['resize_scale'],
            enable_preview_stream=False,
        )

        if ocr_active:
            recognizer = ShipIdRecognizer()
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
        self._single_video_worker = None
        self._group_frame_hub = None
        self._per_camera_pipelines = []
        self._reid_manager = None
        self._seam_anchor_verifier = None
        self._bg_registry = None
        self._active_group_id = None
        pipeline_preview.clear()
        self._gpu_status = None
        _log.info("Pipeline stopped")

    @property
    def gpu_status(self) -> dict[str, Any] | None:
        return self._gpu_status

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
            min_hits=settings.TRACK_MIN_HITS,
            max_tentative_misses=settings.TRACK_MAX_TENTATIVE_MISSES,
            max_lost_frames=settings.TRACK_MAX_LOST_FRAMES,
            iou_threshold=settings.TRACK_IOU_THRESHOLD,
            reid_window_sec=settings.TRACK_REID_WINDOW_SEC,
            reid_max_centroid_dist=settings.TRACK_REID_MAX_DIST,
            on_track_removed=on_removed_test
        )

        recognizer = ShipIdRecognizer() if enable_ocr else None
        
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
            if enable_ocr and recognizer and (frame_count % settings.OCR_INTERVAL_FRAMES == 0):
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

pipeline_service = PipelineService()

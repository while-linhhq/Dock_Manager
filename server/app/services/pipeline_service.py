from __future__ import annotations
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any
import datetime
import mimetypes

import cv2
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.models.detection_media import DetectionMedia
from app.repositories import vessel_repo, detection_repo, order_repo, port_log_repo
from app.repositories.detection_media_repository import detection_media_repo
from app.repositories.port_config_repository import port_config_repo
from app.schemas import VesselCreate, DetectionCreate, PortLogCreate
from app.core.config import settings
from app.services.storage.minio_service import put_bytes, put_file

from app.utils.ai.gpu_bootstrap import init_windows_cuda_path
from app.services.ai.boat_tracker import BoatTracker
from app.services.ai.frame_reader import FrameReaderThread
from app.services.ai.frame_fusion import FrameFuser, FrameFusionWorker, build_fusion_config_from_group
from app.services.ai.frame_synchronizer import FrameSynchronizer
from app.services.ai.multi_frame_reader import CameraSource, LatestFrameBuffer, MultiFrameReaderThread
from app.services.ai.ocr_worker import OcrWorkerThread
from app.utils.ai.ship_id_recognizer import ShipIdRecognizer
from app.services.ai.video_recorder import VideoRecorderThread
from app.utils.ai.yolo_detector import load_yolo_detector
from app.services.ai.yolo_worker import YoloWorkerThread
from app.services import pipeline_preview

init_windows_cuda_path("pre")

_log = logging.getLogger("app.services.pipeline")

MediaInfo = dict[str, Any]

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
    p = Path(str(local_path))
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
        self._multi_readers: list[MultiFrameReaderThread] = []
        self._fusion_worker: FrameFusionWorker | None = None
        self._yolo_worker: YoloWorkerThread | None = None
        self._ocr_worker: OcrWorkerThread | None = None
        self._video_worker: VideoRecorderThread | None = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=5)
        self._result_queue: queue.Queue = queue.Queue(maxsize=10)
        self._ocr_queue: queue.Queue = queue.Queue(maxsize=10)
        self._video_queue: queue.Queue = queue.Queue(maxsize=30)
        self.ocr_cache: dict[str, Any] = {}
        self.ocr_lock = threading.Lock()
        self._runtime_media_base = Path('app/data-docker/runtime-media')
        self._track_snapshot_media: dict[str, MediaInfo] = {}
        self._video_media: list[MediaInfo] = []
        self._media_lock = threading.Lock()
        self._detector: Any = None
        self._detector_signature: tuple[str, str, float] | None = None
        self._boat_tracker: BoatTracker = BoatTracker()
        self._db: Session | None = None

    def _reset_runtime_queues(self) -> None:
        self._frame_queue = queue.Queue(maxsize=5)
        self._result_queue = queue.Queue(maxsize=10)
        self._ocr_queue = queue.Queue(maxsize=10)
        self._video_queue = queue.Queue(maxsize=30)

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
            'record_fps': max(1, self._to_int(cfg_map.get('record_fps', ''), int(settings.RECORD_FPS))),
            'sync_tolerance_ms': max(
                0,
                self._to_int(cfg_map.get('sync_tolerance_ms', ''), 400),
            ),
        }

    @property
    def is_running(self) -> bool:
        single_running = self._reader is not None and self._reader.is_alive()
        fusion_running = self._fusion_worker is not None and self._fusion_worker.is_alive()
        return single_running or fusion_running

    def _upload_captured_image(
        self,
        track_id: str | None,
        media_type: str,
        image_bgr,
        filename: str,
        remember_for_detection: bool,
    ) -> None:
        ok, encoded = cv2.imencode('.jpg', image_bgr)
        if not ok:
            _log.warning('Failed to encode captured %s image for track_id=%s', media_type, track_id)
            return

        day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        track_segment = _safe_key_segment(track_id or 'untracked')
        object_key = _make_minio_key(
            'detections',
            'staging',
            day,
            track_segment,
            media_type,
            filename,
        )
        try:
            uri = _upload_bytes_to_minio(
                data=encoded.tobytes(),
                object_key=object_key,
                content_type='image/jpeg',
            )
        except Exception:
            _log.exception('Failed to upload captured %s image to MinIO', media_type)
            return

        if remember_for_detection and track_id:
            with self._media_lock:
                self._track_snapshot_media[str(track_id)] = {
                    'uri': uri,
                    'size': int(len(encoded)),
                    'created_at': time.time(),
                }

    def _upload_recorded_video(self, local_path: str) -> None:
        path = Path(local_path)
        if not path.exists():
            return

        day = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        object_key = _make_minio_key('detections', 'staging', day, 'videos', path.name)
        try:
            uri = _upload_file_to_minio(local_path=str(path), object_key=object_key)
            size = path.stat().st_size
            with self._media_lock:
                self._video_media.append(
                    {
                        'uri': uri,
                        'size': size,
                        'created_at': time.time(),
                    }
                )
                self._video_media = self._video_media[-20:]
        except Exception:
            _log.exception('Failed to upload recorded video to MinIO: %s', str(path))
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                _log.warning('Failed to remove runtime video temp file: %s', str(path))

    def _pop_track_snapshot_media(self, track_id: str) -> MediaInfo | None:
        with self._media_lock:
            return self._track_snapshot_media.pop(str(track_id), None)

    def _latest_video_media(self) -> MediaInfo | None:
        with self._media_lock:
            if not self._video_media:
                return None
            return dict(self._video_media[-1])

    def _persist_track_removed(self, db: Session, tb: Any, hist: list[tuple[str, float]]) -> None:
        """Persist finalized track to DB tables: vessel, detection, and port_log."""
        det_id_for_invoice: int | None = None
        try:
            ship_id = (tb.ship_id or "UNKNOWN").strip().upper()
            start_dt_utc = datetime.datetime.fromtimestamp(tb.first_seen_ts, tz=datetime.timezone.utc)
            end_dt_utc = datetime.datetime.fromtimestamp(tb.last_seen_ts, tz=datetime.timezone.utc)
            # 1. Tìm hoặc tạo Vessel
            vessel = vessel_repo.get_by_ship_id_normalized(db, ship_id)
            if not vessel:
                vessel = vessel_repo.create(db, VesselCreate(ship_id=ship_id))
            else:
                vessel_repo.update_last_seen(db, vessel.id)

            snapshot_media = self._pop_track_snapshot_media(str(tb.track_id))
            video_media = self._latest_video_media()
            snapshot_uri = snapshot_media['uri'] if snapshot_media else None
            video_uri = video_media['uri'] if video_media else None

            # 2. Lưu Detection record
            try:
                det = detection_repo.create(
                    db,
                    DetectionCreate(
                        vessel_id=vessel.id,
                        track_id=tb.track_id,
                        start_time=start_dt_utc,
                        end_time=end_dt_utc,
                        video_path=video_uri,
                        audit_image_path=snapshot_uri,
                        ocr_results=[{'id': h[0], 'conf': h[1]} for h in hist],
                        confidence=tb.conf,
                    ),
                )
            except IntegrityError:
                # Defense-in-depth: if track_id collides (e.g., after restart), reuse the existing detection
                db.rollback()
                det = detection_repo.get_by_track_id(db, str(tb.track_id))
                if det is None:
                    raise
            det_id_for_invoice = det.id
            # 2b. Attach media rows. Prefer MinIO URIs (presigned at read time) for FE playback.
            if snapshot_uri:
                file_path = snapshot_uri
                exists = (
                    db.query(DetectionMedia)
                    .filter(
                        DetectionMedia.detection_id == det.id,
                        DetectionMedia.media_type == 'image',
                        DetectionMedia.file_path == file_path,
                    )
                    .first()
                    is not None
                )
                if not exists:
                    detection_media_repo.create(
                        db,
                        {
                            'detection_id': det.id,
                            'media_type': 'image',
                            'file_path': file_path,
                            'file_size': snapshot_media.get('size') if snapshot_media else None,
                        },
                    )
            if video_uri:
                file_path = video_uri
                exists = (
                    db.query(DetectionMedia)
                    .filter(
                        DetectionMedia.detection_id == det.id,
                        DetectionMedia.media_type == 'video',
                        DetectionMedia.file_path == file_path,
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
                            'file_path': file_path,
                            'file_size': video_media.get('size') if video_media else None,
                        },
                    )

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
            min_hits=runtime_cfg['track_min_hits'],
            max_tentative_misses=runtime_cfg['track_max_tentative_misses'],
            max_lost_frames=runtime_cfg['track_max_lost_frames'],
            iou_threshold=runtime_cfg['track_iou_threshold'],
            reid_window_sec=runtime_cfg['track_reid_window_sec'],
            reid_max_centroid_dist=runtime_cfg['track_reid_max_dist'],
            on_track_removed=combined_on_removed
        )

        # Đồng bộ FPS: dùng record_fps làm nhịp đọc frame → nhịp infer → nhịp record/preview.
        self._reader = FrameReaderThread(
            source,
            self._frame_queue,
            self._stop,
            target_fps=runtime_cfg['record_fps'],
        )
        try:
            pipeline_preview.set_target_fps(runtime_cfg['record_fps'])
        except Exception:
            pass
        self._yolo_worker = YoloWorkerThread(
            self._detector, self._boat_tracker, self._frame_queue, self._result_queue,
            self._ocr_queue, self._video_queue, self._stop, ocr_interval, ocr_active,
            ocr_cache=self.ocr_cache, ocr_lock=self.ocr_lock, ocr_label_ttl=ocr_label_ttl,
            record_overlay_resize_scale=runtime_cfg['resize_scale'],
            enable_preview_stream=True,
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

    def start_group(self, group: Any, enable_ocr: bool | None = None) -> None:
        if self.is_running:
            _log.warning('Pipeline is already running')
            return

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

        self._boat_tracker = BoatTracker(
            min_hits=runtime_cfg['track_min_hits'],
            max_tentative_misses=runtime_cfg['track_max_tentative_misses'],
            max_lost_frames=runtime_cfg['track_max_lost_frames'],
            iou_threshold=runtime_cfg['track_iou_threshold'],
            reid_window_sec=runtime_cfg['track_reid_window_sec'],
            reid_max_centroid_dist=runtime_cfg['track_reid_max_dist'],
            on_track_removed=combined_on_removed,
        )

        frame_buffer = LatestFrameBuffer()
        camera_sources = [
            CameraSource(
                camera_id=int(member.camera_id),
                source=member.camera.rtsp_url,
            )
            for member in enabled_members
        ]
        self._multi_readers = [
            MultiFrameReaderThread(
                source,
                frame_buffer,
                self._stop,
                target_fps=runtime_cfg['record_fps'],
            )
            for source in camera_sources
        ]
        synchronizer = FrameSynchronizer(
            frame_buffer,
            [source.camera_id for source in camera_sources],
            tolerance_ms=runtime_cfg['sync_tolerance_ms'],
        )
        self._fusion_worker = FrameFusionWorker(
            synchronizer,
            FrameFuser(build_fusion_config_from_group(group)),
            self._frame_queue,
            self._stop,
            target_fps=runtime_cfg['record_fps'],
        )
        try:
            pipeline_preview.set_target_fps(runtime_cfg['record_fps'])
        except Exception:
            pass

        self._yolo_worker = YoloWorkerThread(
            self._detector,
            self._boat_tracker,
            self._frame_queue,
            self._result_queue,
            self._ocr_queue,
            self._video_queue,
            self._stop,
            ocr_interval,
            ocr_active,
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

        for reader in self._multi_readers:
            reader.start()
        self._fusion_worker.start()
        self._yolo_worker.start()
        if self._ocr_worker:
            self._ocr_worker.start()

        _log.info(
            'Pipeline started with camera_group_id=%s cameras=%s',
            group.id,
            [source.camera_id for source in camera_sources],
        )

    def stop(self) -> None:
        self._stop.set()
        if self._reader:
            self._reader.join(timeout=2.0)
        for reader in self._multi_readers:
            reader.join(timeout=2.0)
        if self._fusion_worker:
            self._fusion_worker.join(timeout=2.0)
        if self._yolo_worker:
            self._yolo_worker.join(timeout=2.0)
        if self._ocr_worker:
            self._ocr_worker.join(timeout=2.0)
        if self._video_worker:
            self._video_worker.join(timeout=2.0)
        
        # Final flush
        if self._boat_tracker:
            self._boat_tracker.flush_shutdown_logs()
            
        self._reader = self._yolo_worker = self._ocr_worker = self._video_worker = None
        self._fusion_worker = None
        self._multi_readers = []
        pipeline_preview.clear()
        _log.info("Pipeline stopped")

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

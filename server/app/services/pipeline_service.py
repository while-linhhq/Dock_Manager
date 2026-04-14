from __future__ import annotations
import logging
import os
import queue
import shutil
import threading
import time
from pathlib import Path
from typing import Any
import datetime
import mimetypes

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.session import SessionLocal
from app.models.detection_media import DetectionMedia
from app.repositories import vessel_repo, detection_repo, order_repo, port_log_repo
from app.repositories.detection_media_repository import detection_media_repo
from app.repositories.port_config_repository import port_config_repo
from app.schemas import VesselCreate, DetectionCreate, PortLogCreate
from app.core.config import settings
from app.services.storage.minio_service import put_file

from app.utils.ai.gpu_bootstrap import init_windows_cuda_path
from app.services.ai.boat_tracker import BoatTracker
from app.services.ai.frame_reader import FrameReaderThread
from app.services.ai.ocr_worker import OcrWorkerThread, _build_track_removed_logger
from app.utils.ai.ship_id_recognizer import ShipIdRecognizer
from app.services.ai.video_recorder import VideoRecorderThread
from app.utils.ai.yolo_detector import load_yolo_detector
from app.services.ai.yolo_worker import YoloWorkerThread
from app.services import pipeline_preview
from app.utils.media.faststart_mp4 import has_moov_atom

init_windows_cuda_path("pre")

_log = logging.getLogger("app.services.pipeline")

def _guess_content_type(p: Path) -> str:
    ct, _ = mimetypes.guess_type(str(p))
    return ct or 'application/octet-stream'


def _make_minio_key(detection_id: int, media_type: str, filename: str) -> str:
    prefix = str(getattr(settings, 'MINIO_MEDIA_PREFIX', '') or '').strip().strip('/')
    safe_media = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in (media_type or 'media'))
    safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in filename)
    core = f'detections/{int(detection_id)}/{safe_media}/{safe_name}'
    return f'{prefix}/{core}' if prefix else core


def _maybe_upload_to_minio(*, local_path: str | None, detection_id: int, media_type: str) -> str | None:
    """
    Best-effort upload to MinIO and return minio:// URI.
    Falls back to local path if MinIO is disabled or upload fails.
    """
    if not local_path:
        return None
    if not bool(getattr(settings, 'MINIO_UPLOAD_ON_DETECT', True)):
        return None
    p = Path(str(local_path))
    if not p.exists():
        return None
    bucket = str(getattr(settings, 'MINIO_BUCKET', '') or '').strip() or 'media'
    key = _make_minio_key(detection_id, media_type, p.name)
    try:
        put_file(
            local_path=str(p),
            bucket=bucket,
            object_key=key,
            content_type=_guess_content_type(p),
        )
        return f'minio://{bucket}/{key}'
    except Exception:
        _log.exception('MinIO upload failed (media_type=%s, path=%s)', media_type, str(p))
        return None


def _safe_ship_segment(ship_id: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in ship_id.strip().upper())
    return cleaned or 'UNKNOWN'


def _find_latest_track_frame(runs_base: Path, event_dt_utc: datetime.datetime, track_id: str) -> Path | None:
    day = event_dt_utc.date().isoformat()
    cap_dirs = [
        runs_base / 'cap' / day,
        runs_base / 'detect' / 'cap' / day,  # legacy path
    ]
    candidates: list[Path] = []
    for cap_dir in cap_dirs:
        if not cap_dir.exists():
            continue
        candidates.extend(list(cap_dir.glob(f'*_{track_id}_frame.jpg')))
        candidates.extend(list(cap_dir.glob(f'*_{track_id}_noocr_frame.jpg')))
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _find_latest_video_for_event(runs_base: Path, event_dt_utc: datetime.datetime) -> Path | None:
    day = event_dt_utc.date().isoformat()
    videos_dirs = [
        runs_base / 'videos' / day,
        runs_base / 'detect' / 'videos' / day,  # legacy path
    ]
    candidates: list[Path] = []
    for videos_dir in videos_dirs:
        if not videos_dir.exists():
            continue
        candidates.extend(list(videos_dir.glob('*.mp4')))
    # Avoid tiny/incomplete files that can't be played
    def _is_playable(p: Path) -> bool:
        try:
            if not p.exists():
                return False
            if p.stat().st_size < 1_000_000:  # 1MB
                return False
            if not has_moov_atom(p):
                return False
            return True
        except Exception:
            return False

    candidates = [p for p in candidates if _is_playable(p)]
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _copy_snapshot_to_ship_day(
    runs_base: Path,
    ship_id: str,
    event_dt_utc: datetime.datetime,
    track_id: str,
    source_frame_path: Path | None,
) -> str | None:
    if source_frame_path is None or not source_frame_path.exists():
        return None
    day = event_dt_utc.date().isoformat()
    target_dir = runs_base / 'by-ship' / _safe_ship_segment(ship_id) / day / 'snapshots'
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f'{track_id}_{source_frame_path.name}'
    shutil.copy2(source_frame_path, target_file)
    return str(target_file).replace('\\', '/')


def _copy_video_to_ship_day(
    runs_base: Path,
    ship_id: str,
    event_dt_utc: datetime.datetime,
    track_id: str,
    source_video_path: Path | None,
) -> str | None:
    if source_video_path is None or not source_video_path.exists():
        return None
    day = event_dt_utc.date().isoformat()
    target_dir = runs_base / 'by-ship' / _safe_ship_segment(ship_id) / day / 'videos'
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f'{track_id}_{source_video_path.name}'
    if not target_file.exists():
        shutil.copy2(source_video_path, target_file)
    return str(target_file).replace('\\', '/')

class PipelineService:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._reader: FrameReaderThread | None = None
        self._yolo_worker: YoloWorkerThread | None = None
        self._ocr_worker: OcrWorkerThread | None = None
        self._video_worker: VideoRecorderThread | None = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=30)
        self._result_queue: queue.Queue = queue.Queue(maxsize=30)
        self._ocr_queue: queue.Queue = queue.Queue(maxsize=30)
        self._video_queue: queue.Queue = queue.Queue(maxsize=60)
        self.ocr_cache: dict[str, Any] = {}
        self.ocr_lock = threading.Lock()
        self._runs_base = Path("runs")
        self._detector: Any = None
        self._detector_signature: tuple[str, str, float] | None = None
        self._boat_tracker: BoatTracker = BoatTracker()
        self._db: Session | None = None

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
        }

    @property
    def is_running(self) -> bool:
        return self._reader is not None and self._reader.is_alive()

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

            source_frame = _find_latest_track_frame(self._runs_base, end_dt_utc, str(tb.track_id))
            source_video = _find_latest_video_for_event(self._runs_base, end_dt_utc)
            snapshot_path = _copy_snapshot_to_ship_day(
                self._runs_base,
                ship_id=ship_id,
                event_dt_utc=end_dt_utc,
                track_id=str(tb.track_id),
                source_frame_path=source_frame,
            )
            verify_video_path = _copy_video_to_ship_day(
                self._runs_base,
                ship_id=ship_id,
                event_dt_utc=end_dt_utc,
                track_id=str(tb.track_id),
                source_video_path=source_video,
            )

            # 2. Lưu Detection record
            try:
                det = detection_repo.create(
                    db,
                    DetectionCreate(
                        vessel_id=vessel.id,
                        track_id=tb.track_id,
                        start_time=start_dt_utc,
                        end_time=end_dt_utc,
                        video_path=verify_video_path,
                        audit_image_path=snapshot_path,
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
            if snapshot_path:
                minio_uri = _maybe_upload_to_minio(
                    local_path=snapshot_path,
                    detection_id=det.id,
                    media_type='image',
                )
                file_path = minio_uri or snapshot_path
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
                    try:
                        size = Path(snapshot_path).stat().st_size
                    except Exception:
                        size = None
                    detection_media_repo.create(
                        db,
                        {
                            'detection_id': det.id,
                            'media_type': 'image',
                            'file_path': file_path,
                            'file_size': size,
                        },
                    )
            if verify_video_path:
                minio_uri = _maybe_upload_to_minio(
                    local_path=verify_video_path,
                    detection_id=det.id,
                    media_type='video',
                )
                file_path = minio_uri or verify_video_path
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
                    try:
                        size = Path(verify_video_path).stat().st_size
                    except Exception:
                        size = None
                    detection_media_repo.create(
                        db,
                        {
                            'detection_id': det.id,
                            'media_type': 'video',
                            'file_path': file_path,
                            'file_size': size,
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
        
        # Combine DB callback with Audit Logger callback
        db_cb = self._on_track_removed_db
        audit_cb = _build_track_removed_logger(
            str(self._runs_base), 
            runtime_cfg['ocr_audit_enable'],
            log_dedup_window_sec=0.0 # Can add to settings if needed
        )
        
        def combined_on_removed(tb, hist):
            db_cb(tb, hist)
            if audit_cb:
                audit_cb(tb, hist)

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
                boat_tracker=self._boat_tracker, runs_base=str(self._runs_base),
                save_ocr_audit_frames=runtime_cfg['ocr_audit_save_frames']
            )

        if runtime_cfg['record_enable']:
            self._video_worker = VideoRecorderThread(
                self._video_queue, self._stop,
                max_duration_sec=runtime_cfg['record_max_duration_min'] * 60,
                gap_sec=runtime_cfg['record_no_boat_gap_sec'],
                record_fps=runtime_cfg['record_fps'],
                runs_base=str(self._runs_base)
            )
            self._video_worker.start()

        self._reader.start()
        self._yolo_worker.start()
        if self._ocr_worker:
            self._ocr_worker.start()
            
        _log.info(f"Pipeline started with source: {source}")

    def stop(self) -> None:
        self._stop.set()
        if self._reader: self._reader.join(timeout=2.0)
        if self._yolo_worker: self._yolo_worker.join(timeout=2.0)
        if self._ocr_worker: self._ocr_worker.join(timeout=2.0)
        if self._video_worker: self._video_worker.join(timeout=2.0)
        
        # Final flush
        if self._boat_tracker:
            self._boat_tracker.flush_shutdown_logs()
            
        self._reader = self._yolo_worker = self._ocr_worker = self._video_worker = None
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

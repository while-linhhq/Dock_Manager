from __future__ import annotations
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any
import datetime

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.repositories import vessel_repo, detection_repo, order_repo, port_log_repo
from app.schemas import VesselCreate, DetectionCreate, PortLogCreate
from app.core.config import settings

from app.utils.ai.gpu_bootstrap import init_windows_cuda_path
from app.services.ai.boat_tracker import BoatTracker
from app.services.ai.frame_reader import FrameReaderThread
from app.services.ai.ocr_worker import OcrWorkerThread, _build_track_removed_logger
from app.utils.ai.ship_id_recognizer import ShipIdRecognizer
from app.services.ai.video_recorder import VideoRecorderThread
from app.utils.ai.yolo_detector import load_yolo_detector
from app.services.ai.yolo_worker import YoloWorkerThread

init_windows_cuda_path("pre")

_log = logging.getLogger("app.services.pipeline")

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
        self._boat_tracker: BoatTracker = BoatTracker()
        self._db: Session | None = None

    @property
    def is_running(self) -> bool:
        return self._reader is not None and self._reader.is_alive()

    def _persist_track_removed(self, db: Session, tb: Any, hist: list[tuple[str, float]]) -> None:
        """Persist finalized track to DB tables: vessel, detection, and port_log."""
        try:
            ship_id = tb.ship_id or "UNKNOWN"
            # 1. Tìm hoặc tạo Vessel
            vessel = vessel_repo.get_by_ship_id(db, ship_id)
            if not vessel:
                vessel = vessel_repo.create(db, VesselCreate(ship_id=ship_id))
            else:
                vessel_repo.update_last_seen(db, vessel.id)

            # 2. Lưu Detection record
            detection_repo.create(db, DetectionCreate(
                vessel_id=vessel.id,
                track_id=tb.track_id,
                start_time=datetime.datetime.fromtimestamp(tb.first_seen_ts),
                end_time=datetime.datetime.fromtimestamp(tb.last_seen_ts),
                ocr_results=[{"id": h[0], "conf": h[1]} for h in hist],
                confidence=tb.conf
            ))

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
                logged_at=datetime.datetime.utcnow(),
                track_id=tb.track_id,
                voted_ship_id=ship_id,
                first_seen_at=datetime.datetime.fromtimestamp(tb.first_seen_ts),
                last_seen_at=datetime.datetime.fromtimestamp(tb.last_seen_ts),
                confidence=tb.conf,
                ocr_attempts=len(hist),
                vote_summary=vote_summary
            ))
        except Exception:
            db.rollback()
            raise

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
        
        # Load detector if not loaded
        if self._detector is None:
            # COCO class id 8 = boat
            self._detector, _ = load_yolo_detector(
                settings.MODEL_PATH, 
                settings.DEVICE, 
                settings.CONF, 
                [8]
            )

        # Use settings for all params
        ocr_active = enable_ocr if enable_ocr is not None else settings.ENABLE_OCR
        ocr_interval = settings.OCR_INTERVAL_FRAMES
        ocr_label_ttl = settings.OCR_LABEL_TTL_SEC
        
        # Combine DB callback with Audit Logger callback
        db_cb = self._on_track_removed_db
        audit_cb = _build_track_removed_logger(
            str(self._runs_base), 
            settings.OCR_AUDIT_ENABLE,
            log_dedup_window_sec=0.0 # Can add to settings if needed
        )
        
        def combined_on_removed(tb, hist):
            db_cb(tb, hist)
            if audit_cb:
                audit_cb(tb, hist)

        self._boat_tracker = BoatTracker(
            min_hits=settings.TRACK_MIN_HITS,
            max_tentative_misses=settings.TRACK_MAX_TENTATIVE_MISSES,
            max_lost_frames=settings.TRACK_MAX_LOST_FRAMES,
            iou_threshold=settings.TRACK_IOU_THRESHOLD,
            reid_window_sec=settings.TRACK_REID_WINDOW_SEC,
            reid_max_centroid_dist=settings.TRACK_REID_MAX_DIST,
            on_track_removed=combined_on_removed
        )

        self._reader = FrameReaderThread(source, self._frame_queue, self._stop)
        self._yolo_worker = YoloWorkerThread(
            self._detector, self._boat_tracker, self._frame_queue, self._result_queue,
            self._ocr_queue, self._video_queue, self._stop, ocr_interval, ocr_active,
            ocr_cache=self.ocr_cache, ocr_lock=self.ocr_lock, ocr_label_ttl=ocr_label_ttl,
            record_overlay_resize_scale=settings.RESIZE_SCALE
        )

        if ocr_active:
            recognizer = ShipIdRecognizer()
            self._ocr_worker = OcrWorkerThread(
                recognizer, self._ocr_queue, self.ocr_cache, self.ocr_lock, self._stop,
                ocr_label_ttl, settings.SAVE_MIN_INTERVAL_SEC, 
                boat_tracker=self._boat_tracker, runs_base=str(self._runs_base),
                save_ocr_audit_frames=settings.OCR_AUDIT_SAVE_FRAMES
            )

        if settings.RECORD_ENABLE:
            self._video_worker = VideoRecorderThread(
                self._video_queue, self._stop,
                max_duration_sec=settings.RECORD_MAX_DURATION_MIN * 60,
                gap_sec=settings.RECORD_NO_BOAT_GAP_SEC,
                record_fps=settings.RECORD_FPS,
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
                "first_seen": datetime.datetime.fromtimestamp(tb.first_seen_ts).isoformat(),
                "last_seen": datetime.datetime.fromtimestamp(tb.last_seen_ts).isoformat(),
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

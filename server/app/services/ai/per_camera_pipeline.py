from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from app.services import pipeline_preview
from app.services.ai.boat_tracker import BoatTracker, TrackState, TrackedBoat
from app.services.ai.clahe_preprocessor import ClahePreprocessConfig, preprocess_frame_clahe
from app.services.ai.cross_camera_reid import CrossCameraReIdManager
from app.services.ai.embedding_extractor import EmbeddingExtractor
from app.services.ai.frame_reader import FrameReaderThread
from app.services.ai.motion_classifier import MOTION_STATIC, MotionClassifier
from app.services.ai.seam_anchor_color import extract_dominant_hsv
from app.services.ai.ocr_worker import OcrQueueItem, OcrWorkerThread
from app.utils.ai.overlay import draw_ship_detection_overlay
from app.utils.ai.pipeline_utils import clamp_box, put_queue_drop_oldest
from app.utils.ai.ship_id_recognizer import ShipIdRecognizer

_COLOR_TENTATIVE = (128, 128, 128)
_COLOR_CONFIRMED = (0, 255, 0)
_COLOR_LOST = (0, 165, 255)


@dataclass(frozen=True)
class PerCameraPipelineConfig:
    camera_id: int
    source: str | int
    record_fps: float
    enable_ocr: bool
    ocr_interval_frames: int
    ocr_label_ttl_sec: float
    save_min_interval_sec: float
    ocr_audit_save_frames: bool
    resize_scale: float
    track_min_hits: int
    track_max_tentative_misses: int
    track_max_lost_frames: int
    track_iou_threshold: float
    track_reid_window_sec: float
    track_reid_max_dist: float
    clahe_clip_limit: float
    clahe_tile_size: int
    edge_zone_ratio: float
    enable_preview_stream: bool = False
    track_min_confirm_sec: float | None = None
    track_max_tentative_sec: float | None = None
    track_max_lost_sec: float | None = None
    ocr_interval_sec: float | None = None


class PerCameraPipeline(threading.Thread):
    def __init__(
        self,
        *,
        config: PerCameraPipelineConfig,
        detector: Any,
        detector_lock: threading.Lock,
        reid_manager: CrossCameraReIdManager,
        embedding_extractor: EmbeddingExtractor,
        video_queue: queue.Queue | None,
        stop_event: threading.Event,
        ocr_cache: dict,
        ocr_lock: threading.RLock,
        runs_base: str,
        on_image_captured=None,
        on_overlay_media_sample=None,
        input_frame_queue: queue.Queue | None = None,
        shared_ocr_queue: queue.Queue | None = None,
        single_camera_video_queue: queue.Queue | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.config = config
        self._detector = detector
        self._detector_lock = detector_lock
        self._reid_manager = reid_manager
        self._embedding_extractor = embedding_extractor
        self._video_queue = video_queue
        self._single_camera_video_queue = single_camera_video_queue
        self._stop_event = stop_event
        self._ocr_cache = ocr_cache
        self._ocr_lock = ocr_lock
        self._runs_base = runs_base
        self._on_overlay_media_sample = on_overlay_media_sample
        self._uses_external_frames = input_frame_queue is not None
        self._frame_queue = input_frame_queue or queue.Queue(maxsize=3)
        self._reader: FrameReaderThread | None = None
        if not self._uses_external_frames:
            self._reader = FrameReaderThread(
                config.source,
                self._frame_queue,
                stop_event,
                target_fps=config.record_fps,
            )
        self._tracker = BoatTracker(
            min_hits=config.track_min_hits,
            max_tentative_misses=config.track_max_tentative_misses,
            max_lost_frames=config.track_max_lost_frames,
            iou_threshold=config.track_iou_threshold,
            reid_window_sec=0.0,
            reid_max_centroid_dist=config.track_reid_max_dist,
            on_track_removed=self._on_local_track_removed,
            camera_id=config.camera_id,
            min_confirm_sec=config.track_min_confirm_sec,
            max_tentative_sec=config.track_max_tentative_sec,
            max_lost_sec=config.track_max_lost_sec,
        )
        self._motion_classifier = MotionClassifier()
        self._clahe_config = ClahePreprocessConfig(
            clip_limit=config.clahe_clip_limit,
            tile_grid_size=config.clahe_tile_size,
        )
        self._shared_ocr_queue = shared_ocr_queue
        self._ocr_queue: queue.Queue | None = None
        self._ocr_worker: OcrWorkerThread | None = None
        if config.enable_ocr:
            if shared_ocr_queue is not None:
                self._ocr_queue = shared_ocr_queue
            else:
                self._ocr_queue = queue.Queue(maxsize=5)
                self._ocr_worker = OcrWorkerThread(
                    ShipIdRecognizer(),
                    self._ocr_queue,
                    self._ocr_cache,
                    self._ocr_lock,
                    self._stop_event,
                    config.ocr_label_ttl_sec,
                    config.save_min_interval_sec,
                    boat_tracker=self._tracker,
                    runs_base=runs_base,
                    save_ocr_audit_frames=config.ocr_audit_save_frames,
                    on_image_captured=on_image_captured,
                    on_ocr_result=self._on_ocr_result,
                )
        self._frame_count = 0
        self._fps_started_at: float | None = None
        self._last_ocr_ts = 0.0

    @property
    def tracker(self) -> BoatTracker:
        return self._tracker

    def start(self) -> None:
        if self._reader is not None:
            self._reader.start()
        if self._ocr_worker is not None:
            self._ocr_worker.start()
        super().start()

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    raw_frame = self._frame_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                self._frame_count += 1
                if self._fps_started_at is None:
                    self._fps_started_at = time.time()
                fps_est = self._frame_count / max(1e-6, time.time() - self._fps_started_at)
                self._process_frame(raw_frame, fps_est)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                'PerCameraPipeline crashed for camera_id=%s',
                self.config.camera_id,
            )
        finally:
            self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        if self._reader is not None:
            self._reader.join(timeout=timeout)
        if self._ocr_worker is not None:
            self._ocr_worker.join(timeout=timeout)
        super().join(timeout=timeout)

    def flush_shutdown_logs(self) -> None:
        self._tracker.flush_shutdown_logs()

    def _process_frame(self, raw_frame: np.ndarray, fps_est: float) -> None:
        processed = preprocess_frame_clahe(raw_frame, self._clahe_config)
        with self._detector_lock:
            boxes_list, det_confs = self._detector.predict_boxes(processed)
        tracked_boats = self._tracker.update(boxes_list, det_confs)

        annotated = raw_frame.copy()
        for track in tracked_boats:
            self._enrich_track(raw_frame, track)
            color = _color_for_track(track)
            box = track.box
            cv2.rectangle(
                annotated,
                (int(box[0]), int(box[1])),
                (int(box[2]), int(box[3])),
                color,
                2,
            )

        active_ids = {str(track.track_id) for track in tracked_boats}
        self._motion_classifier.forget_missing(active_ids)
        overlay_frame = draw_ship_detection_overlay(
            annotated,
            tracked_boats,
            self._ocr_cache,
            self._ocr_lock,
            self.config.ocr_label_ttl_sec,
            fps_est,
            1.0,
        )
        if self._on_overlay_media_sample is not None:
            try:
                self._on_overlay_media_sample(
                    int(self.config.camera_id),
                    overlay_frame,
                    tracked_boats,
                )
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    'on_overlay_media_sample failed for camera_id=%s',
                    self.config.camera_id,
                )
        if self.config.enable_preview_stream:
            display_frame = overlay_frame
            if self.config.resize_scale != 1.0:
                display_frame = draw_ship_detection_overlay(
                    annotated,
                    tracked_boats,
                    self._ocr_cache,
                    self._ocr_lock,
                    self.config.ocr_label_ttl_sec,
                    fps_est,
                    self.config.resize_scale,
                )
            pipeline_preview.push_bgr_frame(display_frame)
        record_queues = (
            self._video_queue is not None or self._single_camera_video_queue is not None
        )
        if record_queues:
            video_frame = overlay_frame
            if self.config.resize_scale != 1.0:
                video_frame = draw_ship_detection_overlay(
                    annotated,
                    tracked_boats,
                    self._ocr_cache,
                    self._ocr_lock,
                    self.config.ocr_label_ttl_sec,
                    fps_est,
                    self.config.resize_scale,
                )
            item = (video_frame, tracked_boats)
            if self._video_queue is not None:
                put_queue_drop_oldest(self._video_queue, item)
            if self._single_camera_video_queue is not None:
                put_queue_drop_oldest(self._single_camera_video_queue, item)

        self._queue_ocr(raw_frame, tracked_boats)

    def _enrich_track(self, frame: np.ndarray, track: TrackedBoat) -> None:
        if track.state != TrackState.CONFIRMED:
            return
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = clamp_box(track.box, width, height)
        crop = frame[y1:y2, x1:x2]
        embedding = self._embedding_extractor.extract(crop)
        motion_state = self._motion_classifier.classify(frame, track)
        now = time.time()
        if motion_state == MOTION_STATIC:
            if track.static_since_ts is None:
                track.static_since_ts = now
        else:
            track.static_since_ts = None
        dominant_hsv = extract_dominant_hsv(frame, (x1, y1, x2 - x1, y2 - y1))
        self._tracker.update_track_metadata(
            str(track.track_id),
            embedding=embedding,
            motion_state=motion_state,
        )
        track.embedding = embedding
        track.motion_state = motion_state
        track.dominant_color_hsv = dominant_hsv
        self._reid_manager.report_track_update(
            int(self.config.camera_id),
            track,
            embedding=embedding,
            frame_shape=(height, width),
        )
        global_ship_id = self._reid_manager.get_global_ship_id(
            int(self.config.camera_id),
            str(track.track_id),
        )
        if global_ship_id:
            track.ship_id = global_ship_id
            track.last_known_ship_id = global_ship_id
            self._tracker.update_track_metadata(str(track.track_id), ship_id=global_ship_id)

    def _queue_ocr(self, frame: np.ndarray, tracked_boats: list[TrackedBoat]) -> None:
        if not self.config.enable_ocr or self._ocr_queue is None:
            return
        if self.config.ocr_interval_sec is not None:
            now = time.time()
            if now - self._last_ocr_ts < float(self.config.ocr_interval_sec):
                return
            self._last_ocr_ts = now
        elif self._frame_count % max(1, self.config.ocr_interval_frames) != 0:
            return
        confirmed = [track for track in tracked_boats if track.state == TrackState.CONFIRMED]
        if not confirmed:
            return

        items = [(track.track_id, track.box.copy()) for track in confirmed]
        if self._shared_ocr_queue is not None:
            put_queue_drop_oldest(
                self._ocr_queue,
                OcrQueueItem(
                    frame=frame.copy(),
                    boxes_list=items,
                    boat_tracker=self._tracker,
                    on_ocr_result=self._on_ocr_result,
                    camera_id=int(self.config.camera_id),
                ),
            )
        else:
            put_queue_drop_oldest(self._ocr_queue, (frame.copy(), items))

    def _on_ocr_result(self, track_id: str, ship_id: str, confidence: float) -> None:
        self._reid_manager.report_ocr_result(
            int(self.config.camera_id),
            str(track_id),
            ship_id,
            confidence,
        )
        global_ship_id = self._reid_manager.get_global_ship_id(
            int(self.config.camera_id),
            str(track_id),
        )
        if global_ship_id:
            self._tracker.update_track_metadata(str(track_id), ship_id=global_ship_id)

    def _on_local_track_removed(
        self,
        track: TrackedBoat,
        ocr_history: list[tuple[str, float]],
    ) -> None:
        self._reid_manager.report_track_removed(
            int(self.config.camera_id),
            track,
            ocr_history,
        )


def _edge_side(box: np.ndarray, width: int, edge_zone_ratio: float) -> str | None:
    x1, _, x2, _ = box.astype(float)
    edge_px = max(1.0, float(width) * float(edge_zone_ratio))
    centroid_x = (x1 + x2) * 0.5
    if centroid_x <= edge_px or x1 <= edge_px:
        return 'left'
    if centroid_x >= width - edge_px or x2 >= width - edge_px:
        return 'right'
    return None


def _color_for_track(track: TrackedBoat) -> tuple[int, int, int]:
    if track.state == TrackState.TENTATIVE:
        return _COLOR_TENTATIVE
    if track.state == TrackState.LOST:
        return _COLOR_LOST
    return _COLOR_CONFIRMED

"""YOLO inference thread: detect boat, annotate frame, fan-out queues."""
from __future__ import annotations

import queue
import threading
import time

import cv2

from app.services.ai.boat_tracker import BoatTracker, TrackState, TrackedBoat
from app.utils.ai.overlay import draw_ship_detection_overlay
from app.utils.ai.pipeline_utils import put_queue_drop_oldest
from app.services import pipeline_preview

_COLOR_TENTATIVE = (128, 128, 128)
_COLOR_CONFIRMED = (0, 255, 0)
_COLOR_LOST = (0, 165, 255)


def _color_for_track(tb: TrackedBoat) -> tuple[int, int, int]:
    if tb.state == TrackState.TENTATIVE:
        return _COLOR_TENTATIVE
    if tb.state == TrackState.LOST:
        return _COLOR_LOST
    return _COLOR_CONFIRMED


class YoloWorkerThread(threading.Thread):
    def __init__(
        self,
        detector,
        boat_tracker: BoatTracker,
        frame_queue: "queue.Queue",
        result_queue: "queue.Queue",
        ocr_queue: "queue.Queue | None",
        video_queue: "queue.Queue | None",
        stop_event: threading.Event,
        ocr_interval: int,
        enable_ocr: bool,
        ocr_cache: dict | None = None,
        ocr_lock: threading.RLock | None = None,
        ocr_label_ttl: float = 5.0,
        record_overlay_resize_scale: float = 1.0,
        enable_preview_stream: bool = True,
    ):
        super().__init__(daemon=True)
        self._detector = detector
        self._tracker = boat_tracker
        self._frame_queue = frame_queue
        self._result_queue = result_queue
        self._ocr_queue = ocr_queue
        self._video_queue = video_queue
        self._stop_event = stop_event
        self.ocr_interval = ocr_interval
        self.enable_ocr = enable_ocr
        self.frame_count = 0
        self._ocr_cache = ocr_cache
        self._ocr_lock = ocr_lock
        self._ocr_label_ttl = ocr_label_ttl
        self._record_overlay_resize_scale = record_overlay_resize_scale
        self._enable_preview_stream = enable_preview_stream
        self._fps_t0: float | None = None

    def run(self):
        try:
            while not self._stop_event.is_set():
                try:
                    frame = self._frame_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                self.frame_count += 1
                if self._fps_t0 is None:
                    self._fps_t0 = time.time()
                fps_est = self.frame_count / max(
                    1e-6, time.time() - self._fps_t0
                )

                boxes_list, det_confs = self._detector.predict_boxes(frame)
                tracked_boats = self._tracker.update(boxes_list, det_confs)

                annotated_frame = frame.copy()
                for tb in tracked_boats:
                    b = tb.box
                    col = _color_for_track(tb)
                    cv2.rectangle(
                        annotated_frame,
                        (int(b[0]), int(b[1])),
                        (int(b[2]), int(b[3])),
                        col,
                        2,
                    )

                put_queue_drop_oldest(
                    self._result_queue,
                    (annotated_frame, tracked_boats),
                )

                # Một pipeline overlay cho cả WebSocket preview và ghi video (đồng bộ với frame lưu).
                overlay_frame = draw_ship_detection_overlay(
                    annotated_frame.copy(),
                    tracked_boats,
                    self._ocr_cache,
                    self._ocr_lock,
                    self._ocr_label_ttl,
                    fps_est,
                    self._record_overlay_resize_scale,
                )

                if self._enable_preview_stream:
                    try:
                        pipeline_preview.push_bgr_frame(overlay_frame)
                    except Exception:
                        pass

                if self._video_queue is not None:
                    put_queue_drop_oldest(
                        self._video_queue,
                        (overlay_frame, tracked_boats),
                    )

                confirmed = [
                    tb
                    for tb in tracked_boats
                    if tb.state == TrackState.CONFIRMED
                ]
                ocr_tick = (
                    self.enable_ocr
                    and self._ocr_queue is not None
                    and (self.frame_count % self.ocr_interval == 0)
                    and len(confirmed) > 0
                )
                if ocr_tick:
                    try:
                        items = [(tb.track_id, tb.box.copy()) for tb in confirmed]
                        self._ocr_queue.put_nowait((frame.copy(), items))
                    except queue.Full:
                        pass
        except Exception as e:
            print(f"[WARNING] YoloWorkerThread crashed: {e}")
        finally:
            self._stop_event.set()

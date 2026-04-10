"""Ghi video từ frame đã annotate (YOLO), luồng riêng."""
from __future__ import annotations
import os
import queue
import threading
import time

import cv2

from app.services.ai.boat_tracker import TrackState, TrackedBoat

from app.utils.ai.detect_paths import RUNS_DETECT, ensure_dir, timestamp_prefix, videos_dir_for_today


def _n_confirmed(tracked_boats: list) -> int:
    return sum(
        1
        for t in tracked_boats
        if getattr(t, "state", None) == TrackState.CONFIRMED
    )


class VideoRecorderThread(threading.Thread):
    """
    Nhận (annotated_frame, tracked_boats) từ queue; ghi MP4 khi có tàu CONFIRMED.
    - Ngắt: hết max duration hoặc không có CONFIRMED liên tục >= gap (debounce nhiễu).
    - Restart file: số CONFIRMED tăng so với max_boat_count của session hiện tại.
    """

    def __init__(
        self,
        video_queue: "queue.Queue",
        stop_event: threading.Event,
        max_duration_sec: float,
        gap_sec: float,
        record_fps: float,
        runs_base: str = RUNS_DETECT,
    ):
        super().__init__(daemon=True)
        self._video_queue = video_queue
        self._stop_event = stop_event
        self._max_duration_sec = max(0.0, float(max_duration_sec))
        # gap_sec <= 0: không ngắt theo "mất tàu" (chỉ max duration / số tàu tăng)
        self._gap_sec = float(gap_sec)
        self._record_fps = max(1.0, float(record_fps))
        self._runs_base = runs_base

        self._writer: cv2.VideoWriter | None = None
        self._current_path: str | None = None
        self._max_boat_count = 0
        self._start_ts = 0.0
        self._last_boat_ts = 0.0

    def _stop_recording(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            if self._current_path:
                print(f"[RECORD] Saved: {self._current_path}")
            self._current_path = None

    def _begin_session(self, frame, n_boats: int) -> None:
        h, w = frame.shape[:2]
        out_dir = ensure_dir(videos_dir_for_today(self._runs_base))
        name = f"{timestamp_prefix()}.mp4"
        path = os.path.join(out_dir, name)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            path, fourcc, self._record_fps, (w, h)
        )
        if not writer.isOpened():
            print(f"[RECORD] Error: could not open VideoWriter for {path}")
            return

        self._writer = writer
        self._current_path = path
        self._max_boat_count = n_boats
        now = time.monotonic()
        self._start_ts = now
        self._last_boat_ts = now
        self._writer.write(frame)
        print(f"[RECORD] Started: {path} (confirmed={n_boats})")

    def _maybe_stop_on_timeout(self, now: float) -> None:
        if self._writer is None:
            return
        if self._max_duration_sec > 0 and (
            now - self._start_ts >= self._max_duration_sec
        ):
            self._stop_recording()
            return
        if self._gap_sec > 0 and now - self._last_boat_ts >= self._gap_sec:
            self._stop_recording()

    def _process_frame(self, frame, tracked_boats: list[TrackedBoat]) -> None:
        n = _n_confirmed(tracked_boats)
        now = time.monotonic()

        if self._writer is not None:
            if n > self._max_boat_count:
                self._stop_recording()
                self._begin_session(frame, n)
                return

            self._writer.write(frame)
            if n > 0:
                self._last_boat_ts = now
            self._maybe_stop_on_timeout(now)
            return

        if n > 0:
            self._begin_session(frame, n)

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    item = self._video_queue.get(timeout=0.5)
                except queue.Empty:
                    if self._writer is not None:
                        self._maybe_stop_on_timeout(time.monotonic())
                    continue

                if not item or len(item) < 2:
                    continue
                frame, tracked_boats = item[0], item[1]
                if frame is None or frame.size == 0:
                    continue

                self._process_frame(frame, tracked_boats)
        except Exception as e:
            print(f"[WARNING] VideoRecorderThread crashed: {e}")
        finally:
            self._stop_recording()

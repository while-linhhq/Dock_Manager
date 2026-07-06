from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from app.utils.ai.ffmpeg_log import suppress_ffmpeg_decoder_logs

suppress_ffmpeg_decoder_logs()

import cv2

from app.services.ai.frame_reader import open_rtsp
from app.utils.ai.frame_quality import is_usable_bgr_frame
from app.utils.ai.rtsp_capture import FfmpegNvdecCapture, GStreamerNvdecCapture


@dataclass(frozen=True)
class CameraSource:
    camera_id: int
    source: str | int


@dataclass
class TimedFrame:
    camera_id: int
    frame: Any
    captured_at: float
    sequence: int = 0


class LatestFrameBuffer:
    def __init__(self, history_sec: float = 8.0) -> None:
        self._frames: dict[int, TimedFrame] = {}
        self._history: dict[int, deque[TimedFrame]] = {}
        self._history_sec = max(1.0, float(history_sec))
        self._sequences: dict[int, int] = {}
        self._lock = threading.Lock()

    def set(self, camera_id: int, frame: Any, captured_at: float | None = None) -> None:
        camera_key = int(camera_id)
        capture_ts = captured_at or time.monotonic()
        with self._lock:
            sequence = self._sequences.get(camera_key, 0) + 1
            self._sequences[camera_key] = sequence
            item = TimedFrame(
                camera_id=camera_key,
                frame=frame.copy(),
                captured_at=capture_ts,
                sequence=sequence,
            )
            self._frames[camera_key] = item
            history = self._history.setdefault(camera_key, deque())
            history.append(item)
            cutoff = capture_ts - self._history_sec
            while history and history[0].captured_at < cutoff:
                history.popleft()

    def snapshot(self, copy_frames: bool = True) -> dict[int, TimedFrame]:
        with self._lock:
            return {
                camera_id: TimedFrame(
                    item.camera_id,
                    item.frame.copy() if copy_frames else item.frame,
                    item.captured_at,
                    item.sequence,
                )
                for camera_id, item in self._frames.items()
            }

    def history_snapshot(
        self,
        camera_ids: list[int] | None = None,
        *,
        copy_frames: bool = True,
    ) -> dict[int, list[TimedFrame]]:
        ids = None if camera_ids is None else {int(camera_id) for camera_id in camera_ids}
        with self._lock:
            result: dict[int, list[TimedFrame]] = {}
            for camera_id, items in self._history.items():
                if ids is not None and camera_id not in ids:
                    continue
                result[camera_id] = [
                    TimedFrame(
                        item.camera_id,
                        item.frame.copy() if copy_frames else item.frame,
                        item.captured_at,
                        item.sequence,
                    )
                    for item in items
                ]
            return result


def _drain_latest_from_capture(cap: Any, *, max_grabs: int = 4) -> Any | None:
    """Drop a few buffered RTSP frames; return the newest decoded image."""
    latest = None
    grabs = max(1, int(max_grabs))
    for _ in range(grabs):
        grabbed = cap.grab()
        if not grabbed:
            break
        ok, frame = cap.retrieve()
        if ok and frame is not None:
            latest = frame
    if latest is not None:
        return latest
    ok, frame = cap.read()
    if ok and frame is not None:
        return frame
    return None


class MultiFrameReaderThread(threading.Thread):
    def __init__(
        self,
        source: CameraSource,
        frame_buffer: LatestFrameBuffer,
        stop_event: threading.Event,
        target_fps: float | None = None,
        *,
        drain_rtsp_buffer: bool = True,
        max_drain_grabs: int = 4,
    ) -> None:
        super().__init__(daemon=True)
        self._source = source
        self._frame_buffer = frame_buffer
        self._stop_event = stop_event
        self._cap = None
        self._drain_rtsp_buffer = drain_rtsp_buffer
        self._max_drain_grabs = max(1, int(max_drain_grabs))
        self._target_interval = 1.0 / target_fps if target_fps and target_fps > 0 else None

    def run(self) -> None:
        try:
            self._cap = self._open_capture()
            if self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                print(f'Error: Could not open stream {self._source.source}')
                return

            next_emit = time.monotonic()
            while not self._stop_event.is_set():
                if isinstance(self._cap, (FfmpegNvdecCapture, GStreamerNvdecCapture)):
                    ok, frame = self._cap.read()
                    frame = frame if ok and frame is not None else None
                elif self._drain_rtsp_buffer:
                    frame = _drain_latest_from_capture(
                        self._cap,
                        max_grabs=self._max_drain_grabs,
                    )
                else:
                    ok, frame = self._cap.read()
                    frame = frame if ok and frame is not None else None

                if frame is None:
                    if isinstance(self._source.source, str):
                        self._cap.release()
                        time.sleep(2)
                        self._cap = self._open_capture()
                        if self._cap.isOpened():
                            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        continue
                    break

                now = time.monotonic()
                if self._target_interval is not None and now < next_emit:
                    continue
                if self._target_interval is not None:
                    next_emit = now + self._target_interval
                self._frame_buffer.set(self._source.camera_id, frame, captured_at=now)
        except Exception as err:
            print(f'[WARNING] MultiFrameReaderThread crashed: {err}')
        finally:
            if self._cap is not None:
                self._cap.release()

    def _open_capture(self):
        if isinstance(self._source.source, str):
            return open_rtsp(self._source.source)
        return cv2.VideoCapture(self._source.source)


def capture_snapshot(
    source: str | int,
    timeout_sec: float = 8.0,
    *,
    warmup_frames: int = 3,
) -> Any | None:
    cap = open_rtsp(source) if isinstance(source, str) else cv2.VideoCapture(source)
    try:
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        for _ in range(max(0, int(warmup_frames))):
            ok, frame = cap.read()
            if ok and frame is not None and is_usable_bgr_frame(frame):
                return frame.copy()

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if ok and frame is not None and is_usable_bgr_frame(frame):
                return frame.copy()
            time.sleep(0.05)
        return None
    finally:
        cap.release()

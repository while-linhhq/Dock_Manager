from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import cv2

from app.services.ai.frame_reader import open_rtsp


@dataclass(frozen=True)
class CameraSource:
    camera_id: int
    source: str | int


@dataclass
class TimedFrame:
    camera_id: int
    frame: Any
    captured_at: float


class LatestFrameBuffer:
    def __init__(self) -> None:
        self._frames: dict[int, TimedFrame] = {}
        self._lock = threading.Lock()

    def set(self, camera_id: int, frame: Any, captured_at: float | None = None) -> None:
        with self._lock:
            self._frames[int(camera_id)] = TimedFrame(
                camera_id=int(camera_id),
                frame=frame.copy(),
                captured_at=captured_at or time.monotonic(),
            )

    def snapshot(self) -> dict[int, TimedFrame]:
        with self._lock:
            return {
                camera_id: TimedFrame(item.camera_id, item.frame.copy(), item.captured_at)
                for camera_id, item in self._frames.items()
            }


class MultiFrameReaderThread(threading.Thread):
    def __init__(
        self,
        source: CameraSource,
        frame_buffer: LatestFrameBuffer,
        stop_event: threading.Event,
        target_fps: float | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self._source = source
        self._frame_buffer = frame_buffer
        self._stop_event = stop_event
        self._cap = None
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
                ok, frame = self._cap.read()
                if not ok or frame is None:
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
                self._frame_buffer.set(self._source.camera_id, frame)
        except Exception as err:
            print(f'[WARNING] MultiFrameReaderThread crashed: {err}')
        finally:
            if self._cap is not None:
                self._cap.release()

    def _open_capture(self):
        if isinstance(self._source.source, str):
            return open_rtsp(self._source.source)
        return cv2.VideoCapture(self._source.source)


def capture_snapshot(source: str | int, timeout_sec: float = 5.0):
    cap = open_rtsp(source) if isinstance(source, str) else cv2.VideoCapture(source)
    try:
        if not cap.isOpened():
            return None
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if ok and frame is not None:
                return frame.copy()
            time.sleep(0.05)
        return None
    finally:
        cap.release()

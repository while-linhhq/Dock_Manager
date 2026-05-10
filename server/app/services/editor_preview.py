from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2

from app.services.ai.multi_frame_reader import (
    CameraSource,
    LatestFrameBuffer,
    MultiFrameReaderThread,
    TimedFrame,
)


@dataclass
class _PreviewStream:
    buffer: LatestFrameBuffer
    stop_event: threading.Event
    reader: MultiFrameReaderThread
    ref_count: int = 0
    last_jpeg: bytes | None = None
    last_encoded_at: float = 0.0


class EditorPreviewManager:
    def __init__(self, target_fps: float = 8.0, jpeg_quality: int = 72) -> None:
        self._streams: dict[int, _PreviewStream] = {}
        self._lock = threading.Lock()
        self._target_fps = target_fps
        self._jpeg_quality = jpeg_quality
        self._min_encode_interval = 1.0 / max(1.0, target_fps)

    def acquire(self, camera_id: int, source: str | int) -> None:
        camera_key = int(camera_id)
        with self._lock:
            stream = self._streams.get(camera_key)
            if stream is None or not stream.reader.is_alive():
                stop_event = threading.Event()
                buffer = LatestFrameBuffer()
                reader = MultiFrameReaderThread(
                    CameraSource(camera_id=camera_key, source=source),
                    frame_buffer=buffer,
                    stop_event=stop_event,
                    target_fps=self._target_fps,
                )
                stream = _PreviewStream(buffer=buffer, stop_event=stop_event, reader=reader)
                self._streams[camera_key] = stream
                reader.start()
            stream.ref_count += 1

    def release(self, camera_id: int) -> None:
        camera_key = int(camera_id)
        reader: MultiFrameReaderThread | None = None
        with self._lock:
            stream = self._streams.get(camera_key)
            if stream is None:
                return
            stream.ref_count = max(0, stream.ref_count - 1)
            if stream.ref_count > 0:
                return
            stream.stop_event.set()
            reader = stream.reader
            self._streams.pop(camera_key, None)

        if reader is not None:
            reader.join(timeout=2.0)

    def get_jpeg(self, camera_id: int) -> bytes | None:
        camera_key = int(camera_id)
        with self._lock:
            stream = self._streams.get(camera_key)
            if stream is None:
                return None
            now = time.monotonic()
            if stream.last_jpeg is not None and now - stream.last_encoded_at < self._min_encode_interval:
                return stream.last_jpeg
            snapshot = stream.buffer.snapshot()

        timed_frame = snapshot.get(camera_key)
        if timed_frame is None:
            return None

        ok, encoded = cv2.imencode(
            '.jpg',
            timed_frame.frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
        )
        if not ok:
            return None

        jpeg = encoded.tobytes()
        with self._lock:
            stream = self._streams.get(camera_key)
            if stream is not None:
                stream.last_jpeg = jpeg
                stream.last_encoded_at = time.monotonic()
        return jpeg

    def latest_frames(self, camera_ids: list[int]) -> dict[int, TimedFrame]:
        frames: dict[int, TimedFrame] = {}
        camera_keys = {int(camera_id) for camera_id in camera_ids}
        with self._lock:
            streams = {
                camera_id: stream
                for camera_id, stream in self._streams.items()
                if camera_id in camera_keys
            }

        for camera_id, stream in streams.items():
            snapshot = stream.buffer.snapshot()
            timed_frame = snapshot.get(camera_id)
            if timed_frame is not None:
                frames[camera_id] = timed_frame
        return frames


editor_preview_manager = EditorPreviewManager()

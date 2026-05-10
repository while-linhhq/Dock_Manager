from __future__ import annotations

import time

from app.services.ai.multi_frame_reader import LatestFrameBuffer, TimedFrame


class FrameSynchronizer:
    def __init__(
        self,
        frame_buffer: LatestFrameBuffer,
        required_camera_ids: list[int],
        tolerance_ms: int = 400,
        stale_after_sec: float = 2.0,
    ) -> None:
        self._frame_buffer = frame_buffer
        self._required_camera_ids = [int(camera_id) for camera_id in required_camera_ids]
        self._tolerance_sec = max(0.0, tolerance_ms / 1000.0)
        self._stale_after_sec = stale_after_sec

    def next_batch(self) -> dict[int, TimedFrame] | None:
        frames = self._frame_buffer.snapshot()
        selected = {
            camera_id: frames[camera_id]
            for camera_id in self._required_camera_ids
            if camera_id in frames
        }
        if not selected:
            return None

        now = time.monotonic()
        fresh = {
            camera_id: frame
            for camera_id, frame in selected.items()
            if now - frame.captured_at <= self._stale_after_sec
        }
        if not fresh:
            return None

        timestamps = [frame.captured_at for frame in fresh.values()]
        if len(fresh) == len(self._required_camera_ids):
            if max(timestamps) - min(timestamps) <= self._tolerance_sec:
                return fresh

        # Prefer low latency over blocking forever when one RTSP stream lags.
        return fresh

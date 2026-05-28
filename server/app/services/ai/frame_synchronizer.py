from __future__ import annotations

import time

from app.services.ai.multi_frame_reader import LatestFrameBuffer, TimedFrame


class FrameSynchronizer:
    def __init__(
        self,
        frame_buffer: LatestFrameBuffer,
        required_camera_ids: list[int],
        tolerance_ms: int = 400,
        stale_after_sec: float = 2.5,
    ) -> None:
        self._frame_buffer = frame_buffer
        self._required_camera_ids = [int(camera_id) for camera_id in required_camera_ids]
        self._tolerance_sec = max(0.0, tolerance_ms / 1000.0)
        self._stale_after_sec = stale_after_sec

    def _fresh_frames(
        self,
        camera_ids: list[int],
    ) -> dict[int, TimedFrame]:
        frames = self._frame_buffer.snapshot()
        now = time.monotonic()
        selected = {
            int(camera_id): frames[int(camera_id)]
            for camera_id in camera_ids
            if int(camera_id) in frames
        }
        return {
            camera_id: frame
            for camera_id, frame in selected.items()
            if now - frame.captured_at <= self._stale_after_sec
        }

    def _is_aligned(self, batch: dict[int, TimedFrame], camera_ids: list[int]) -> bool:
        if len(batch) != len(camera_ids):
            return False
        timestamps = [frame.captured_at for frame in batch.values()]
        if not timestamps:
            return False
        return (max(timestamps) - min(timestamps)) <= self._tolerance_sec

    def try_aligned_batch(
        self,
        camera_ids: list[int] | None = None,
    ) -> dict[int, TimedFrame] | None:
        ids = [int(x) for x in (camera_ids or self._required_camera_ids)]
        if not ids:
            return None
        fresh = self._fresh_frames(ids)
        if len(fresh) != len(ids):
            return None
        anchor_ts = max(frame.captured_at for frame in fresh.values())
        aligned = {
            camera_id: frame
            for camera_id, frame in fresh.items()
            if anchor_ts - frame.captured_at <= self._tolerance_sec
        }
        if len(aligned) == len(ids):
            return aligned
        return None

    def wait_aligned_batch(
        self,
        camera_ids: list[int] | None = None,
        *,
        timeout_sec: float = 2.0,
        poll_interval_sec: float = 0.01,
    ) -> dict[int, TimedFrame] | None:
        ids = [int(x) for x in (camera_ids or self._required_camera_ids)]
        if not ids:
            return None
        deadline = time.monotonic() + max(0.05, float(timeout_sec))
        while time.monotonic() < deadline:
            aligned = self.try_aligned_batch(ids)
            if aligned is not None:
                return aligned
            time.sleep(max(0.005, float(poll_interval_sec)))
        return None

    def next_batch(self) -> dict[int, TimedFrame] | None:
        return self.try_aligned_batch(self._required_camera_ids)

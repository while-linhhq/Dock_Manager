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
        camera_offsets_ms: dict[int, int | float] | None = None,
    ) -> None:
        self._frame_buffer = frame_buffer
        self._required_camera_ids = [int(camera_id) for camera_id in required_camera_ids]
        self._tolerance_sec = max(0.0, tolerance_ms / 1000.0)
        self._stale_after_sec = stale_after_sec
        self._camera_offsets_sec = {
            int(camera_id): float(offset_ms) / 1000.0
            for camera_id, offset_ms in (camera_offsets_ms or {}).items()
        }
        self._last_emitted_sequences: dict[int, int] = {}

    def _effective_ts(self, camera_id: int, frame: TimedFrame) -> float:
        return frame.captured_at - self._camera_offsets_sec.get(int(camera_id), 0.0)

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

    def _select_history_frame(
        self,
        frames: list[TimedFrame],
        camera_id: int,
        target_effective_ts: float,
    ) -> TimedFrame | None:
        best: TimedFrame | None = None
        best_delta = float('inf')
        for frame in frames:
            effective_ts = self._effective_ts(camera_id, frame)
            delta = abs(effective_ts - target_effective_ts)
            if delta <= self._tolerance_sec and delta <= best_delta:
                best = frame
                best_delta = delta
        return best

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

        if not self._camera_offsets_sec:
            anchor_ts = max(frame.captured_at for frame in fresh.values())
            aligned = {
                camera_id: frame
                for camera_id, frame in fresh.items()
                if anchor_ts - frame.captured_at <= self._tolerance_sec
            }
            if len(aligned) != len(ids):
                return None
        else:
            # Use adjusted/effective capture time, not raw host receive time.
            # A camera with +5000ms latency has content from roughly 5s earlier;
            # align other cameras against that effective time using their history.
            target_effective_ts = min(
                self._effective_ts(camera_id, frame)
                for camera_id, frame in fresh.items()
            )
            history = self._frame_buffer.history_snapshot(ids, copy_frames=True)
            if len(history) != len(ids):
                return None
            aligned: dict[int, TimedFrame] = {}
            for camera_id in ids:
                frame = self._select_history_frame(
                    history.get(camera_id, []),
                    camera_id,
                    target_effective_ts,
                )
                if frame is None:
                    return None
                aligned[camera_id] = frame

        # Every emitted group batch must contain a new frame from every camera.
        # Reusing a previous frame from a slow/backlogged camera beside fresh
        # frames from other cameras makes the fused view look "synced" by
        # timestamp while the visual content keeps drifting apart.
        if any(
            self._last_emitted_sequences.get(camera_id) == frame.sequence
            for camera_id, frame in aligned.items()
        ):
            return None
        self._last_emitted_sequences = {
            camera_id: frame.sequence for camera_id, frame in aligned.items()
        }
        return aligned

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

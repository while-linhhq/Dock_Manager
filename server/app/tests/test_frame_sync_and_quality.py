import time

import numpy as np

from app.services.ai.frame_synchronizer import FrameSynchronizer
from app.services.ai.multi_frame_reader import LatestFrameBuffer
from app.utils.ai.frame_quality import is_usable_bgr_frame


def test_is_usable_rejects_flat_gray() -> None:
    flat = np.full((480, 640, 3), 128, dtype=np.uint8)
    assert is_usable_bgr_frame(flat) is False


def test_is_usable_accepts_textured_frame() -> None:
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, size=(480, 640, 3), dtype=np.uint8)
    assert is_usable_bgr_frame(frame) is True


def test_wait_aligned_batch_requires_close_timestamps() -> None:
    buffer = LatestFrameBuffer()
    now = time.monotonic()
    buffer.set(1, np.zeros((100, 100, 3), dtype=np.uint8), captured_at=now)
    buffer.set(2, np.zeros((100, 100, 3), dtype=np.uint8), captured_at=now + 0.05)
    sync = FrameSynchronizer(buffer, [1, 2], tolerance_ms=100)
    batch = sync.wait_aligned_batch(timeout_sec=0.2)
    assert batch is not None
    assert set(batch.keys()) == {1, 2}


def test_aligned_batch_requires_new_frame_from_every_camera() -> None:
    buffer = LatestFrameBuffer()
    now = time.monotonic()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    buffer.set(1, frame, captured_at=now)
    buffer.set(2, frame, captured_at=now + 0.01)
    sync = FrameSynchronizer(buffer, [1, 2], tolerance_ms=100)

    assert sync.try_aligned_batch() is not None

    # Camera 1 advances but camera 2 is still the previous frame. Emitting this
    # would visually mix different moments and let group sync drift over time.
    buffer.set(1, frame, captured_at=now + 0.02)
    assert sync.try_aligned_batch() is None

    buffer.set(2, frame, captured_at=now + 0.03)
    assert sync.try_aligned_batch() is not None


def test_aligned_batch_uses_history_with_camera_latency_offsets() -> None:
    buffer = LatestFrameBuffer(history_sec=10.0)
    now = time.monotonic()
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Camera 1 is low-latency and has a historical frame matching camera 2's
    # delayed content time. Camera 2 receives a frame now, but its visual content
    # is 5 seconds old, so sync must pick camera 1's older frame, not latest.
    buffer.set(1, frame, captured_at=now - 5.0)
    buffer.set(1, frame, captured_at=now)
    buffer.set(2, frame, captured_at=now)

    sync = FrameSynchronizer(
        buffer,
        [1, 2],
        tolerance_ms=100,
        camera_offsets_ms={2: 5000},
    )
    batch = sync.try_aligned_batch()

    assert batch is not None
    assert batch[1].captured_at == now - 5.0
    assert batch[2].captured_at == now

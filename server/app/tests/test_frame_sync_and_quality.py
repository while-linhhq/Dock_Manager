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

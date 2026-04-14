"""Latest-frame JPEG buffer for WebSocket preview (thread-safe, throttled)."""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

_lock = threading.Lock()
_jpeg: bytes | None = None
_last_emit: float = 0.0
_min_interval_sec = 0.12  # ~8 fps cap for preview bandwidth


def set_target_fps(fps: float) -> None:
    """Set preview JPEG emit rate cap (best-effort)."""
    global _min_interval_sec
    try:
        f = float(fps)
    except Exception:
        return
    if f <= 0:
        return
    # Cap interval; allow a little headroom to avoid busy loops.
    _min_interval_sec = max(0.0, 1.0 / f)


def push_bgr_frame(frame: np.ndarray) -> None:
    if frame is None or frame.size == 0:
        return
    global _last_emit, _jpeg
    now = time.monotonic()
    if now - _last_emit < _min_interval_sec:
        return
    _last_emit = now
    h, w = frame.shape[:2]
    max_w = 960
    if w > max_w:
        scale = max_w / float(w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
    if not ok:
        return
    data = buf.tobytes()
    with _lock:
        _jpeg = data


def get_jpeg() -> bytes | None:
    with _lock:
        return _jpeg


def clear() -> None:
    global _jpeg, _last_emit
    with _lock:
        _jpeg = None
        _last_emit = 0.0

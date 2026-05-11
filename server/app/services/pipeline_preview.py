"""Latest-frame JPEG preview hub for WebSocket preview streams."""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

_lock = threading.Lock()
_frame_ready = threading.Condition(_lock)
_stop_event = threading.Event()
_encoder_thread: threading.Thread | None = None
_latest_frame: np.ndarray | None = None
_latest_frame_seq = 0
_encoded_frame_seq = 0
_jpeg: bytes | None = None
_min_interval_sec = 0.05
_jpeg_quality = 72
_max_width = 960


def set_target_fps(fps: float) -> None:
    """Set preview JPEG encode cadence. This should mirror runtime record_fps."""
    global _min_interval_sec
    try:
        f = float(fps)
    except Exception:
        return
    if f <= 0:
        return
    _min_interval_sec = max(0.0, 1.0 / f)


def _ensure_encoder_thread() -> None:
    global _encoder_thread
    with _lock:
        if _encoder_thread is not None and _encoder_thread.is_alive():
            return
        _stop_event.clear()
        _encoder_thread = threading.Thread(target=_encoder_loop, daemon=True)
        _encoder_thread.start()


def _resize_for_preview(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= _max_width:
        return frame
    scale = _max_width / float(w)
    return cv2.resize(frame, (int(w * scale), int(h * scale)))


def _encoder_loop() -> None:
    global _encoded_frame_seq, _jpeg
    next_encode = time.monotonic()
    while not _stop_event.is_set():
        with _frame_ready:
            while not _stop_event.is_set() and _latest_frame_seq <= _encoded_frame_seq:
                _frame_ready.wait(timeout=0.5)
            if _stop_event.is_set():
                return
            wait_sec = next_encode - time.monotonic()
            if wait_sec > 0:
                _frame_ready.wait(timeout=min(wait_sec, 0.05))
                continue
            frame = None if _latest_frame is None else _latest_frame.copy()
            frame_seq = _latest_frame_seq

        if frame is None:
            continue

        preview_frame = _resize_for_preview(frame)
        ok, buf = cv2.imencode(
            '.jpg',
            preview_frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), _jpeg_quality],
        )
        next_encode = time.monotonic() + _min_interval_sec
        if not ok:
            continue

        with _lock:
            _jpeg = buf.tobytes()
            _encoded_frame_seq = frame_seq


def push_bgr_frame(frame: np.ndarray) -> None:
    if frame is None or frame.size == 0:
        return
    _ensure_encoder_thread()
    global _latest_frame, _latest_frame_seq
    with _frame_ready:
        _latest_frame = frame.copy()
        _latest_frame_seq += 1
        _frame_ready.notify_all()


def get_jpeg() -> bytes | None:
    with _lock:
        return _jpeg


def get_jpeg_with_sequence() -> tuple[int, bytes | None]:
    with _lock:
        return _encoded_frame_seq, _jpeg


def clear() -> None:
    global _jpeg, _latest_frame, _latest_frame_seq, _encoded_frame_seq, _encoder_thread
    _stop_event.set()
    with _frame_ready:
        _jpeg = None
        _latest_frame = None
        _latest_frame_seq = 0
        _encoded_frame_seq = 0
        _frame_ready.notify_all()
    if _encoder_thread is not None:
        _encoder_thread.join(timeout=1.0)
    with _lock:
        _encoder_thread = None
        _jpeg = None

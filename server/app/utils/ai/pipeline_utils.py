"""Helpers dùng chung giữa worker threads và overlay."""
from __future__ import annotations

import queue


def clamp_box(b, w, h):
    x1 = max(0, int(b[0]))
    y1 = max(0, int(b[1]))
    x2 = min(w, int(b[2]))
    y2 = min(h, int(b[3]))
    return x1, y1, x2, y2


def cache_key(b, idx):
    return f"{idx}_{b[0]}_{b[1]}_{b[2]}_{b[3]}"


def ocr_cache_key_track(track_id: str | int) -> str:
    """Stable OCR cache key across frames (replaces bbox-based key)."""
    return f"t{track_id}"


def put_queue_drop_oldest(q: "queue.Queue", payload):
    try:
        q.put_nowait(payload)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass

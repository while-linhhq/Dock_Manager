"""Helpers dùng chung giữa worker threads và overlay."""
from __future__ import annotations

import queue
import re
from typing import Any, Callable

_OCR_LABEL_SHIP_ID = re.compile(r'^([A-Z]{2}-\d{4})')


def clamp_box(b, w, h):
    x1 = max(0, int(b[0]))
    y1 = max(0, int(b[1]))
    x2 = min(w, int(b[2]))
    y2 = min(h, int(b[3]))
    return x1, y1, x2, y2


def cache_key(b, idx):
    return f"{idx}_{b[0]}_{b[1]}_{b[2]}_{b[3]}"


def ocr_cache_key_track(track_id: str | int, camera_id: int | None = None) -> str:
    """Stable OCR cache key across frames (replaces bbox-based key)."""
    if camera_id is not None:
        return f'c{int(camera_id)}:t{track_id}'
    return f't{track_id}'


def parse_ocr_ship_id_from_label(text: str) -> str | None:
    """Extract ship ID from OCR overlay label, e.g. ``BS-1234 (0.92)`` or ``BS-1234 (voted)``."""
    raw = str(text or '').strip().upper()
    if not raw:
        return None
    match = _OCR_LABEL_SHIP_ID.match(raw)
    return match.group(1) if match else None


def resolve_ocr_hint_for_visual(
    *,
    boat_tracker: Any | None,
    track_id: str,
    ocr_cache: dict,
    ocr_lock: Any,
    camera_id: int,
    catalog_is_known: Callable[[str], bool] | None = None,
) -> str | None:
    """
    OCR ship ID for visual fusion: tracker vote first, then cache ``ocr_ship_id`` / label text.
    Unknown catalog IDs are stripped so bogus OCR does not poison visual search.
    """
    hint: str | None = None
    if boat_tracker is not None:
        voted = boat_tracker.get_voted_ship_id(str(track_id))
        if voted:
            normalized = str(voted).strip().upper()
            if normalized:
                hint = normalized

    if hint is None:
        cache_key = ocr_cache_key_track(track_id, camera_id)
        with ocr_lock:
            entry = ocr_cache.get(cache_key)
        if isinstance(entry, dict):
            explicit = str(entry.get('ocr_ship_id') or '').strip().upper()
            if explicit:
                hint = explicit
            else:
                hint = parse_ocr_ship_id_from_label(str(entry.get('text') or ''))

    if hint and catalog_is_known is not None and not catalog_is_known(hint):
        return None
    return hint


def drain_queue_latest(q: "queue.Queue", first):
    """Keep only the newest queued item (drop backlog so AI/preview stay real-time)."""
    item = first
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
    return item


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

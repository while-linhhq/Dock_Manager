"""Vẽ overlay lên frame preview (det conf, global id, OCR, vector match, FPS)."""
from __future__ import annotations

import time

import cv2
import numpy as np

from app.services.ai.boat_tracker import TrackedBoat, TrackState
from app.utils.ai.pipeline_utils import ocr_cache_key_track
from app.utils.ai.time_sync import format_capture_wall_clock

_BERTH_IN_FILL_BGR = (90, 230, 110)
_BERTH_OUT_FILL_BGR = (110, 190, 255)
_BERTH_PENDING_FILL_BGR = (240, 195, 110)
_BERTH_FILL_ALPHA = 0.32
BERTH_IN_FILL_BGR = _BERTH_IN_FILL_BGR
BERTH_OUT_FILL_BGR = _BERTH_OUT_FILL_BGR
BERTH_PENDING_FILL_BGR = _BERTH_PENDING_FILL_BGR
BERTH_FILL_ALPHA = _BERTH_FILL_ALPHA


def resolve_berth_visual_state(track: TrackedBoat) -> str | None:
    """Return 'in' / 'out' / 'pending' for berth overlay, else None (skip tentative)."""
    if track.state not in (TrackState.CONFIRMED, TrackState.LOST):
        return None
    if track.berth_out_ts is not None:
        return 'out'
    if track.berth_in_ts is not None:
        return 'in'
    return 'pending'


def berth_fill_color_for_state(state: str) -> tuple[int, int, int]:
    if state == 'in':
        return BERTH_IN_FILL_BGR
    if state == 'out':
        return BERTH_OUT_FILL_BGR
    return BERTH_PENDING_FILL_BGR


def tint_bbox_overlay(
    frame: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color_bgr: tuple[int, int, int],
    alpha: float = _BERTH_FILL_ALPHA,
) -> None:
    h, w = frame.shape[:2]
    x1 = max(0, min(w - 1, int(x1)))
    y1 = max(0, min(h - 1, int(y1)))
    x2 = max(0, min(w, int(x2)))
    y2 = max(0, min(h, int(y2)))
    if x2 <= x1 or y2 <= y1:
        return
    roi = frame[y1:y2, x1:x2]
    tint = np.full_like(roi, color_bgr, dtype=np.uint8)
    cv2.addWeighted(tint, alpha, roi, 1.0 - alpha, 0, roi)


def _tint_bbox_region(
    frame: np.ndarray,
    box: np.ndarray,
    color_bgr: tuple[int, int, int],
    alpha: float,
) -> None:
    tint_bbox_overlay(
        frame,
        int(box[0]),
        int(box[1]),
        int(box[2]),
        int(box[3]),
        color_bgr,
        alpha,
    )


def draw_berth_state_bbox_overlays(
    frame: np.ndarray,
    tracked_boats: list[TrackedBoat],
) -> np.ndarray:
    """Light bbox fill: blue=pending, green=IN, orange=OUT."""
    if frame is None or frame.size == 0:
        return frame
    for track in tracked_boats:
        state = resolve_berth_visual_state(track)
        if state is None:
            continue
        color = berth_fill_color_for_state(state)
        _tint_bbox_region(frame, track.box, color, _BERTH_FILL_ALPHA)
    return frame


def draw_ship_detection_overlay(
    display_frame,
    tracked_boats: list[TrackedBoat],
    ocr_cache: dict | None,
    ocr_lock,
    ocr_label_ttl: float,
    fps: float,
    resize_scale: float,
    *,
    frame_captured_mono: float | None = None,
    camera_id: int | None = None,
):
    """
    Vẽ det confidence, global id + state, OCR ship_id, vector best ship + similarity, FPS.
    Nếu ocr_cache và ocr_lock là None: bỏ qua phần OCR (bbox đã vẽ ở worker).
    """
    now = time.time()

    for tb in tracked_boats:
        b = tb.box
        dc = tb.conf
        cv2.putText(
            display_frame,
            f"det {dc:.2f}",
            (int(b[0]), int(b[1]) - 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (180, 220, 255),
            2,
        )
        global_id = str(tb.ship_id or 'N/A')
        label = f"GID {global_id} [{tb.state.value}]"
        cv2.putText(
            display_frame,
            label,
            (int(b[0]), int(b[1]) - 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (220, 220, 100),
            2,
        )

    if ocr_cache is not None and ocr_lock is not None:
        with ocr_lock:
            for k in list(ocr_cache.keys()):
                if now - ocr_cache[k]["time"] >= ocr_label_ttl:
                    del ocr_cache[k]
            for tb in tracked_boats:
                ck = ocr_cache_key_track(tb.track_id, tb.camera_id)
                ent = ocr_cache.get(ck)
                if not ent:
                    continue
                b = tb.box
                y = min(int(b[3]) + 24, display_frame.shape[0] - 6)
                ocr_ship_id = str(ent.get('text') or '').strip()
                if ocr_ship_id:
                    cv2.putText(
                        display_frame,
                        f"OCR: {ocr_ship_id}",
                        (int(b[0]), y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 220, 255),
                        2,
                    )
                    y = min(y + 20, display_frame.shape[0] - 6)
                visual_ship_id = str(ent.get('visual_ship_id') or '').strip()
                visual_conf = float(ent.get('visual_confidence') or 0.0)
                if visual_ship_id:
                    conf_pct = max(0.0, min(1.0, visual_conf)) * 100.0
                    cv2.putText(
                        display_frame,
                        f"VEC: {visual_ship_id} ({conf_pct:.1f}%)",
                        (int(b[0]), y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.52,
                        (120, 255, 120),
                        2,
                    )

    if frame_captured_mono is not None:
        sync_label = format_capture_wall_clock(frame_captured_mono, camera_id=camera_id)
        cv2.putText(
            display_frame,
            sync_label,
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (80, 220, 255),
            2,
        )

    cv2.putText(
        display_frame,
        f"FPS: {fps:.1f}",
        (10, 58 if frame_captured_mono is not None else 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2,
    )

    n_conf = sum(1 for t in tracked_boats if t.state == TrackState.CONFIRMED)
    cv2.putText(
        display_frame,
        f"confirmed: {n_conf}",
        (10, 88 if frame_captured_mono is not None else 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (200, 255, 200),
        2,
    )

    if resize_scale != 1.0:
        hh, ww = display_frame.shape[:2]
        display_frame = cv2.resize(
            display_frame,
            (int(ww * resize_scale), int(hh * resize_scale)),
        )

    return display_frame

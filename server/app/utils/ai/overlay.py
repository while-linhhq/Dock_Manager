"""Vẽ overlay lên frame preview (det conf, global id, OCR, vector match, FPS)."""
from __future__ import annotations

import time

import cv2
import numpy as np

from app.services.ai.boat_tracker import TrackedBoat, TrackState
from app.services.ai.ship_id_lock import effective_ship_id
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


def berth_zone_overlay_line(
    overlap: float | None,
    threshold: float | None,
) -> tuple[str, tuple[int, int, int]] | None:
    """Return (label, bgr_color) e.g. ('ZONE: 42% / 30%', green)."""
    if overlap is None or threshold is None:
        return None
    pct = int(round(max(0.0, min(1.0, overlap)) * 100))
    thr = int(round(max(0.0, min(1.0, threshold)) * 100))
    label = f'ZONE: {pct}% / {thr}%'
    if overlap >= threshold:
        color = (80, 220, 80)
    elif overlap >= threshold * 0.85:
        color = (0, 210, 255)
    else:
        color = (80, 80, 255)
    return label, color


def ocr_overlay_line(entry: dict | None) -> str:
    """Always include OCR label; value empty when OCR has not run yet."""
    text = str((entry or {}).get('text') or '').strip()
    return f'OCR: {text}'


def emb_overlay_line(entry: dict | None) -> str:
    """EMB from Qdrant top hit only — never echo OCR-hint fusion fallback."""
    emb_id = str((entry or {}).get('visual_emb_ship_id') or '').strip()
    if not emb_id:
        return 'EMB:'
    emb_conf = float((entry or {}).get('visual_emb_confidence') or 0.0)
    conf_pct = max(0.0, min(1.0, emb_conf)) * 100.0
    return f'EMB: {emb_id} ({conf_pct:.1f}%)'


def final_overlay_line(track: TrackedBoat, entry: dict | None) -> str:
    source = str((entry or {}).get('visual_source') or 'ocr').strip()
    final_id = str(effective_ship_id(track) or 'N/A')
    lock_suffix = ' [LOCK]' if track.ship_id_locked else ''
    return f'Final: {final_id} [{source}]{lock_suffix}'


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
    zone_threshold: float | None = None,
):
    """
    Vẽ 3 dòng trên bbox: gid / trk+state / det conf.
    Vẽ 3 dòng dưới bbox: OCR / EMB / Final (từ ocr_cache).
    """
    now = time.time()

    for tb in tracked_boats:
        b = tb.box
        x1 = int(b[0])
        y1 = int(b[1])

        gid_label = f"gid: {tb.global_id or tb.track_id}"
        cv2.putText(
            display_frame,
            gid_label,
            (x1, y1 - 86),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (200, 160, 255),
            2,
        )

        trk_label = f"trk: {tb.track_id} [{tb.state.value}]"
        cv2.putText(
            display_frame,
            trk_label,
            (x1, y1 - 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 180, 180),
            2,
        )

        bw = int(b[2] - b[0])
        bh = int(b[3] - b[1])
        cv2.putText(
            display_frame,
            f"det: {tb.conf:.2f}  {bw}x{bh}",
            (x1, y1 - 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 220, 255),
            2,
        )

        zone_line = berth_zone_overlay_line(
            tb.berth_zone_overlap,
            zone_threshold if zone_threshold is not None else tb.berth_zone_threshold,
        )
        if zone_line is not None:
            zone_text, zone_color = zone_line
            cv2.putText(
                display_frame,
                zone_text,
                (x1, y1 - 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                zone_color,
                2,
            )

    if ocr_cache is not None and ocr_lock is not None:
        with ocr_lock:
            for k in list(ocr_cache.keys()):
                if now - ocr_cache[k]['time'] >= ocr_label_ttl:
                    del ocr_cache[k]
            for tb in tracked_boats:
                ck = ocr_cache_key_track(tb.track_id, tb.camera_id)
                ent = ocr_cache.get(ck)
                b = tb.box
                y_base = min(int(b[3]) + 24, display_frame.shape[0] - 6)

                cv2.putText(
                    display_frame,
                    ocr_overlay_line(ent if isinstance(ent, dict) else None),
                    (int(b[0]), y_base),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 220, 255),
                    2,
                )
                y_base = min(y_base + 20, display_frame.shape[0] - 6)

                cv2.putText(
                    display_frame,
                    emb_overlay_line(ent if isinstance(ent, dict) else None),
                    (int(b[0]), y_base),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    (120, 255, 120),
                    2,
                )
                y_base = min(y_base + 20, display_frame.shape[0] - 6)

                cv2.putText(
                    display_frame,
                    final_overlay_line(tb, ent if isinstance(ent, dict) else None),
                    (int(b[0]), y_base),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    (255, 220, 80),
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

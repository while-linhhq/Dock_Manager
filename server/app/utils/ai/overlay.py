"""Vẽ overlay lên frame preview (det conf, track id/state, OCR label, FPS)."""
from __future__ import annotations

import time

import cv2

from app.services.ai.boat_tracker import TrackedBoat, TrackState
from app.utils.ai.pipeline_utils import ocr_cache_key_track


def draw_ship_detection_overlay(
    display_frame,
    tracked_boats: list[TrackedBoat],
    ocr_cache: dict | None,
    ocr_lock,
    ocr_label_ttl: float,
    fps: float,
    resize_scale: float,
):
    """
    Vẽ det confidence, track id + state, nhãn OCR (theo TTL), FPS; resize nếu resize_scale != 1.
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
        label = f"T{tb.track_id} [{tb.state.value}]"
        cv2.putText(
            display_frame,
            label,
            (int(b[0]), int(b[1]) - 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (220, 220, 100),
            2,
        )

    for tb in tracked_boats:
        if tb.ship_id:
            b = tb.box
            cv2.putText(
                display_frame,
                tb.ship_id,
                (int(b[0]), int(b[1]) - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2,
            )

    if ocr_cache is not None and ocr_lock is not None:
        with ocr_lock:
            for k in list(ocr_cache.keys()):
                if now - ocr_cache[k]["time"] >= ocr_label_ttl:
                    del ocr_cache[k]

    cv2.putText(
        display_frame,
        f"FPS: {fps:.1f}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2,
    )

    n_conf = sum(1 for t in tracked_boats if t.state == TrackState.CONFIRMED)
    cv2.putText(
        display_frame,
        f"confirmed: {n_conf}",
        (10, 60),
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

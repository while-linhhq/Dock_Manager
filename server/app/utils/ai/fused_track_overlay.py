"""Draw per-camera tracker boxes onto a fused layout canvas (fast preview/video path)."""
from __future__ import annotations

from collections.abc import Callable
import time

import cv2
import numpy as np

from app.services.ai.boat_tracker import TrackState, TrackedBoat
from app.services.ai.frame_fusion import FusionMember, map_detection_box_to_fused_layout
from app.services.ai.multi_frame_reader import TimedFrame
from app.utils.ai.overlay import (
    BERTH_FILL_ALPHA,
    berth_fill_color_for_state,
    berth_zone_overlay_line,
    emb_overlay_line,
    final_overlay_line,
    ocr_overlay_line,
    resolve_berth_visual_state,
    tint_bbox_overlay,
)
from app.utils.ai.pipeline_utils import ocr_cache_key_track

TrackProvider = Callable[[], list[TrackedBoat]]

_COLOR_TENTATIVE = (128, 128, 128)
_COLOR_CONFIRMED = (0, 255, 0)
_COLOR_LOST = (0, 165, 255)
_PANEL_BG = (18, 24, 32)
_PANEL_ALPHA = 0.72
_TEXT_PRIMARY = (245, 245, 245)
_TEXT_SECONDARY = (210, 210, 210)
_TEXT_OCR = (0, 220, 255)
_TEXT_EMB = (120, 255, 120)
_TEXT_FINAL = (255, 220, 80)


def _color_for_track(track: TrackedBoat) -> tuple[int, int, int]:
    if track.state == TrackState.TENTATIVE:
        return _COLOR_TENTATIVE
    if track.state == TrackState.LOST:
        return _COLOR_LOST
    return _COLOR_CONFIRMED


def _draw_text_with_bg(
    frame: np.ndarray,
    lines: list[tuple[str, tuple[int, int, int], float]],
    x: int,
    y_bottom: int,
) -> None:
    if not lines:
        return
    padding_x = 6
    padding_y = 5
    line_gap = 4
    max_width = 0
    total_height = padding_y
    metrics: list[tuple[int, int, int, tuple[int, int, int], float]] = []
    for text, color, scale in lines:
        (width, height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        metrics.append((width, height, baseline, color, scale))
        max_width = max(max_width, width)
        total_height += height + baseline + line_gap
    total_height += padding_y - line_gap

    x1 = max(0, int(x))
    y2 = max(total_height, int(y_bottom))
    y1 = max(0, y2 - total_height)
    x2 = min(frame.shape[1], x1 + max_width + padding_x * 2)
    if x2 <= x1 or y2 <= y1:
        return

    roi = frame[y1:y2, x1:x2]
    panel = np.full_like(roi, _PANEL_BG, dtype=np.uint8)
    cv2.addWeighted(panel, _PANEL_ALPHA, roi, 1.0 - _PANEL_ALPHA, 0, roi)

    text_y = y1 + padding_y
    for text, (_width, height, baseline, color, scale) in zip(
        (line[0] for line in lines),
        metrics,
        strict=False,
    ):
        text_y += height
        origin = (x1 + padding_x, text_y)
        cv2.putText(
            frame,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 0),
            3,
            lineType=cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            text,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            1,
            lineType=cv2.LINE_AA,
        )
        text_y += baseline + line_gap


def draw_fused_track_overlay(
    fused: np.ndarray,
    *,
    members_by_camera: dict[int, FusionMember],
    batch: dict[int, TimedFrame],
    track_providers: list[TrackProvider],
    ocr_cache: dict | None = None,
    ocr_lock=None,
    ocr_label_ttl: float = 0.0,
) -> np.ndarray:
    """Mutates and returns fused BGR image with tracker overlays."""
    if fused is None or fused.size == 0:
        return fused

    canvas_h, canvas_w = fused.shape[:2]
    now = None
    if ocr_cache is not None and ocr_lock is not None:
        now = float(time.time())
        with ocr_lock:
            for key in list(ocr_cache.keys()):
                try:
                    if now - float(ocr_cache[key].get('time', 0.0)) >= float(ocr_label_ttl):
                        del ocr_cache[key]
                except Exception:
                    del ocr_cache[key]
    for provider in track_providers:
        try:
            tracks = provider()
        except Exception:
            continue
        for track in tracks:
            camera_id = int(track.camera_id) if track.camera_id is not None else None
            if camera_id is None:
                continue
            member = members_by_camera.get(camera_id)
            timed = batch.get(camera_id)
            if member is None or timed is None or timed.frame is None:
                continue
            source_h, source_w = timed.frame.shape[:2]
            mapped = map_detection_box_to_fused_layout(
                track.box,
                member,
                source_h,
                source_w,
            )
            if mapped is None:
                continue
            x1, y1, x2, y2 = mapped
            x1 = max(0, min(canvas_w - 1, x1))
            y1 = max(0, min(canvas_h - 1, y1))
            x2 = max(0, min(canvas_w, x2))
            y2 = max(0, min(canvas_h, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            berth_state = resolve_berth_visual_state(track)
            if berth_state is not None:
                tint_bbox_overlay(
                    fused,
                    x1,
                    y1,
                    x2,
                    y2,
                    berth_fill_color_for_state(berth_state),
                    BERTH_FILL_ALPHA,
                )
            color = _color_for_track(track)
            cv2.rectangle(fused, (x1, y1), (x2, y2), color, 2)
            cache_key = ocr_cache_key_track(track.track_id, track.camera_id)
            entry = None
            if ocr_cache is not None and ocr_lock is not None:
                with ocr_lock:
                    cached = ocr_cache.get(cache_key)
                    if isinstance(cached, dict):
                        entry = dict(cached)

            panel_lines: list[tuple[str, tuple[int, int, int], float]] = [
                (f'ID {track.global_id or track.track_id}', _TEXT_SECONDARY, 0.38),
                (
                    f'{track.ship_id or f"T{track.track_id}"} [{track.state.value}]',
                    _TEXT_PRIMARY,
                    0.48,
                ),
            ]
            zone_line = berth_zone_overlay_line(
                track.berth_zone_overlap,
                track.berth_zone_threshold,
            )
            if zone_line is not None:
                zone_text, zone_color = zone_line
                panel_lines.append((zone_text.replace('ZONE: ', 'ZONE '), zone_color, 0.38))

            cache_entry = entry if isinstance(entry, dict) else None
            ocr_panel = ocr_overlay_line(cache_entry).replace('OCR: ', 'OCR ', 1)
            emb_panel = emb_overlay_line(cache_entry).replace('EMB: ', 'EMB ', 1)
            panel_lines.append((ocr_panel, _TEXT_OCR, 0.38))
            panel_lines.append((emb_panel, _TEXT_EMB, 0.38))
            panel_lines.append(
                (
                    final_overlay_line(track, cache_entry).replace('Final: ', 'FINAL ', 1),
                    _TEXT_FINAL,
                    0.40,
                )
            )

            panel_bottom = min(canvas_h - 4, y1 - 4) if y1 > 72 else min(canvas_h - 4, y2 + 72)
            _draw_text_with_bg(fused, panel_lines, x1, panel_bottom)
    return fused

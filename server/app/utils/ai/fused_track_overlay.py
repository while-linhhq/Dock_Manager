"""Draw per-camera tracker boxes onto a fused layout canvas (fast preview/video path)."""
from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

from app.services.ai.boat_tracker import TrackState, TrackedBoat
from app.services.ai.frame_fusion import FusionMember, map_detection_box_to_fused_layout
from app.services.ai.multi_frame_reader import TimedFrame

TrackProvider = Callable[[], list[TrackedBoat]]

_COLOR_TENTATIVE = (128, 128, 128)
_COLOR_CONFIRMED = (0, 255, 0)
_COLOR_LOST = (0, 165, 255)


def _color_for_track(track: TrackedBoat) -> tuple[int, int, int]:
    if track.state == TrackState.TENTATIVE:
        return _COLOR_TENTATIVE
    if track.state == TrackState.LOST:
        return _COLOR_LOST
    return _COLOR_CONFIRMED


def draw_fused_track_overlay(
    fused: np.ndarray,
    *,
    members_by_camera: dict[int, FusionMember],
    batch: dict[int, TimedFrame],
    track_providers: list[TrackProvider],
) -> np.ndarray:
    """Mutates and returns fused BGR image with tracker overlays."""
    if fused is None or fused.size == 0:
        return fused

    canvas_h, canvas_w = fused.shape[:2]
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
            color = _color_for_track(track)
            cv2.rectangle(fused, (x1, y1), (x2, y2), color, 2)
            label = track.ship_id or f'T{track.track_id}'
            cv2.putText(
                fused,
                label,
                (x1, max(12, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                2,
            )
    return fused

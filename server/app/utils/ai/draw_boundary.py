from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.services.ai.boundary_crossing import BoundaryConfig, polyline_segments
from app.services.ai.frame_fusion import FusionMember, map_camera_point_to_fused_layout


def _draw_polyline(
    frame: np.ndarray,
    points: list[tuple[float, float]],
    color: tuple[int, int, int],
    label: str,
    *,
    sx: float,
    sy: float,
) -> None:
    if len(points) < 2:
        return
    scaled = [(int(p[0] * sx), int(p[1] * sy)) for p in points]
    for seg in polyline_segments(scaled):
        cv2.line(frame, (int(seg[0]), int(seg[1])), (int(seg[2]), int(seg[3])), color, 2)
    cv2.putText(frame, label, scaled[0], cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def draw_boundary_lines(
    frame: np.ndarray,
    config: BoundaryConfig | None,
) -> np.ndarray:
    if config is None or frame is None or frame.size == 0:
        return frame
    h, w = frame.shape[:2]
    sx = w / max(1, config.frame_w)
    sy = h / max(1, config.frame_h)
    _draw_polyline(frame, config.line1, (0, 200, 0), 'L1', sx=sx, sy=sy)
    _draw_polyline(frame, config.line2, (0, 0, 255), 'L2', sx=sx, sy=sy)
    return frame


def draw_boundary_lines_on_fused(
    fused: np.ndarray,
    *,
    members: list[Any],
    boundary_by_camera: dict[int, dict | None],
    frame_shapes: dict[int, tuple[int, int]] | None = None,
) -> np.ndarray:
    if fused is None or fused.size == 0:
        return fused

    for member in members:
        camera_id = int(member.camera_id)
        raw = boundary_by_camera.get(camera_id)
        config = BoundaryConfig.from_dict(raw)
        if config is None:
            continue

        src_h, src_w = (frame_shapes or {}).get(camera_id, (config.frame_h, config.frame_w))
        fusion_member = member if isinstance(member, FusionMember) else FusionMember(
            camera_id=camera_id,
            layout_x=int(getattr(member, 'layout_x', 0) or 0),
            layout_y=int(getattr(member, 'layout_y', 0) or 0),
            layout_w=getattr(member, 'layout_w', None),
            layout_h=getattr(member, 'layout_h', None),
            layout_rotation=float(getattr(member, 'layout_rotation', 0) or 0),
            crop_top=int(getattr(member, 'crop_top', 0) or 0),
            crop_bottom=int(getattr(member, 'crop_bottom', 0) or 0),
            crop_left=int(getattr(member, 'crop_left', 0) or 0),
            crop_right=int(getattr(member, 'crop_right', 0) or 0),
            enabled=bool(getattr(member, 'enabled', True)),
        )

        for points, color, label in (
            (config.line1, (0, 200, 0), 'L1'),
            (config.line2, (0, 0, 255), 'L2'),
        ):
            mapped: list[tuple[int, int]] = []
            for px, py in points:
                pt = map_camera_point_to_fused_layout(
                    px, py, fusion_member, src_h, src_w
                )
                if pt is not None:
                    mapped.append(pt)
            if len(mapped) < 2:
                continue
            for i in range(len(mapped) - 1):
                cv2.line(fused, mapped[i], mapped[i + 1], color, 2)
            cv2.putText(fused, label, mapped[0], cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return fused

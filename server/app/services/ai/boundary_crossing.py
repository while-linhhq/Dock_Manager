from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Point = tuple[float, float]
Segment = tuple[float, float, float, float]  # x1, y1, x2, y2
Polyline = list[Point]


def segment_intersection_t(p0: Point, p1: Point, line: Segment) -> Optional[float]:
    """Return param t in [0,1] along p0->p1 where it crosses the line segment, else None."""
    x1, y1, x2, y2 = line
    px, py = p1[0] - p0[0], p1[1] - p0[1]
    lx, ly = x2 - x1, y2 - y1
    denom = px * ly - py * lx
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - p0[0]) * ly - (y1 - p0[1]) * lx) / denom
    u = ((x1 - p0[0]) * py - (y1 - p0[1]) * px) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t
    return None


def polyline_segments(points: Polyline) -> list[Segment]:
    if len(points) < 2:
        return []
    return [
        (points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    ]


def _parse_polyline(raw: object) -> Optional[Polyline]:
    if isinstance(raw, list):
        points: Polyline = []
        for item in raw:
            if not isinstance(item, dict):
                return None
            points.append((float(item['x']), float(item['y'])))
        return points if len(points) >= 2 else None
    if isinstance(raw, dict) and 'x1' in raw:
        return [
            (float(raw['x1']), float(raw['y1'])),
            (float(raw['x2']), float(raw['y2'])),
        ]
    return None


@dataclass
class BoundaryConfig:
    frame_w: int
    frame_h: int
    line1: Polyline
    line2: Polyline
    enabled: bool = True
    window_sec: float = 120.0

    @classmethod
    def from_dict(cls, data: dict | None) -> Optional['BoundaryConfig']:
        if not data or not data.get('enabled', True):
            return None
        try:
            line1 = _parse_polyline(data.get('line1'))
            line2 = _parse_polyline(data.get('line2'))
            if line1 is None or line2 is None:
                return None
            return cls(
                frame_w=int(data['frame_w']),
                frame_h=int(data['frame_h']),
                line1=line1,
                line2=line2,
                enabled=bool(data.get('enabled', True)),
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass
class _TrackState:
    last_center: Optional[Point] = None
    pending_line: Optional[int] = None  # 1 or 2
    pending_ts: float = 0.0


class BoundaryCrossingTracker:
    def __init__(self, config: BoundaryConfig) -> None:
        self._cfg = config
        self._states: dict[str, _TrackState] = {}

    @property
    def config(self) -> BoundaryConfig:
        return self._cfg

    def _scaled_polyline(
        self, points: Polyline, frame_w: int, frame_h: int
    ) -> Polyline:
        sx = frame_w / max(1, self._cfg.frame_w)
        sy = frame_h / max(1, self._cfg.frame_h)
        return [(p[0] * sx, p[1] * sy) for p in points]

    def _earliest_crossing_t(
        self,
        prev: Point,
        center: Point,
        polyline: Polyline,
    ) -> Optional[float]:
        best: Optional[float] = None
        for seg in polyline_segments(polyline):
            t = segment_intersection_t(prev, center, seg)
            if t is not None and (best is None or t < best):
                best = t
        return best

    def update(
        self,
        track_id: str,
        center: Point,
        ts: float,
        frame_w: int,
        frame_h: int,
    ) -> Optional[str]:
        st = self._states.get(track_id)
        if st is None:
            st = _TrackState()
            self._states[track_id] = st
        prev = st.last_center
        st.last_center = center
        if prev is None:
            return None

        l1 = self._scaled_polyline(self._cfg.line1, frame_w, frame_h)
        l2 = self._scaled_polyline(self._cfg.line2, frame_w, frame_h)
        crossed: list[tuple[float, int]] = []
        t1 = self._earliest_crossing_t(prev, center, l1)
        t2 = self._earliest_crossing_t(prev, center, l2)
        if t1 is not None:
            crossed.append((t1, 1))
        if t2 is not None:
            crossed.append((t2, 2))
        crossed.sort()

        event: Optional[str] = None
        for _, line_id in crossed:
            if st.pending_line is not None and ts - st.pending_ts > self._cfg.window_sec:
                st.pending_line = None
            if st.pending_line is None or st.pending_line == line_id:
                st.pending_line = line_id
                st.pending_ts = ts
            else:
                if st.pending_line == 1 and line_id == 2:
                    event = 'in'
                elif st.pending_line == 2 and line_id == 1:
                    event = 'out'
                st.pending_line = None
        return event

    def forget(self, active_ids: set[str]) -> None:
        for tid in list(self._states):
            if tid not in active_ids:
                del self._states[tid]


def apply_boundary_lines_update(
    *,
    camera_id: int,
    payload: dict | None,
) -> None:
    """Push new boundary config to live preview streams and running pipeline."""
    from app.services.editor_preview import editor_preview_manager
    from app.services.pipeline_service import pipeline_service

    editor_preview_manager.set_boundary_lines(int(camera_id), payload)
    pipeline_service.update_camera_boundary_lines(int(camera_id), payload)

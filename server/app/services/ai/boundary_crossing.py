from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Point = tuple[float, float]
Segment = tuple[float, float, float, float]  # x1, y1, x2, y2
Polyline = list[Point]
Bbox = tuple[float, float, float, float]  # x1, y1, x2, y2
TrackPhase = Literal['outside', 'inside', 'completed']


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


def _parse_polyline(raw: object, *, min_points: int = 2) -> Optional[Polyline]:
    if isinstance(raw, list):
        points: Polyline = []
        for item in raw:
            if not isinstance(item, dict):
                return None
            points.append((float(item['x']), float(item['y'])))
        return points if len(points) >= min_points else None
    if isinstance(raw, dict) and 'x1' in raw:
        return [
            (float(raw['x1']), float(raw['y1'])),
            (float(raw['x2']), float(raw['y2'])),
        ]
    return None


def _normalize_box(box: Bbox) -> Bbox:
    x1, y1, x2, y2 = box
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _signed_polygon_area(vertices: Polyline) -> float:
    if len(vertices) < 3:
        return 0.0
    area = 0.0
    for i in range(len(vertices)):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % len(vertices)]
        area += x1 * y2 - x2 * y1
    return area * 0.5


def _polygon_area(vertices: list[Point]) -> float:
    return abs(_signed_polygon_area(vertices))


def _ensure_ccw_polygon(polygon: Polyline) -> Polyline:
    """Clipper expects interior on the left of each edge (CCW in image coords)."""
    if len(polygon) < 3:
        return polygon
    if _signed_polygon_area(polygon) < 0:
        return list(reversed(polygon))
    return polygon


def _bbox_corners(box: Bbox) -> list[Point]:
    x1, y1, x2, y2 = _normalize_box(box)
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def _clip_polygon_by_halfplane(
    vertices: list[Point],
    anchor: Point,
    normal: tuple[float, float],
) -> list[Point]:
    """Keep vertices inside half-plane (signed distance >= 0)."""
    if not vertices:
        return []

    def signed_distance(point: Point) -> float:
        return (point[0] - anchor[0]) * normal[0] + (point[1] - anchor[1]) * normal[1]

    def inside(point: Point) -> bool:
        return signed_distance(point) >= -1e-9

    def intersect(p1: Point, p2: Point) -> Point:
        d1 = signed_distance(p1)
        d2 = signed_distance(p2)
        denom = d1 - d2
        if abs(denom) < 1e-12:
            return p1
        t = d1 / denom
        return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))

    output: list[Point] = []
    previous = vertices[-1]
    for current in vertices:
        previous_inside = inside(previous)
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                output.append(intersect(previous, current))
            output.append(current)
        elif previous_inside:
            output.append(intersect(previous, current))
        previous = current
    return output


def _clip_polygon_by_segment_edge(
    subject: list[Point],
    edge_start: Point,
    edge_end: Point,
) -> list[Point]:
    """Clip subject polygon to the inside of a convex polygon edge (CCW half-plane)."""
    dx = edge_end[0] - edge_start[0]
    dy = edge_end[1] - edge_start[1]
    inward = (-dy, dx)
    return _clip_polygon_by_halfplane(subject, edge_start, inward)


def bbox_fraction_inside_polygon(box: Bbox, polygon: Polyline) -> float:
    """Area(bbox ∩ polygon) / area(bbox). Polygon is closed implicitly."""
    if len(polygon) < 3:
        return 0.0

    polygon = _ensure_ccw_polygon(polygon)
    x1, y1, x2, y2 = _normalize_box(box)
    bbox_area = max(0.0, (x2 - x1) * (y2 - y1))
    if bbox_area < 1e-9:
        return 0.0

    clipped = _bbox_corners(box)
    n = len(polygon)
    for i in range(n):
        clipped = _clip_polygon_by_segment_edge(
            clipped,
            polygon[i],
            polygon[(i + 1) % n],
        )
        if not clipped:
            return 0.0
    return min(1.0, _polygon_area(clipped) / bbox_area)


def _segments_intersect(seg_a: Segment, seg_b: Segment) -> bool:
    return segment_intersection_t(
        (seg_a[0], seg_a[1]),
        (seg_a[2], seg_a[3]),
        seg_b,
    ) is not None


def polyline_touches_bbox(polyline: Polyline, box: Bbox) -> bool:
    """True if any polyline segment intersects the bbox rectangle border."""
    x1, y1, x2, y2 = _normalize_box(box)
    bbox_edges: list[Segment] = [
        (x1, y1, x2, y1),
        (x2, y1, x2, y2),
        (x2, y2, x1, y2),
        (x1, y2, x1, y1),
    ]
    for seg in polyline_segments(polyline):
        for edge in bbox_edges:
            if _segments_intersect(seg, edge):
                return True
    return False


def resolve_bbox_cross_threshold(payload: dict | None, *, default: float = 0.30) -> float:
    """Read per-camera berth zone overlap threshold from cameras.boundary_lines JSON."""
    if not isinstance(payload, dict):
        return default
    raw_threshold = payload.get('bbox_cross_threshold', default)
    try:
        threshold = float(raw_threshold)
    except (TypeError, ValueError):
        return default
    # Legacy/admin payloads may store whole percents (40) instead of fractions (0.40).
    if threshold > 1.0:
        threshold = threshold / 100.0
    return max(0.05, min(0.95, threshold))


@dataclass
class BoundaryConfig:
    frame_w: int
    frame_h: int
    line1: Polyline
    line2: Polyline
    berth_zone: Polyline
    enabled: bool = True
    window_sec: float = 120.0
    bbox_cross_threshold: float = 0.30

    @classmethod
    def _parse_common(cls, data: dict, *, require_berth_zone: bool) -> Optional['BoundaryConfig']:
        line1 = _parse_polyline(data.get('line1'))
        line2 = _parse_polyline(data.get('line2'))
        if line1 is None or line2 is None:
            return None
        berth_zone = _parse_polyline(data.get('berth_zone'), min_points=3)
        if require_berth_zone and berth_zone is None:
            return None
        threshold = resolve_bbox_cross_threshold(data)
        return cls(
            frame_w=int(data['frame_w']),
            frame_h=int(data['frame_h']),
            line1=line1,
            line2=line2,
            berth_zone=berth_zone or [],
            enabled=bool(data.get('enabled', True)),
            bbox_cross_threshold=threshold,
        )

    @classmethod
    def from_dict(cls, data: dict | None) -> Optional['BoundaryConfig']:
        if not data or not data.get('enabled', True):
            return None
        try:
            return cls._parse_common(data, require_berth_zone=True)
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def for_overlay(cls, data: dict | None) -> Optional['BoundaryConfig']:
        """Parse boundary geometry for preview overlay (berth_zone optional)."""
        if not data or not data.get('enabled', True):
            return None
        try:
            return cls._parse_common(data, require_berth_zone=False)
        except (KeyError, TypeError, ValueError):
            return None


@dataclass
class _TrackState:
    last_box: Optional[Bbox] = None
    phase: TrackPhase = 'outside'
    pending_line: Optional[int] = None
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

    def _frame_box(self, box: Bbox) -> Bbox:
        """Detector boxes are already in live frame pixel space; only normalize."""
        return _normalize_box(box)

    def _zone_overlap_ratio(
        self,
        box: Bbox,
        frame_w: int,
        frame_h: int,
    ) -> float:
        scaled_zone = self._scaled_polyline(self._cfg.berth_zone, frame_w, frame_h)
        return bbox_fraction_inside_polygon(box, scaled_zone)

    def zone_overlap_ratio(
        self,
        box: Bbox,
        frame_w: int,
        frame_h: int,
    ) -> float:
        """Fraction of bbox area inside berth_zone (0.0–1.0), scaled to current frame."""
        return self._zone_overlap_ratio(self._frame_box(box), frame_w, frame_h)

    def _line_touches_with_history(
        self,
        prev_box: Optional[Bbox],
        curr_box: Bbox,
        polyline: Polyline,
        frame_w: int,
        frame_h: int,
    ) -> bool:
        scaled = self._scaled_polyline(polyline, frame_w, frame_h)
        if polyline_touches_bbox(scaled, curr_box):
            return True
        if prev_box is not None:
            return polyline_touches_bbox(scaled, prev_box)
        return False

    def update(
        self,
        track_id: str,
        box: Bbox,
        ts: float,
        frame_w: int,
        frame_h: int,
    ) -> Optional[str]:
        st = self._states.get(track_id)
        if st is None:
            st = _TrackState()
            self._states[track_id] = st

        prev_box = st.last_box
        frame_box = self._frame_box(box)
        st.last_box = frame_box

        if st.phase == 'completed':
            return None

        overlap = self._zone_overlap_ratio(frame_box, frame_w, frame_h)
        threshold = self._cfg.bbox_cross_threshold

        if st.phase == 'inside':
            if overlap < threshold:
                st.phase = 'completed'
                st.pending_line = None
                return 'out'
            return None

        if st.pending_line is not None and ts - st.pending_ts > self._cfg.window_sec:
            st.pending_line = None

        l1_hit = self._line_touches_with_history(
            prev_box, frame_box, self._cfg.line1, frame_w, frame_h
        )
        l2_hit = self._line_touches_with_history(
            prev_box, frame_box, self._cfg.line2, frame_w, frame_h
        )

        if st.phase == 'outside':
            # Seed 'inside' khi track XUẤT HIỆN LẦN ĐẦU đã nằm gọn trong berth_zone
            # (overlap >= threshold, không chạm line nào). Xảy ra khi: track-id đổi
            # giữa vùng neo, hoặc camera nhận handoff và chỉ thấy tàu SAU khi nó đã
            # vào zone (điển hình là camera chứng kiến cảnh RA). Máy trạng thái chưa
            # từng thấy chuỗi line1→line2 nên sẽ kẹt 'outside' và KHÔNG BAO GIỜ phát
            # 'out' → OUT rơi về fallback last_seen. Seed thẳng 'inside' để khi
            # overlap tụt < threshold sẽ phát 'out' đúng. KHÔNG phát 'in' (đây không
            # phải arrival thật — berth_in do camera gốc giữ), tránh berth_in giả.
            # Điều kiện `not l1_hit and not l2_hit` phân biệt track sinh-giữa-vùng với
            # track đang băng qua ranh giới (track cross line vẫn đi path line1→line2).
            if (
                prev_box is None
                and overlap >= threshold
                and not l1_hit
                and not l2_hit
            ):
                st.phase = 'inside'
                st.pending_line = None
                return None
            if l1_hit and st.pending_line is None:
                st.pending_line = 1
                st.pending_ts = ts
            elif l2_hit and st.pending_line is None:
                st.pending_line = None
            elif l2_hit and st.pending_line == 1:
                if overlap >= threshold:
                    st.phase = 'inside'
                    st.pending_line = None
                    return 'in'
                st.pending_line = None

        return None

    def forget(self, active_ids: set[str]) -> None:
        for tid in list(self._states):
            if tid not in active_ids:
                del self._states[tid]

    def get_phase(self, track_id: str) -> TrackPhase:
        st = self._states.get(track_id)
        return st.phase if st is not None else 'outside'


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

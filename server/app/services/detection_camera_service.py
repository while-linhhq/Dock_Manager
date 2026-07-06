"""Resolve camera IN/OUT cho detection từ boundary_crossing_events.

Detection không lưu camera_id trực tiếp. Camera lúc tàu IN/OUT vùng neo đậu
được ghi trong boundary_crossing_events (direction 'in'/'out') theo track_id.
Batch resolver để tránh N+1 khi list nhiều detection.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.boundary_crossing_event import BoundaryCrossingEvent
from app.models.camera import Camera


def _camera_name_map(db: Session, camera_ids: set[int]) -> dict[int, str]:
    if not camera_ids:
        return {}
    rows = (
        db.query(Camera.id, Camera.camera_name)
        .filter(Camera.id.in_(sorted(camera_ids)))
        .all()
    )
    return {int(cid): str(name) for cid, name in rows}


def resolve_camera_in_out(
    db: Session,
    track_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Trả map track_id -> {in_camera_id, in_camera_name, out_camera_id, out_camera_name}.

    IN = event 'in' sớm nhất, OUT = event 'out' muộn nhất cho track đó.
    """
    ids = [t for t in {str(t).strip() for t in track_ids} if t]
    if not ids:
        return {}

    events = (
        db.query(
            BoundaryCrossingEvent.track_id,
            BoundaryCrossingEvent.direction,
            BoundaryCrossingEvent.camera_id,
            BoundaryCrossingEvent.crossed_at,
        )
        .filter(BoundaryCrossingEvent.track_id.in_(ids))
        .order_by(BoundaryCrossingEvent.crossed_at.asc())
        .all()
    )

    # in: giữ crossed_at nhỏ nhất; out: giữ crossed_at lớn nhất
    result: dict[str, dict[str, Any]] = {}
    camera_ids: set[int] = set()
    for track_id, direction, camera_id, crossed_at in events:
        if camera_id is None:
            continue
        tid = str(track_id)
        entry = result.setdefault(
            tid,
            {'in_camera_id': None, 'out_camera_id': None, '_in_ts': None, '_out_ts': None},
        )
        cid = int(camera_id)
        camera_ids.add(cid)
        if direction == 'in':
            if entry['_in_ts'] is None or crossed_at < entry['_in_ts']:
                entry['_in_ts'] = crossed_at
                entry['in_camera_id'] = cid
        elif direction == 'out':
            if entry['_out_ts'] is None or crossed_at > entry['_out_ts']:
                entry['_out_ts'] = crossed_at
                entry['out_camera_id'] = cid

    names = _camera_name_map(db, camera_ids)
    for entry in result.values():
        entry['in_camera_name'] = names.get(entry['in_camera_id']) if entry['in_camera_id'] else None
        entry['out_camera_name'] = names.get(entry['out_camera_id']) if entry['out_camera_id'] else None
        entry.pop('_in_ts', None)
        entry.pop('_out_ts', None)
    return result

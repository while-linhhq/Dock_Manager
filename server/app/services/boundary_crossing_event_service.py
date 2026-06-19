"""Ghi và truy vấn sự kiện vượt boundary line (INPUT/OUTPUT)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.boundary_crossing_event import BoundaryCrossingEvent

logger = logging.getLogger(__name__)


def record_boundary_crossing_event(
    *,
    camera_id: int,
    track_id: str,
    direction: str,
    crossed_at_ts: float,
    ship_id: str | None = None,
) -> None:
    """Ghi sự kiện vượt line (best-effort, không chặn pipeline)."""
    if direction not in ('in', 'out'):
        return

    crossed_at = datetime.fromtimestamp(float(crossed_at_ts), tz=timezone.utc)
    db = SessionLocal()
    try:
        db.add(
            BoundaryCrossingEvent(
                camera_id=int(camera_id),
                track_id=str(track_id),
                ship_id=str(ship_id) if ship_id else None,
                direction=direction,
                crossed_at=crossed_at,
            )
        )
        db.commit()
    except Exception as err:
        db.rollback()
        logger.warning(
            'boundary_crossing_event: failed to record camera=%s track=%s dir=%s: %s',
            camera_id,
            track_id,
            direction,
            err,
        )
    finally:
        db.close()


def count_boundary_crossings(
    db: Session,
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[int, int]:
    """Đếm INPUT (in) và OUTPUT (out) trong kỳ."""
    in_count = int(
        db.query(BoundaryCrossingEvent.id)
        .filter(
            BoundaryCrossingEvent.direction == 'in',
            BoundaryCrossingEvent.crossed_at >= start_utc,
            BoundaryCrossingEvent.crossed_at < end_utc,
        )
        .count()
    )
    out_count = int(
        db.query(BoundaryCrossingEvent.id)
        .filter(
            BoundaryCrossingEvent.direction == 'out',
            BoundaryCrossingEvent.crossed_at >= start_utc,
            BoundaryCrossingEvent.crossed_at < end_utc,
        )
        .count()
    )
    return in_count, out_count

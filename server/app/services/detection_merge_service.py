"""Post-hoc detection merge service.

After the pipeline creates a detection, call absorb_contained() to find any
older detections of the same vessel whose berth window is fully contained
within the new one, absorb them (soft-delete their UNPAID invoices and
themselves), and return the winner's id.

The winner is always the detection with the longest berth window duration.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.detection_repository import detection_repo

_log = logging.getLogger(__name__)


def absorb_contained(db: Session, detection_id: int) -> int:
    """Absorb detections of the same vessel whose berth window is fully
    contained within the new detection's berth window.

    Returns:
        The winner's detection id (may differ from detection_id if an older
        detection turns out to have a longer berth window).
    """
    new_det = detection_repo.get(db, detection_id)
    if new_det is None:
        _log.warning('detection_merge: detection %s not found, skipping', detection_id)
        return detection_id

    if new_det.berth_in_time is None or new_det.berth_out_time is None:
        return detection_id

    candidates = detection_repo.get_overlapping_by_vessel(
        db,
        vessel_id=new_det.vessel_id,
        berth_in=new_det.berth_in_time,
        berth_out=new_det.berth_out_time,
        exclude_id=new_det.id,
    )

    pool = [new_det] + [c for c in candidates if c.berth_in_time and c.berth_out_time]

    def _duration(d):
        return (d.berth_out_time - d.berth_in_time).total_seconds()

    winner = max(pool, key=_duration)

    now = datetime.now(timezone.utc)

    # Stage all mutations first, then commit once — avoids partial-commit
    # orphans when there are multiple losers, and prevents DetachedInstanceError
    # from mid-loop commits expiring SQLAlchemy attributes.
    for det in pool:
        if det.id == winner.id:
            continue

        for inv in list(det.invoices):
            if inv.payment_status == 'UNPAID' and inv.deleted_at is None:
                inv.deleted_at = now

        detection_repo.soft_delete(db, det.id)

        _log.info(
            'detection_merge: absorbed detection %s into winner %s',
            det.id,
            winner.id,
        )

    db.commit()

    return winner.id

"""Post-hoc detection merge service.

After the pipeline creates a detection, call absorb_contained() to find any
older detections of the same vessel whose berth/time window overlaps or is
contained within the new one, absorb them (soft-delete their UNPAID invoices
and themselves), and return the winner's id.

The winner is always the detection with the longest effective duration
(berth_out − berth_in, fallback end_time − berth_in).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.detection_repository import detection_repo

_log = logging.getLogger(__name__)


def _effective_end(det) -> datetime | None:
    """berth_out_time nếu có, fallback end_time (track mất giữa chừng).
    Normalize sang tz-aware UTC để tránh lỗi subtract naive/aware."""
    raw = det.berth_out_time or det.end_time
    if raw is None:
        return None
    if raw.tzinfo is None:
        return raw.replace(tzinfo=timezone.utc)
    return raw


def _effective_duration(det) -> float:
    """Thời lượng tính bằng giây. Trả 0 nếu thiếu mốc."""
    start = det.berth_in_time
    end = _effective_end(det)
    if start is None or end is None:
        return 0.0
    return max(0.0, (end - start).total_seconds())


def absorb_contained(db: Session, detection_id: int) -> int:
    """Absorb detections of the same vessel whose berth/time window overlaps
    or is contained within the new detection's window.

    Candidate chỉ cần có berth_in_time (berth_out_time có thể NULL — dùng
    end_time fallback). Detection đã accepted (is_accepted=True) được repo
    query loại ở tầng DB.

    Returns:
        The winner's detection id (may differ from detection_id if an older
        detection turns out to have a longer effective window).
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

    # Candidate phải có berth_in; berth_out có thể NULL (fallback end_time).
    pool = [new_det] + [c for c in candidates if c.berth_in_time is not None]

    winner = max(pool, key=_effective_duration)

    now = datetime.now(timezone.utc)

    for det in pool:
        if det.id == winner.id:
            continue

        for inv in list(det.invoices):
            if inv.payment_status == 'UNPAID' and inv.deleted_at is None:
                inv.deleted_at = now

        detection_repo.soft_delete(db, det.id)

        _log.info(
            'detection_merge: absorbed detection %s (dur=%.1fs) into winner %s (dur=%.1fs)',
            det.id,
            _effective_duration(det),
            winner.id,
            _effective_duration(winner),
        )

    db.commit()

    return winner.id

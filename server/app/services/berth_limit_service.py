"""Berth limit checks: per ship (ship_id), per calendar day/month (VN timezone).

Limit is configured on fee_config but applies independently to each vessel/ship:
e.g. limit 5/day means each ship may dock at most 5 times that day, not 5 total
across all ships sharing the fee config or vessel type.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.fee import FeeConfig
from app.models.vessel import Vessel
from app.repositories.fee_config_repository import fee_config_repo
from app.services.detection_invoice_service import is_unknown_ship_id

VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def _reference_dt(detection: Optional[Detection], fallback: Optional[datetime] = None) -> datetime:
    if detection is not None:
        return detection.start_time or detection.created_at or datetime.now(VN_TZ)
    if fallback is not None:
        if fallback.tzinfo is None:
            return fallback.replace(tzinfo=VN_TZ)
        return fallback.astimezone(VN_TZ)
    return datetime.now(VN_TZ)


def window_bounds_vn(reference: datetime, unit: str) -> tuple[datetime, datetime]:
    """Inclusive start, exclusive end in UTC for DB comparison."""
    if reference.tzinfo is None:
        ref_vn = reference.replace(tzinfo=VN_TZ)
    else:
        ref_vn = reference.astimezone(VN_TZ)

    if unit == 'day':
        start_vn = ref_vn.replace(hour=0, minute=0, second=0, microsecond=0)
        end_vn = start_vn + timedelta(days=1)
    elif unit == 'month':
        start_vn = ref_vn.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_vn.month == 12:
            end_vn = start_vn.replace(year=start_vn.year + 1, month=1)
        else:
            end_vn = start_vn.replace(month=start_vn.month + 1)
    else:
        raise ValueError(f'unsupported berth_limit_unit: {unit}')

    return start_vn.astimezone(ZoneInfo('UTC')), end_vn.astimezone(ZoneInfo('UTC'))


def _normalize_ship_id(ship_id: Optional[str]) -> Optional[str]:
    normalized = (ship_id or '').strip().upper()
    if not normalized or is_unknown_ship_id(normalized):
        return None
    return normalized


def _ship_detection_query(
    db: Session,
    *,
    vessel_id: Optional[int],
    ship_id: Optional[str],
):
    normalized_ship = _normalize_ship_id(ship_id)
    q = db.query(Detection)
    if normalized_ship:
        q = q.join(Vessel, Detection.vessel_id == Vessel.id).filter(
            func.upper(func.trim(Vessel.ship_id)) == normalized_ship,
        )
    elif vessel_id is not None:
        q = q.filter(Detection.vessel_id == vessel_id)
    else:
        return None
    return q


def count_ship_berths_in_window(
    db: Session,
    *,
    vessel_id: Optional[int],
    ship_id: Optional[str],
    window_start: datetime,
    window_end: datetime,
) -> int:
    """
    Count berth events (detections) for one ship in the window.
    Prefer ship_id so all rows for the same registered ship aggregate together.
    Fall back to vessel_id when ship_id is missing.
    """
    q = _ship_detection_query(db, vessel_id=vessel_id, ship_id=ship_id)
    if q is None:
        return 0

    time_col = func.coalesce(Detection.start_time, Detection.created_at)
    return int(
        q.filter(
            time_col >= window_start,
            time_col < window_end,
        ).count()
    )


def count_ship_berths_at_event(
    db: Session,
    *,
    vessel_id: Optional[int],
    ship_id: Optional[str],
    window_start: datetime,
    window_end: datetime,
    event_time: datetime,
    event_detection_id: Optional[int],
) -> int:
    """Berth ordinal for this ship in the window (including this detection)."""
    q = _ship_detection_query(db, vessel_id=vessel_id, ship_id=ship_id)
    if q is None:
        return 0

    time_col = func.coalesce(Detection.start_time, Detection.created_at)
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=ZoneInfo('UTC'))
    else:
        event_time = event_time.astimezone(ZoneInfo('UTC'))

    in_window = and_(time_col >= window_start, time_col < window_end)
    if event_detection_id is not None:
        at_or_before = or_(
            time_col < event_time,
            and_(time_col == event_time, Detection.id <= event_detection_id),
        )
    else:
        at_or_before = time_col <= event_time

    return int(q.filter(in_window, at_or_before).count())


def _fee_has_berth_limit(fee: FeeConfig) -> bool:
    count = fee.berth_limit_count
    unit = (fee.berth_limit_unit or '').strip().lower()
    return count is not None and count > 0 and unit in ('day', 'month')


def _fees_with_berth_limits(fees: Sequence[FeeConfig]) -> list[FeeConfig]:
    return [fee for fee in fees if _fee_has_berth_limit(fee)]


def is_over_limit_for_fee(
    db: Session,
    *,
    vessel_id: Optional[int],
    ship_id: Optional[str],
    fee: FeeConfig,
    reference: datetime,
    event_time: Optional[datetime] = None,
    event_detection_id: Optional[int] = None,
) -> bool:
    if not _fee_has_berth_limit(fee):
        return False
    limit = int(fee.berth_limit_count)
    unit = (fee.berth_limit_unit or '').strip().lower()
    start, end = window_bounds_vn(reference, unit)

    if event_time is not None:
        count = count_ship_berths_at_event(
            db,
            vessel_id=vessel_id,
            ship_id=ship_id,
            window_start=start,
            window_end=end,
            event_time=event_time,
            event_detection_id=event_detection_id,
        )
    else:
        count = count_ship_berths_in_window(
            db,
            vessel_id=vessel_id,
            ship_id=ship_id,
            window_start=start,
            window_end=end,
        )
    return count > limit


def is_ship_over_berth_limit(
    db: Session,
    *,
    vessel_id: Optional[int],
    ship_id: Optional[str],
    reference: datetime,
    fee_configs: Sequence[FeeConfig],
    event_time: Optional[datetime] = None,
    event_detection_id: Optional[int] = None,
) -> bool:
    """True if this ship exceeds any applicable fee_config berth limit."""
    for fee in _fees_with_berth_limits(fee_configs):
        if is_over_limit_for_fee(
            db,
            vessel_id=vessel_id,
            ship_id=ship_id,
            fee=fee,
            reference=reference,
            event_time=event_time,
            event_detection_id=event_detection_id,
        ):
            return True
    return False


@dataclass
class _ShipBerthContext:
    vessel_id: Optional[int]
    ship_id: Optional[str]
    vessel_type_id: Optional[int]
    reference: datetime
    event_time: Optional[datetime]
    event_detection_id: Optional[int]


def _invoice_berth_context(db: Session, invoice) -> Optional[_ShipBerthContext]:
    if not invoice.vessel_id:
        return None

    vessel = invoice.vessel
    vessel_id = invoice.vessel_id
    ship_id: Optional[str] = None
    vessel_type_id: Optional[int] = None

    if vessel is not None:
        ship_id = vessel.ship_id
        vessel_type_id = vessel.vessel_type_id
    else:
        resolved = _resolve_vessel_context(db, vessel_id)
        if not resolved:
            return None
        vessel, vessel_id, ship_id = resolved
        vessel_type_id = vessel.vessel_type_id

    if _normalize_ship_id(ship_id) is None and vessel_id is None:
        return None

    detection = invoice.detection
    if detection is None and invoice.detection_id:
        from app.repositories.detection_repository import detection_repo

        detection = detection_repo.get(db, invoice.detection_id)

    reference = datetime.now(VN_TZ)
    event_time: Optional[datetime] = None
    event_detection_id: Optional[int] = None

    if detection is not None:
        reference = _reference_dt(detection)
        event_time = detection.start_time or detection.created_at
        event_detection_id = detection.id
    elif invoice.created_at is not None:
        reference = _reference_dt(None, invoice.created_at)

    return _ShipBerthContext(
        vessel_id=vessel_id,
        ship_id=ship_id,
        vessel_type_id=vessel_type_id,
        reference=reference,
        event_time=event_time,
        event_detection_id=event_detection_id,
    )


def _resolve_vessel_context(db: Session, vessel_id: int):
    from app.repositories.vessel_repository import vessel_repo

    vessel = vessel_repo.get(db, vessel_id)
    if not vessel:
        return None, None, None
    return vessel, vessel.id, vessel.ship_id


def compute_invoice_over_berth_limit(db: Session, invoice) -> bool:
    """invoice: ORM Invoice with optional items/vessel/detection loaded."""
    ctx = _invoice_berth_context(db, invoice)
    if ctx is None:
        return False

    fees_from_items: list[FeeConfig] = []
    seen_ids: set[int] = set()
    if invoice.items:
        for item in invoice.items:
            fc = getattr(item, 'fee_config', None)
            if fc is not None and fc.id not in seen_ids:
                seen_ids.add(fc.id)
                fees_from_items.append(fc)
            elif item.fee_config_id and item.fee_config_id not in seen_ids:
                fc_row = fee_config_repo.get(db, item.fee_config_id)
                if fc_row:
                    seen_ids.add(fc_row.id)
                    fees_from_items.append(fc_row)

    fees_to_check = _fees_with_berth_limits(fees_from_items)
    if not fees_to_check and ctx.vessel_type_id is not None:
        fees_to_check = _fees_with_berth_limits(
            fee_config_repo.get_by_vessel_type(db, ctx.vessel_type_id),
        )

    if not fees_to_check:
        return False

    return is_ship_over_berth_limit(
        db,
        vessel_id=ctx.vessel_id,
        ship_id=ctx.ship_id,
        reference=ctx.reference,
        fee_configs=fees_to_check,
        event_time=ctx.event_time,
        event_detection_id=ctx.event_detection_id,
    )


def compute_detection_over_berth_limit(db: Session, detection: Detection) -> bool:
    if not detection.vessel_id:
        return False

    vessel = detection.vessel
    ship_id: Optional[str] = None
    vessel_id = detection.vessel_id
    vessel_type_id: Optional[int] = None

    if vessel is not None:
        ship_id = vessel.ship_id
        vessel_type_id = vessel.vessel_type_id
    else:
        resolved = _resolve_vessel_context(db, detection.vessel_id)
        if not resolved:
            return False
        vessel, vessel_id, ship_id = resolved
        vessel_type_id = vessel.vessel_type_id

    if vessel_type_id is None:
        return False

    reference = _reference_dt(detection)
    event_time = detection.start_time or detection.created_at
    fees = _fees_with_berth_limits(
        fee_config_repo.get_by_vessel_type(db, vessel_type_id),
    )
    if not fees:
        return False

    return is_ship_over_berth_limit(
        db,
        vessel_id=vessel_id,
        ship_id=ship_id,
        reference=reference,
        fee_configs=fees,
        event_time=event_time,
        event_detection_id=detection.id,
    )

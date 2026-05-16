"""Berth limit checks: count vessel detections per calendar day/month (VN timezone)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.fee import FeeConfig
from app.repositories.fee_config_repository import fee_config_repo

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


def count_vessel_detections_in_window(
    db: Session,
    vessel_id: int,
    window_start: datetime,
    window_end: datetime,
) -> int:
    return int(
        db.query(func.count(Detection.id))
        .filter(
            Detection.vessel_id == vessel_id,
            func.coalesce(Detection.start_time, Detection.created_at) >= window_start,
            func.coalesce(Detection.start_time, Detection.created_at) < window_end,
        )
        .scalar()
        or 0
    )


def _fee_has_berth_limit(fee: FeeConfig) -> bool:
    count = fee.berth_limit_count
    unit = (fee.berth_limit_unit or '').strip().lower()
    return count is not None and count > 0 and unit in ('day', 'month')


def is_over_limit_for_fee(
    db: Session,
    vessel_id: int,
    fee: FeeConfig,
    reference: datetime,
) -> bool:
    if not _fee_has_berth_limit(fee):
        return False
    unit = (fee.berth_limit_unit or '').strip().lower()
    start, end = window_bounds_vn(reference, unit)
    count = count_vessel_detections_in_window(db, vessel_id, start, end)
    return count > int(fee.berth_limit_count)


def is_vessel_over_any_berth_limit(
    db: Session,
    vessel_id: int,
    reference: datetime,
    vessel_type_id: Optional[int] = None,
    fee_configs: Optional[Sequence[FeeConfig]] = None,
) -> bool:
    if fee_configs is None:
        if vessel_type_id is None:
            return False
        fee_configs = fee_config_repo.get_by_vessel_type(db, vessel_type_id)
    for fee in fee_configs:
        if is_over_limit_for_fee(db, vessel_id, fee, reference):
            return True
    return False


def compute_invoice_over_berth_limit(db: Session, invoice) -> bool:
    """invoice: ORM Invoice with optional items/vessel loaded."""
    if not invoice.vessel_id:
        return False

    reference = datetime.now(VN_TZ)
    if invoice.detection is not None:
        reference = _reference_dt(invoice.detection)
    elif invoice.created_at is not None:
        reference = _reference_dt(None, invoice.created_at)

    fees_to_check: list[FeeConfig] = []
    seen_ids: set[int] = set()
    if invoice.items:
        for item in invoice.items:
            fc = getattr(item, 'fee_config', None)
            if fc is not None and fc.id not in seen_ids:
                seen_ids.add(fc.id)
                fees_to_check.append(fc)
            elif item.fee_config_id and item.fee_config_id not in seen_ids:
                fc_row = fee_config_repo.get(db, item.fee_config_id)
                if fc_row:
                    seen_ids.add(fc_row.id)
                    fees_to_check.append(fc_row)

    vessel_type_id = None
    if invoice.vessel is not None:
        vessel_type_id = invoice.vessel.vessel_type_id
    elif invoice.vessel_id:
        from app.repositories.vessel_repository import vessel_repo

        vessel = vessel_repo.get(db, invoice.vessel_id)
        if vessel:
            vessel_type_id = vessel.vessel_type_id

    if not fees_to_check and vessel_type_id is not None:
        fees_to_check = list(fee_config_repo.get_by_vessel_type(db, vessel_type_id))

    return is_vessel_over_any_berth_limit(
        db,
        invoice.vessel_id,
        reference,
        fee_configs=fees_to_check,
    )


def compute_detection_over_berth_limit(db: Session, detection: Detection) -> bool:
    if not detection.vessel_id:
        return False
    from app.repositories.vessel_repository import vessel_repo

    vessel = detection.vessel
    if vessel is None:
        vessel = vessel_repo.get(db, detection.vessel_id)
    if not vessel or vessel.vessel_type_id is None:
        return False

    reference = _reference_dt(detection)
    return is_vessel_over_any_berth_limit(
        db,
        detection.vessel_id,
        reference,
        vessel_type_id=vessel.vessel_type_id,
    )

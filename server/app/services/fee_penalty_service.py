"""Penalty line items: over berth limit + outside configured operating hours."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.fee import FeeConfig
from app.models.vessel import Vessel
from app.schemas.invoice import InvoiceItemCreate
from app.services.berth_limit_service import (
    _reference_dt,
    is_over_limit_for_fee,
)
from app.utils.fee_operating_hours import (
    day_schedule_for_weekday,
    is_within_operating_hours,
    operating_hours_has_enforced_day,
    weekday_key_vn,
)

VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def detection_start_vn(detection: Detection) -> datetime:
    raw = detection.start_time or detection.created_at
    if raw is None:
        return datetime.now(VN_TZ)
    if raw.tzinfo is None:
        return raw.replace(tzinfo=VN_TZ)
    return raw.astimezone(VN_TZ)


def is_outside_for_fee(start_vn: datetime, fee: FeeConfig) -> bool:
    penalty = Decimal(str(fee.outside_hours_penalty_amount or 0))
    if penalty <= 0:
        return False
    hours = fee.operating_hours
    if not operating_hours_has_enforced_day(hours if isinstance(hours, dict) else None):
        return False
    weekday = weekday_key_vn(start_vn)
    day_schedule = day_schedule_for_weekday(hours if isinstance(hours, dict) else None, weekday)
    if day_schedule is None:
        return False
    return not is_within_operating_hours(start_vn, day_schedule)


def _penalty_amount(value: Optional[Decimal | float | str]) -> Decimal:
    amount = Decimal(str(value or 0)).quantize(Decimal('0.01'))
    return amount if amount > 0 else Decimal('0')


def build_penalty_items(
    db: Session,
    *,
    detection: Detection,
    vessel: Vessel,
    fees: Sequence[FeeConfig],
) -> list[InvoiceItemCreate]:
    items: list[InvoiceItemCreate] = []
    start_vn = detection_start_vn(detection)
    reference = _reference_dt(detection)
    event_time = detection.start_time or detection.created_at

    for fee in fees:
        over_penalty = _penalty_amount(fee.over_limit_penalty_amount)
        if over_penalty > 0 and is_over_limit_for_fee(
            db,
            vessel_id=vessel.id,
            ship_id=vessel.ship_id,
            fee=fee,
            reference=reference,
            event_time=event_time,
            event_detection_id=detection.id,
        ):
            items.append(
                InvoiceItemCreate(
                    fee_config_id=fee.id,
                    description=f'{fee.fee_name} — Phạt vượt giới hạn neo đậu (tự động)',
                    quantity=Decimal('1'),
                    unit_price=over_penalty,
                )
            )

        outside_penalty = _penalty_amount(fee.outside_hours_penalty_amount)
        if outside_penalty > 0 and is_outside_for_fee(start_vn, fee):
            items.append(
                InvoiceItemCreate(
                    fee_config_id=fee.id,
                    description=f'{fee.fee_name} — Phạt neo ngoài giờ (tự động)',
                    quantity=Decimal('1'),
                    unit_price=outside_penalty,
                )
            )

    return items


def is_detection_outside_operating_hours(
    db: Session,
    detection: Detection,
    *,
    vessel_type_id: Optional[int] = None,
) -> bool:
    if vessel_type_id is None:
        vessel = detection.vessel
        if vessel is None and detection.vessel_id:
            from app.repositories.vessel_repository import vessel_repo

            vessel = vessel_repo.get(db, detection.vessel_id)
        vessel_type_id = vessel.vessel_type_id if vessel else None
    if vessel_type_id is None:
        return False

    start_vn = detection_start_vn(detection)
    from app.repositories.fee_config_repository import fee_config_repo

    fees = fee_config_repo.get_by_vessel_type(db, vessel_type_id)
    for fee in fees:
        if is_outside_for_fee(start_vn, fee):
            return True
    return False


def compute_invoice_outside_operating_hours(db: Session, invoice) -> bool:
    detection = invoice.detection
    if detection is None and invoice.detection_id:
        from app.repositories.detection_repository import detection_repo

        detection = detection_repo.get(db, invoice.detection_id)
    if detection is None:
        return False

    vessel_type_id: Optional[int] = None
    if invoice.vessel is not None:
        vessel_type_id = invoice.vessel.vessel_type_id
    elif invoice.vessel_id:
        from app.repositories.vessel_repository import vessel_repo

        vessel = vessel_repo.get(db, invoice.vessel_id)
        if vessel:
            vessel_type_id = vessel.vessel_type_id

    return is_detection_outside_operating_hours(
        db,
        detection,
        vessel_type_id=vessel_type_id,
    )

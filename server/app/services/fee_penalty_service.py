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
    outside_operating_hours_for_interval,
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


def is_monthly_fee_outside_for_detection(detection: Detection, fee: FeeConfig) -> bool:
    """Kiểm tra khoảng neo tàu tháng có chạm phần ngoài giờ không."""
    per_hour = _penalty_amount(getattr(fee, 'outside_hours_penalty_per_hour', None))
    if per_hour <= 0:
        per_hour = _penalty_amount(getattr(fee, 'outside_hours_penalty_amount', None))
    if per_hour <= 0:
        return False
    return outside_operating_hours_for_interval(
        detection.berth_in_time or detection.start_time,
        detection.berth_out_time or detection.end_time,
        fee.operating_hours if isinstance(fee.operating_hours, dict) else None,
    ) > 0


def _penalty_amount(value: Optional[Decimal | float | str]) -> Decimal:
    amount = Decimal(str(value or 0)).quantize(Decimal('0.01'))
    return amount if amount > 0 else Decimal('0')


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo('UTC'))
    return dt


def berth_duration_minutes(detection: Detection) -> Optional[Decimal]:
    """Thời lượng thực của MỘT lần neo (phút).

    Ưu tiên berth_in_time → berth_out_time (thời gian tàu thực sự nằm trong
    vùng neo). Thiếu mốc berth thì fallback start_time → end_time. Trả None nếu
    không đủ dữ liệu để tính thời lượng.
    """
    start = _as_utc(detection.berth_in_time) or _as_utc(detection.start_time)
    end = _as_utc(detection.berth_out_time) or _as_utc(detection.end_time)
    if start is None or end is None:
        return None
    secs = (end - start).total_seconds()
    if secs <= 0:
        return None
    return (Decimal(str(secs)) / Decimal('60')).quantize(Decimal('0.01'))


def is_over_duration_for_fee(detection: Detection, fee: FeeConfig) -> bool:
    """True nếu MỘT lần neo này vượt giới hạn thời gian cho phép của fee."""
    penalty = _penalty_amount(getattr(fee, 'over_duration_penalty_amount', None))
    if penalty <= 0:
        return False
    limit = getattr(fee, 'max_berth_duration_minutes', None)
    if limit is None or limit <= 0:
        return False
    duration = berth_duration_minutes(detection)
    if duration is None:
        return False
    return duration > Decimal(str(limit))


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

        classification = getattr(vessel, 'classification', None)
        outside_penalty = _penalty_amount(fee.outside_hours_penalty_amount)

        # Tàu lẻ: giữ nghiệp vụ cũ — một mức phạt cố định cho mỗi lượt bắt đầu ngoài giờ.
        if classification == 'spot' and outside_penalty > 0 and is_outside_for_fee(start_vn, fee):
            items.append(
                InvoiceItemCreate(
                    fee_config_id=fee.id,
                    description=f'{fee.fee_name} — Phạt neo ngoài giờ (tự động)',
                    quantity=Decimal('1'),
                    unit_price=outside_penalty,
                )
            )

        # Tàu tháng: đơn giá ₫/giờ × số giờ thực nằm ngoài khung cho phép.
        # Fallback field cũ giúp cấu hình tàu tháng hiện hữu đổi semantics ngay, không mất phí.
        per_hour = _penalty_amount(getattr(fee, 'outside_hours_penalty_per_hour', None))
        if classification == 'monthly' and per_hour <= 0:
            per_hour = outside_penalty
        if classification == 'monthly' and per_hour > 0:
            hours_outside = outside_operating_hours_for_interval(
                detection.berth_in_time or detection.start_time,
                detection.berth_out_time or detection.end_time,
                fee.operating_hours if isinstance(fee.operating_hours, dict) else None,
            )
            if hours_outside > 0:
                items.append(
                    InvoiceItemCreate(
                        fee_config_id=fee.id,
                        description=(
                            f'{fee.fee_name} — Phạt neo ngoài giờ theo giờ '
                            f'({hours_outside.quantize(Decimal("0.01"))} giờ ngoài khung '
                            f'× {per_hour}₫/giờ) (tự động)'
                        ),
                        quantity=hours_outside,
                        unit_price=per_hour,
                    )
                )

        # unclassified: resolver không trả fee; nhánh này vẫn chủ động không tính phạt.

        over_duration_penalty = _penalty_amount(
            getattr(fee, 'over_duration_penalty_amount', None)
        )
        if over_duration_penalty > 0 and is_over_duration_for_fee(detection, fee):
            duration = berth_duration_minutes(detection)
            limit = getattr(fee, 'max_berth_duration_minutes', None)
            items.append(
                InvoiceItemCreate(
                    fee_config_id=fee.id,
                    description=(
                        f'{fee.fee_name} — Phạt vượt thời gian neo một lần '
                        f'(neo {duration} phút > cho phép {limit} phút) (tự động)'
                    ),
                    quantity=Decimal('1'),
                    unit_price=over_duration_penalty,
                )
            )

    return items


def is_detection_outside_operating_hours(
    db: Session,
    detection: Detection,
    *,
    vessel_id: Optional[int] = None,
) -> bool:
    vessel = detection.vessel
    lookup_id = vessel_id or detection.vessel_id
    if vessel is None and lookup_id:
        from app.repositories.vessel_repository import vessel_repo

        vessel = vessel_repo.get(db, lookup_id)
    vessel_id = vessel.id if vessel else lookup_id
    if vessel_id is None:
        return False

    start_vn = detection_start_vn(detection)
    from app.services.fee_resolution_service import resolve_billable_fees

    fees = resolve_billable_fees(db, vessel or vessel_id)
    classification = getattr(vessel, 'classification', None)
    for fee in fees:
        if classification == 'monthly':
            if is_monthly_fee_outside_for_detection(detection, fee):
                return True
        elif is_outside_for_fee(start_vn, fee):
            return True
    return False


def compute_invoice_outside_operating_hours(db: Session, invoice) -> bool:
    detection = invoice.detection
    if detection is None and invoice.detection_id:
        from app.repositories.detection_repository import detection_repo

        detection = detection_repo.get(db, invoice.detection_id)
    if detection is None:
        return False

    vessel_id: Optional[int] = invoice.vessel_id

    return is_detection_outside_operating_hours(
        db,
        detection,
        vessel_id=vessel_id,
    )

"""Dashboard system overview metrics (operations + registry + billing coverage)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.camera import Camera
from app.models.fee import FeeConfig
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.vessel import Vessel
from app.models.vessel_type import VesselType

TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def _period_start_local(kind: str) -> datetime:
    now = datetime.now(TZ)
    if kind == 'day':
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == 'month':
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def _period_bounds_utc(kind: str) -> tuple[datetime, datetime]:
    start_local = _period_start_local(kind)
    if kind == 'day':
        end_local = start_local + timedelta(days=1)
    elif kind == 'month':
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    else:
        end_local = start_local.replace(year=start_local.year + 1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _count_vessels_created_between(db: Session, kind: str) -> int:
    start_utc, end_utc = _period_bounds_utc(kind)
    return int(
        db.query(Vessel)
        .filter(Vessel.created_at >= start_utc, Vessel.created_at < end_utc)
        .count()
    )


def build_system_overview(db: Session) -> dict:
    total_vessels = int(db.query(Vessel).count())
    vessels_without_type = int(db.query(Vessel).filter(Vessel.vessel_type_id.is_(None)).count())

    # A vessel type is "billable" if it has at least one active config with positive fee and unit != none.
    billable_type_ids = {
        int(row[0])
        for row in (
            db.query(FeeConfig.vessel_type_id)
            .filter(
                FeeConfig.vessel_type_id.is_not(None),
                FeeConfig.is_active.is_(True),
                FeeConfig.unit != 'none',
                FeeConfig.base_fee > Decimal('0'),
            )
            .distinct()
            .all()
        )
    }

    billable_vessels = 0
    no_fee_vessels = 0
    for (type_id,) in db.query(Vessel.vessel_type_id).all():
        if type_id is None:
            no_fee_vessels += 1
            continue
        if int(type_id) in billable_type_ids:
            billable_vessels += 1
        else:
            no_fee_vessels += 1

    total_vessel_types = int(db.query(VesselType).count())
    active_fee_type_ids = {
        int(r[0])
        for r in (
            db.query(FeeConfig.vessel_type_id)
            .filter(FeeConfig.vessel_type_id.is_not(None), FeeConfig.is_active.is_(True))
            .distinct()
            .all()
        )
    }
    vessel_types_without_active_fee = max(total_vessel_types - len(active_fee_type_ids), 0)

    active_cameras = int(db.query(Camera).filter(Camera.is_active.is_(True)).count())
    inactive_cameras = int(db.query(Camera).filter(Camera.is_active.is_(False)).count())

    pending_orders = int(db.query(Order).filter(Order.status == 'PENDING').count())
    unpaid_invoices = int(db.query(Invoice).filter(Invoice.payment_status == 'UNPAID', Invoice.deleted_at.is_(None)).count())
    ai_invoices = int(db.query(Invoice).filter(Invoice.creation_source == 'AI', Invoice.deleted_at.is_(None)).count())

    return {
        'registered_vessels_day': _count_vessels_created_between(db, 'day'),
        'registered_vessels_month': _count_vessels_created_between(db, 'month'),
        'registered_vessels_year': _count_vessels_created_between(db, 'year'),
        'total_registered_vessels': total_vessels,
        'vessels_without_type': vessels_without_type,
        'vessels_no_fee': no_fee_vessels,
        'vessels_billable': billable_vessels,
        'total_vessel_types': total_vessel_types,
        'vessel_types_without_active_fee': vessel_types_without_active_fee,
        'active_cameras': active_cameras,
        'inactive_cameras': inactive_cameras,
        'pending_orders': pending_orders,
        'unpaid_invoices': unpaid_invoices,
        'ai_invoices': ai_invoices,
    }

"""Hóa đơn tự động (creation_source=AI) khi kết thúc track và tàu đã đăng ký trong hệ thống."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories.detection_repository import detection_repo
from app.repositories.fee_config_repository import fee_config_repo
from app.repositories.invoice_repository import invoice_repo
from app.repositories.vessel_repository import vessel_repo
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate
from app.services.invoice_service import invoice_service

_log = logging.getLogger('app.services.detection_invoice')

_UNKNOWN_SHIP = frozenset({'', 'UNKNOWN', 'KHÔNG XÁC ĐỊNH', 'N/A'})


def _norm_ship(s: Optional[str]) -> str:
    return (s or '').strip().upper()


def is_unknown_ship_id(ship_id: Optional[str]) -> bool:
    return _norm_ship(ship_id) in _UNKNOWN_SHIP


def _berthing_hours(start: Optional[datetime], end: Optional[datetime]) -> Decimal:
    """Thời gian neo (giờ), tối thiểu 0.01h; mặc định 1h nếu thiếu mốc."""
    if start is None or end is None:
        return Decimal('1')
    s, e = start, end
    if s.tzinfo is None:
        s = s.replace(tzinfo=timezone.utc)
    if e.tzinfo is None:
        e = e.replace(tzinfo=timezone.utc)
    secs = (e - s).total_seconds()
    if secs <= 0:
        return Decimal('1')
    raw = Decimal(str(secs)) / Decimal('3600')
    return max(raw.quantize(Decimal('0.01'), rounding=ROUND_UP), Decimal('0.01'))


def _fee_unit(fee) -> str:
    u = (fee.unit or 'per_month').strip().lower()
    if u in ('per_hour', 'per_month', 'per_year', 'none'):
        return u
    return 'per_month'


def ensure_ai_invoice_for_detection(detection_id: int, *, vessel_preexisted: bool) -> None:
    """
    Tạo tối đa một hóa đơn AI cho detection_id.
    Chỉ khi tàu đã tồn tại trước lần detect này (trùng mã), có vessel_type_id và có phí active.
    """
    if not vessel_preexisted:
        return

    db: Session = SessionLocal()
    try:
        det = detection_repo.get(db, detection_id)
        if not det or not det.vessel_id:
            return

        vessel = vessel_repo.get(db, det.vessel_id)
        if not vessel:
            return
        if is_unknown_ship_id(vessel.ship_id):
            return
        if vessel.vessel_type_id is None:
            return

        existing = invoice_repo.get_by_detection_id(db, detection_id)
        if existing:
            return

        fees = fee_config_repo.get_by_vessel_type(db, vessel.vessel_type_id)
        if not fees:
            return

        hours = _berthing_hours(det.start_time, det.end_time)
        items: list[InvoiceItemCreate] = []
        has_period = False

        for fee in fees:
            unit = _fee_unit(fee)
            if unit == 'none':
                continue
            base = Decimal(str(fee.base_fee))
            if unit == 'per_hour':
                items.append(
                    InvoiceItemCreate(
                        fee_config_id=fee.id,
                        description=f'{fee.fee_name} — neo {hours} giờ (tự động)',
                        quantity=hours,
                        unit_price=base,
                    )
                )
            elif unit in ('per_month', 'per_year'):
                has_period = True
                label = 'tháng' if unit == 'per_month' else 'năm'
                items.append(
                    InvoiceItemCreate(
                        fee_config_id=fee.id,
                        description=f'{fee.fee_name} — tham chiếu phí theo {label} (quản lý nhập tổng sau)',
                        quantity=Decimal('1'),
                        unit_price=base,
                        amount=Decimal('0'),
                    )
                )

        if not items:
            return

        def _line_sub(it: InvoiceItemCreate) -> Decimal:
            if it.amount is not None:
                return it.amount
            q = it.quantity if it.quantity is not None else Decimal('1')
            return (q * it.unit_price).quantize(Decimal('0.01'))

        inv_no = invoice_repo.generate_unique_invoice_number(db)
        notes_parts = [
            'Hóa đơn tự động từ nhận dạng tàu.',
            f'Track: {det.track_id or "—"}',
        ]
        payload = InvoiceCreate(
            invoice_number=inv_no,
            vessel_id=vessel.id,
            detection_id=det.id,
            creation_source='AI',
            created_by=None,
            notes='\n'.join(notes_parts),
            items=items,
        )

        if has_period:
            subtotal = sum((_line_sub(it) for it in items), Decimal('0'))
            payload = payload.model_copy(
                update={
                    'subtotal': subtotal,
                    'tax_amount': Decimal('0'),
                    'total_amount': Decimal('0'),
                }
            )

        invoice_service.create_with_items(db, payload)
        _log.info(
            'Created AI invoice %s for detection_id=%s vessel=%s',
            inv_no,
            detection_id,
            vessel.ship_id,
        )
    except Exception:
        _log.exception('ensure_ai_invoice_for_detection failed detection_id=%s', detection_id)
        db.rollback()
    finally:
        db.close()

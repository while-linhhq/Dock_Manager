"""Hóa đơn tự động (creation_source=AI) khi kết thúc track và tàu đã đăng ký trong hệ thống."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.detection import Detection
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.repositories.detection_repository import detection_repo
from app.repositories.fee_config_repository import fee_config_repo
from app.repositories.invoice_repository import invoice_repo
from app.repositories.vessel_repository import vessel_repo
from app.services.fee_resolution_service import resolve_billable_fees
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate
from app.services.berth_limit_service import compute_invoice_over_berth_limit
from app.services.fee_penalty_service import build_penalty_items, compute_invoice_outside_operating_hours
from app.services.invoice_service import compute_invoice_total, invoice_service
from app.services.invoice_snapshot_service import is_invoice_financially_locked
from app.services.ship_id_utils import is_unknown_ship_id
from app.utils.fee_billing_unit import normalize_fee_billing_unit

_log = logging.getLogger('app.services.detection_invoice')

_DUPLICATE_BERTH_WINDOW = timedelta(minutes=5)


def _find_duplicate_ai_invoice_for_visit(
    db: Session,
    *,
    vessel_id: int,
    berth_in: Optional[datetime],
) -> Optional[Invoice]:
    """Safety net: unpaid AI invoice for same vessel + berth_in within ±5 minutes."""
    if berth_in is None:
        return None
    anchor = berth_in
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    window_start = anchor - _DUPLICATE_BERTH_WINDOW
    window_end = anchor + _DUPLICATE_BERTH_WINDOW
    return (
        db.query(Invoice)
        .join(Detection, Invoice.detection_id == Detection.id)
        .filter(
            Invoice.vessel_id == int(vessel_id),
            Invoice.deleted_at.is_(None),
            Invoice.payment_status != 'PAID',
            Invoice.creation_source.in_(['AI', 'ORDER_AUTO']),
            Detection.berth_in_time.isnot(None),
            Detection.berth_in_time >= window_start,
            Detection.berth_in_time <= window_end,
        )
        .order_by(Invoice.id.asc())
        .first()
    )


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Chuẩn hóa datetime về tz-aware UTC. Naive được coi là UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _berthing_hours(start: Optional[datetime], end: Optional[datetime]) -> Decimal:
    """Thời gian neo theo giờ thực, không làm tròn lên 0.01h."""
    if start is None and end is None:
        return Decimal('0')
    if start is None or end is None:
        return Decimal('0')
    s, e = _as_utc(start), _as_utc(end)
    secs = (e - s).total_seconds()
    if secs <= 0:
        return Decimal('0')
    return Decimal(str(secs)) / Decimal('3600')


def resolve_berth_window(
    start: Optional[datetime],
    end: Optional[datetime],
    berth_in: Optional[datetime],
    berth_out: Optional[datetime],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Chọn billing window dựa trên berth_in/berth_out, fallback start/end khi thiếu.

    Không clamp — nếu berth_in/out là timestamps từ cross-camera identity
    không giao với detection window, trả về (None, None) để tạo invoice
    tối thiểu (0.01h), không tính tiền neo đậu từ camera khác.
    """
    start = _as_utc(start)
    end = _as_utc(end)
    berth_in = _as_utc(berth_in)
    berth_out = _as_utc(berth_out)
    if berth_in is not None and berth_out is not None:
        # Đủ cả hai mốc: dùng trực tiếp — đây là thời gian thực tàu đậu
        s, e = berth_in, berth_out
        # Chỉ fallback nếu window không hợp lệ (berth hoàn toàn ngoài detection)
        if (start is not None and e < start) or (end is not None and s > end):
            # Berth window không giao với detection này => không tính neo
            return None, None
        if s >= e:
            return None, None
        return s, e
    if berth_in is not None and end is not None:
        # Có berth_in, thiếu berth_out: dùng berth_in → end (rời camera)
        s = berth_in
        if end is not None and s > end:
            return None, None
        return s, end
    if berth_out is not None and start is not None:
        # Có berth_out, thiếu berth_in: dùng start → berth_out
        e = berth_out
        if start is not None and start > e:
            return None, None
        return start, e
    # Không có berth info nào: fallback toàn track
    return start, end


def _line_sub(it: InvoiceItemCreate) -> Decimal:
    if it.amount is not None:
        return it.amount
    q = it.quantity if it.quantity is not None else Decimal('1')
    return (q * it.unit_price).quantize(Decimal('0.01'))


def build_ai_invoice_items(db: Session, det: Detection, vessel, fees) -> list[InvoiceItemCreate]:
    """Dựng danh sách line-item hóa đơn AI từ detection + fee config active.

    Dùng chung cho tạo mới (ensure_) và tính lại khi sửa detection (recompute_).
    Cột "neo đậu" hiển thị theo detection.start_time/end_time nên quantity tiền
    dùng đúng window đó; berth_in/out chỉ là tín hiệu vào/ra vùng cho penalty.
    """
    hours = _berthing_hours(
        cast(Optional[datetime], det.start_time),
        cast(Optional[datetime], det.end_time),
    )
    items: list[InvoiceItemCreate] = []

    for fee in fees:
        unit = normalize_fee_billing_unit(fee.unit)
        if unit == 'none':
            continue
        base = Decimal(str(fee.base_fee))
        if unit == 'per_berth_visit':
            items.append(
                InvoiceItemCreate(
                    fee_config_id=fee.id,
                    description=f'{fee.fee_name} — 1 lượt cập bến (tự động)',
                    quantity=Decimal('1'),
                    unit_price=base,
                )
            )
        elif unit == 'per_hour':
            items.append(
                InvoiceItemCreate(
                    fee_config_id=fee.id,
                    description=f'{fee.fee_name} — neo {hours} giờ (tự động)',
                    quantity=hours,
                    unit_price=base,
                )
            )
        elif unit in ('per_month', 'per_year'):
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

    penalty_items = build_penalty_items(
        db,
        detection=det,
        vessel=vessel,
        fees=fees,
    )
    items.extend(penalty_items)
    return items


def _replace_ai_invoice_items(
    db: Session,
    invoice: Invoice,
    vessel,
    items: list[InvoiceItemCreate],
) -> None:
    """Replace unlocked AI invoice content inside caller's transaction."""
    subtotal = sum((_line_sub(item) for item in items), Decimal('0')).quantize(Decimal('0.01'))
    for old in list(invoice.items):
        db.delete(old)
    db.flush()
    for item in items:
        data = item.model_dump()
        data['invoice_id'] = invoice.id
        db.add(InvoiceItem(**data))

    invoice.subtotal = subtotal
    invoice.tax_amount = Decimal('0')
    invoice.total_amount = compute_invoice_total(
        subtotal,
        Decimal('0'),
        invoice.discount_amount,
    )
    invoice.vessel_id = vessel.id
    db.flush()

    refreshed = invoice_repo.get(db, invoice.id)
    if refreshed:
        refreshed.is_over_berth_limit = compute_invoice_over_berth_limit(db, refreshed)
        refreshed.is_outside_operating_hours = compute_invoice_outside_operating_hours(db, refreshed)


def ensure_ai_invoice_for_detection(
    detection_id: int,
    *,
    session: Session | None = None,
    commit: bool = True,
) -> dict:
    """Tạo tối đa một invoice AI, dùng transaction của caller khi được truyền vào."""
    owns_db = session is None
    db: Session = session or SessionLocal()
    try:
        det = detection_repo.get(db, detection_id)
        if not det or not det.vessel_id:
            return {'status': 'skipped_no_vessel'}

        vessel = vessel_repo.get(db, det.vessel_id)
        if not vessel:
            return {'status': 'skipped_no_vessel'}
        if is_unknown_ship_id(vessel.ship_id):
            return {'status': 'skipped_not_eligible'}

        existing = invoice_repo.get_by_detection_id(db, detection_id)
        if existing:
            return {'status': 'exists', 'invoice_id': existing.id}

        berth_in, _berth_out = resolve_berth_window(
            det.start_time,
            det.end_time,
            det.berth_in_time,
            det.berth_out_time,
        )
        duplicate = _find_duplicate_ai_invoice_for_visit(
            db,
            vessel_id=int(vessel.id),
            berth_in=berth_in,
        )
        if duplicate is not None:
            return {'status': 'duplicate_visit', 'invoice_id': duplicate.id}

        fees = resolve_billable_fees(db, vessel)
        if not fees:
            return {'status': 'skipped_no_fee'}

        items = build_ai_invoice_items(db, det, vessel, fees)
        if not items:
            return {'status': 'skipped_no_items'}

        inv_no = invoice_repo.generate_unique_invoice_number(db)
        notes_parts = [
            'Hóa đơn tự động từ nhận dạng tàu.',
            f'Track: {det.track_id or "—"}',
        ]
        subtotal = sum((_line_sub(it) for it in items), Decimal('0')).quantize(Decimal('0.01'))
        payload = InvoiceCreate(
            invoice_number=inv_no,
            vessel_id=vessel.id,
            detection_id=det.id,
            creation_source='AI',
            created_by=None,
            notes='\n'.join(notes_parts),
            subtotal=subtotal,
            tax_amount=Decimal('0'),
            total_amount=subtotal,
            items=items,
        )

        try:
            with db.begin_nested():
                created = invoice_service.create_with_items(db, payload, commit=False)
        except IntegrityError:
            existing = invoice_repo.get_by_detection_id(db, detection_id)
            if existing is not None:
                if (
                    existing.creation_source in ('AI', 'ORDER_AUTO')
                    and existing.payment_status == 'UNPAID'
                    and not is_invoice_financially_locked(existing)
                ):
                    _replace_ai_invoice_items(db, existing, vessel, items)
                    return {'status': 'recomputed_race', 'invoice_id': existing.id}
                return {'status': 'exists', 'invoice_id': existing.id}
            raise
        if commit:
            db.commit()
        _log.info(
            'Created AI invoice %s for detection_id=%s vessel=%s',
            inv_no,
            detection_id,
            vessel.ship_id,
        )
        return {'status': 'created', 'invoice_id': created.id}
    except Exception:
        _log.exception('ensure_ai_invoice_for_detection failed detection_id=%s', detection_id)
        if commit:
            db.rollback()
            return {'status': 'error'}
        raise
    finally:
        if owns_db:
            db.close()


def recompute_ai_invoice_for_detection(
    detection_id: int,
    *,
    session: Session | None = None,
    commit: bool = True,
) -> dict:
    """Tính lại hóa đơn AI của detection sau khi sửa detection.

    - Không có invoice AI: tạo mới (ủy quyền cho ensure_).
    - Có invoice AI chưa thanh toán: dựng lại line-items + subtotal/total theo
      dữ liệu detection mới, xóa item cũ, ghi item mới.
    - Invoice đã PARTIAL/PAID (financial lock): giữ nguyên, không sửa tiền.

    Trả dict {status, invoice_id?} để endpoint báo lại cho client.
    """
    owns_db = session is None
    db: Session = session or SessionLocal()
    try:
        det = detection_repo.get(db, detection_id)
        if not det:
            return {'status': 'skipped_missing_detection'}

        existing = invoice_repo.get_by_detection_id(db, detection_id)
        if existing is not None and existing.creation_source not in ('AI', 'ORDER_AUTO'):
            return {'status': 'skipped_not_ai', 'invoice_id': existing.id}

        if existing is not None and (
            existing.payment_status in {'PARTIAL', 'PAID'}
            or is_invoice_financially_locked(existing)
        ):
            _log.info(
                'Skip recompute detection_id=%s: invoice %s đã nhận thanh toán (khóa tài chính)',
                detection_id,
                existing.id,
            )
            return {'status': 'skipped_locked', 'invoice_id': existing.id}

        def retire_unbillable(status: str) -> dict:
            if existing is None:
                return {'status': status}
            existing.deleted_at = datetime.now(timezone.utc)
            if commit:
                db.commit()
            else:
                db.flush()
            return {'status': 'retired_unbillable', 'invoice_id': existing.id}

        if not det.vessel_id:
            return retire_unbillable('skipped_no_vessel')

        vessel = vessel_repo.get(db, det.vessel_id)
        if not vessel or is_unknown_ship_id(vessel.ship_id):
            return retire_unbillable('skipped_not_eligible')

        fees = resolve_billable_fees(db, vessel)
        if not fees:
            return retire_unbillable('skipped_no_fee')

        items = build_ai_invoice_items(db, det, vessel, fees)
        if not items:
            return retire_unbillable('skipped_no_items')

        if existing is None:
            return ensure_ai_invoice_for_detection(
                detection_id,
                session=db,
                commit=commit,
            )

        _replace_ai_invoice_items(db, existing, vessel, items)

        if commit:
            db.commit()
        else:
            db.flush()
        _log.info(
            'Recomputed AI invoice %s for detection_id=%s subtotal=%s',
            existing.invoice_number,
            detection_id,
            existing.subtotal,
        )
        return {'status': 'recomputed', 'invoice_id': existing.id}
    except Exception:
        _log.exception('recompute_ai_invoice_for_detection failed detection_id=%s', detection_id)
        if commit:
            db.rollback()
            return {'status': 'error'}
        raise
    finally:
        if owns_db:
            db.close()


def backfill_missing_ai_invoices(limit: int = 200) -> dict:
    """
    Tạo hóa đơn AI cho các detection cũ chưa có invoice (phục vụ backfill/test).
    Chỉ xử lý detection có vessel_id và chưa có invoice chưa xóa.
    """
    db: Session = SessionLocal()
    try:
        ids = [
            int(r[0])
            for r in (
                db.query(Detection.id)
                .outerjoin(
                    Invoice,
                    (Invoice.detection_id == Detection.id) & (Invoice.deleted_at.is_(None)),
                )
                .filter(
                    Detection.vessel_id.is_not(None),
                    Invoice.id.is_(None),
                )
                .order_by(Detection.created_at.desc(), Detection.id.desc())
                .limit(max(1, int(limit)))
                .all()
            )
        ]
    finally:
        db.close()

    created = 0
    processed = 0
    for det_id in ids:
        processed += 1
        ensure_ai_invoice_for_detection(det_id)
        db_check: Session = SessionLocal()
        try:
            if invoice_repo.get_by_detection_id(db_check, det_id):
                created += 1
        finally:
            db_check.close()

    return {
        'processed': processed,
        'created': created,
        'skipped': processed - created,
    }

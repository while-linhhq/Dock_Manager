"""Backfill AI invoices when vessel type / fee config becomes available."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.detection import Detection
from app.models.invoice import Invoice
from app.models.vessel import Vessel
from app.repositories.fee_config_repository import fee_config_repo
from app.repositories.vessel_repository import vessel_repo
from app.services.detection_invoice_service import ensure_ai_invoice_for_detection
from app.services.ship_id_utils import is_unknown_ship_id

_log = logging.getLogger('app.services.ship_invoice_backfill')

DEFAULT_LIMIT = 500


def _fee_unit(fee) -> str:
    u = (fee.unit or 'per_month').strip().lower()
    if u in ('per_hour', 'per_month', 'per_year', 'none'):
        return u
    return 'per_month'


def vessel_type_has_billable_fees(db: Session, vessel_type_id: int) -> bool:
    fees = fee_config_repo.get_by_vessel_type(db, vessel_type_id)
    return any(_fee_unit(f) != 'none' for f in fees)


def vessel_ready_for_ai_invoice(db: Session, vessel_id: int) -> bool:
    vessel = vessel_repo.get(db, vessel_id)
    if not vessel:
        return False
    if is_unknown_ship_id(vessel.ship_id):
        return False
    if vessel.vessel_type_id is None:
        return False
    return vessel_type_has_billable_fees(db, vessel.vessel_type_id)


def _missing_detection_ids_for_vessel(db: Session, vessel_id: int, *, limit: int) -> list[int]:
    rows = (
        db.query(Detection.id)
        .outerjoin(
            Invoice,
            (Invoice.detection_id == Detection.id) & (Invoice.deleted_at.is_(None)),
        )
        .filter(
            Detection.vessel_id == vessel_id,
            Invoice.id.is_(None),
        )
        .order_by(Detection.created_at.asc(), Detection.id.asc())
        .limit(max(1, limit))
        .all()
    )
    return [int(r[0]) for r in rows]


def backfill_ai_invoices_for_vessel(
    db: Session,
    vessel_id: int,
    *,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    if not vessel_ready_for_ai_invoice(db, vessel_id):
        return {'processed': 0, 'created': 0, 'skipped': 0, 'vessel_id': vessel_id}

    det_ids = _missing_detection_ids_for_vessel(db, vessel_id, limit=limit)
    created = 0
    for det_id in det_ids:
        ensure_ai_invoice_for_detection(det_id)
        check_db = SessionLocal()
        try:
            from app.repositories.invoice_repository import invoice_repo

            if invoice_repo.get_by_detection_id(check_db, det_id):
                created += 1
        finally:
            check_db.close()

    processed = len(det_ids)
    result = {
        'processed': processed,
        'created': created,
        'skipped': processed - created,
        'vessel_id': vessel_id,
    }
    if processed:
        _log.info('ship_invoice_backfill vessel_id=%s %s', vessel_id, result)
    return result


def backfill_ai_invoices_for_vessel_type(
    db: Session,
    vessel_type_id: int,
    *,
    limit_per_vessel: int = DEFAULT_LIMIT,
) -> dict:
    if not vessel_type_has_billable_fees(db, vessel_type_id):
        return {
            'processed': 0,
            'created': 0,
            'skipped': 0,
            'vessel_type_id': vessel_type_id,
            'vessels': 0,
        }

    vessels = (
        db.query(Vessel.id)
        .filter(Vessel.vessel_type_id == vessel_type_id)
        .all()
    )
    total_processed = 0
    total_created = 0
    for (vid,) in vessels:
        if not vessel_ready_for_ai_invoice(db, vid):
            continue
        part = backfill_ai_invoices_for_vessel(db, vid, limit=limit_per_vessel)
        total_processed += part['processed']
        total_created += part['created']

    return {
        'processed': total_processed,
        'created': total_created,
        'skipped': total_processed - total_created,
        'vessel_type_id': vessel_type_id,
        'vessels': len(vessels),
    }


def run_vessel_backfill_task(vessel_id: int, *, limit: int = DEFAULT_LIMIT) -> dict:
    db = SessionLocal()
    try:
        result = backfill_ai_invoices_for_vessel(db, vessel_id, limit=limit)
        _log.info('run_vessel_backfill_task vessel_id=%s %s', vessel_id, result)
        return result
    except Exception:
        _log.exception('run_vessel_backfill_task failed vessel_id=%s', vessel_id)
        raise
    finally:
        db.close()


def run_vessel_type_backfill_task(vessel_type_id: int, *, limit_per_vessel: int = DEFAULT_LIMIT) -> dict:
    db = SessionLocal()
    try:
        return backfill_ai_invoices_for_vessel_type(
            db,
            vessel_type_id,
            limit_per_vessel=limit_per_vessel,
        )
    finally:
        db.close()


def fee_config_triggers_backfill(fee) -> bool:
    """True when an active fee can generate AI invoice line items."""
    if not fee.is_active or fee.vessel_type_id is None:
        return False
    return _fee_unit(fee) != 'none'


def should_backfill_after_fee_update(old_fee, updated_fee) -> bool:
    if not fee_config_triggers_backfill(updated_fee):
        return False
    if not fee_config_triggers_backfill(old_fee):
        return True
    if old_fee.vessel_type_id != updated_fee.vessel_type_id:
        return True
    if _fee_unit(old_fee) == 'none' and _fee_unit(updated_fee) != 'none':
        return True
    return False

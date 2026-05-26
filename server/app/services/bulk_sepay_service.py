"""SEPay thanh toán gộp — một mã QR, nhiều hóa đơn."""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from app.models.bulk_payment_session import BulkPaymentSession
from app.repositories.bulk_payment_session_repository import bulk_payment_session_repo
from app.repositories.invoice_repository import invoice_repo
from app.repositories.payment_repository import payment_repo
from app.services.invoice_payment_service import invoice_amount_due
from app.services.invoice_snapshot_service import is_invoice_financially_locked
from app.services.sepay_sync_service import SEPAY_PAYMENT_METHOD

logger = logging.getLogger('app.sepay.bulk')

BULK_REF_PREFIX = 'BULK-'
_BULK_REF_PATTERN = re.compile(r'BULK-[A-Z0-9-]+', re.IGNORECASE)


def generate_bulk_reference_code() -> str:
    return f'{BULK_REF_PREFIX}{datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")}-{secrets.token_hex(3).upper()}'


def resolve_bulk_reference(txn: dict[str, Any], reference_code: Optional[str] = None) -> Optional[str]:
    code = txn.get('code')
    if code is not None and str(code).strip():
        candidate = str(code).strip().upper()
        if candidate.startswith(BULK_REF_PREFIX):
            if reference_code and candidate != reference_code.upper():
                return None
            return candidate

    if not reference_code:
        content = str(txn.get('transaction_content') or '')
        match = _BULK_REF_PATTERN.search(content)
        if match:
            return match.group(0).upper()
        return None

    content = str(txn.get('transaction_content') or '').upper()
    wanted = reference_code.upper()
    if wanted in content:
        return wanted
    return None


def create_bulk_sepay_session(
    db: Session,
    invoice_ids: List[int],
    *,
    created_by: int,
) -> BulkPaymentSession:
    unique_ids: list[int] = []
    seen: set[int] = set()
    for raw in invoice_ids:
        iid = int(raw)
        if iid in seen:
            continue
        seen.add(iid)
        unique_ids.append(iid)

    if not unique_ids:
        raise ValueError('invoice_ids must not be empty')

    payable: list[int] = []
    total = Decimal('0')
    for iid in unique_ids:
        inv = invoice_repo.get(db, iid)
        if not inv:
            raise ValueError(f'Invoice {iid} not found')
        if is_invoice_financially_locked(inv):
            continue
        due = invoice_amount_due(db, inv)
        if due <= 0:
            continue
        payable.append(iid)
        total += due

    if not payable:
        raise ValueError('No payable invoices in request')

    ref = generate_bulk_reference_code()
    return bulk_payment_session_repo.create(
        db,
        reference_code=ref,
        invoice_ids=payable,
        expected_total=total.quantize(Decimal('0.01')),
        created_by=created_by,
    )


def apply_bulk_incoming_transaction(
    db: Session,
    txn: dict[str, Any],
    *,
    bulk_reference: Optional[str] = None,
) -> bool:
    from app.services.sepay_sync_service import _parse_amount_in, _txn_id

    amount_in = _parse_amount_in(txn.get('amount_in'))
    if amount_in <= 0:
        return False

    sepay_id = _txn_id(txn)
    if sepay_id <= 0:
        return False

    resolved_ref = resolve_bulk_reference(txn, bulk_reference)
    if not resolved_ref:
        return False

    session = bulk_payment_session_repo.get_by_reference(db, resolved_ref)
    if not session or session.status != 'pending':
        return False

    expected = Decimal(str(session.expected_total or 0)).quantize(Decimal('0.01'))
    if expected > 0 and amount_in < expected:
        logger.warning(
            'SEPay bulk: underpayment ref=%s expected>=%s got=%s',
            resolved_ref,
            expected,
            amount_in,
        )
        return False

    invoice_ids = list(session.invoice_ids or [])
    if not invoice_ids:
        return False

    content = str(txn.get('transaction_content') or '').strip()
    recorded_any = False

    for invoice_id in invoice_ids:
        inv = invoice_repo.get(db, int(invoice_id))
        if not inv or is_invoice_financially_locked(inv):
            continue
        due = invoice_amount_due(db, inv)
        if due <= 0:
            continue
        payment_ref = f'{sepay_id}-bulk-{invoice_id}'
        if payment_repo.exists_by_reference(db, payment_ref):
            recorded_any = True
            continue
        payment_repo._create_payment_row(
            db,
            int(invoice_id),
            due,
            payment_method=SEPAY_PAYMENT_METHOD,
            payment_reference=payment_ref,
            notes=f'SEPay bulk {resolved_ref}: {content}'.strip()[:500] or None,
            created_by=session.created_by,
        )
        recorded_any = True

    if not recorded_any:
        return False

    bulk_payment_session_repo.mark_completed(db, session, sepay_id)
    logger.info('SEPay bulk: completed ref=%s sepay_id=%s invoices=%s', resolved_ref, sepay_id, len(invoice_ids))
    return True


def sync_bulk_sepay_session(db: Session, reference_code: str) -> BulkPaymentSession:
    from app.services.sepay_sync_service import sync_sepay_payments

    session = bulk_payment_session_repo.get_by_reference(db, reference_code)
    if not session:
        raise ValueError('Bulk payment session not found')
    if session.status != 'completed':
        sync_sepay_payments(db, bulk_reference=reference_code)
        session = bulk_payment_session_repo.get_by_reference(db, reference_code)
    if not session:
        raise ValueError('Bulk payment session not found')
    return session

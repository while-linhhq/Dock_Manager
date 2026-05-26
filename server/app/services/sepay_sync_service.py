import logging
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.repositories.invoice_repository import invoice_repo
from app.repositories.payment_repository import payment_repo
from app.repositories.port_config_repository import port_config_repo
from app.services.sepay_api_client import SepayApiError, default_transaction_date_min, list_transactions
from app.services.sepay_config_service import get_sepay_config, resolve_sepay_bank

logger = logging.getLogger('app.sepay.sync')

SEPAY_PAYMENT_METHOD = 'sepay_transfer'
LAST_SYNCED_TXN_KEY = 'sepay_last_synced_txn_id'


def _parse_amount_in(raw: Any) -> Decimal:
    try:
        return Decimal(str(raw or 0))
    except Exception:
        return Decimal('0')


def _txn_id(txn: dict[str, Any]) -> int:
    try:
        return int(txn.get('id') or 0)
    except (TypeError, ValueError):
        return 0


def _resolve_invoice_number(txn: dict[str, Any], invoice_number: Optional[str]) -> Optional[str]:
    code = txn.get('code')
    if code is not None and str(code).strip():
        resolved = str(code).strip()
        if invoice_number and resolved != invoice_number:
            return None
        return resolved

    if not invoice_number:
        return None

    content = str(txn.get('transaction_content') or '')
    if invoice_number in content:
        return invoice_number
    return None


def apply_incoming_transaction(db: Session, txn: dict[str, Any], invoice_number: Optional[str] = None) -> bool:
    amount_in = _parse_amount_in(txn.get('amount_in'))
    if amount_in <= 0:
        return False

    sepay_id = _txn_id(txn)
    if sepay_id <= 0:
        return False

    payment_ref = str(sepay_id)
    if payment_repo.exists_by_reference(db, payment_ref):
        return False

    resolved_number = _resolve_invoice_number(txn, invoice_number)
    if not resolved_number:
        return False

    invoice = invoice_repo.get_by_number(db, resolved_number)
    if not invoice:
        logger.debug('SEPay sync: no invoice for code=%s', resolved_number)
        return False

    if (invoice.payment_status or '').upper() == 'PAID':
        return False

    total = (invoice.total_amount or Decimal('0')).quantize(Decimal('0.01'))
    if total > 0 and amount_in < total:
        logger.warning(
            'SEPay sync: underpayment invoice=%s expected>=%s got=%s',
            resolved_number,
            total,
            amount_in,
        )
        return False

    pay_amount = amount_in if amount_in > 0 else total
    content = str(txn.get('transaction_content') or '').strip()
    payment_repo.create(
        db,
        invoice_id=invoice.id,
        amount=pay_amount,
        payment_method=SEPAY_PAYMENT_METHOD,
        payment_reference=payment_ref,
        notes=f'SEPay sync: {content}'.strip()[:500] or None,
        created_by=None,
    )
    logger.info('SEPay sync: recorded payment invoice=%s sepay_id=%s', resolved_number, payment_ref)
    return True


def _read_last_synced_txn_id(db: Session) -> int:
    row = port_config_repo.get_by_key(db, LAST_SYNCED_TXN_KEY)
    if not row or not (row.value or '').strip():
        return 0
    try:
        return int(str(row.value).strip())
    except ValueError:
        return 0


def _write_last_synced_txn_id(db: Session, txn_id: int) -> None:
    if txn_id <= 0:
        return
    port_config_repo.upsert(
        db,
        LAST_SYNCED_TXN_KEY,
        str(txn_id),
        description='ID giao dịch SEPay mới nhất đã quét (since_id cho lần sync sau)',
    )


def sync_sepay_payments(
    db: Session,
    *,
    invoice_number: Optional[str] = None,
    bulk_reference: Optional[str] = None,
) -> dict[str, Any]:
    cfg = get_sepay_config(db)
    if not cfg.api_token:
        return {'ok': False, 'reason': 'api_token_missing', 'recorded': 0, 'scanned': 0}

    resolved = resolve_sepay_bank(db)
    if not resolved:
        return {'ok': False, 'reason': 'bank_account_missing', 'recorded': 0, 'scanned': 0}

    bank_account = resolved.bank_account

    since_id = _read_last_synced_txn_id(db) if not invoice_number and not bulk_reference else None
    date_min = None if since_id else default_transaction_date_min(30)

    try:
        transactions = list_transactions(
            cfg.api_token,
            account_number=bank_account,
            since_id=since_id,
            limit=200 if invoice_number or bulk_reference else 100,
            transaction_date_min=date_min,
        )
    except SepayApiError as exc:
        logger.warning('SEPay sync failed: %s', exc)
        return {'ok': False, 'reason': str(exc), 'recorded': 0, 'scanned': 0}

    recorded = 0
    max_txn_id = since_id or 0

    from app.services.bulk_sepay_service import apply_bulk_incoming_transaction

    for txn in transactions:
        txn_id = _txn_id(txn)
        if txn_id > max_txn_id:
            max_txn_id = txn_id
        if bulk_reference:
            if apply_bulk_incoming_transaction(db, txn, bulk_reference=bulk_reference):
                recorded += 1
        elif apply_incoming_transaction(db, txn, invoice_number=invoice_number):
            recorded += 1
        elif not invoice_number and apply_bulk_incoming_transaction(db, txn):
            recorded += 1

    if not invoice_number and not bulk_reference and max_txn_id > (since_id or 0):
        _write_last_synced_txn_id(db, max_txn_id)

    return {
        'ok': True,
        'recorded': recorded,
        'scanned': len(transactions),
        'since_id': since_id,
        'max_txn_id': max_txn_id,
    }

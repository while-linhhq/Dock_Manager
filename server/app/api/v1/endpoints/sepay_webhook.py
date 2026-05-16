import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.repositories.invoice_repository import invoice_repo
from app.repositories.payment_repository import payment_repo
from app.schemas.sepay import SepayBankInfoRead
from app.services.sepay_config_service import build_sepay_webhook_url, get_sepay_config

logger = logging.getLogger('app.sepay')
router = APIRouter()

SEPAY_SIGNATURE_MAX_AGE_SEC = 300
SEPAY_PAYMENT_METHOD = 'sepay_transfer'


def _verify_sepay_hmac(raw_body: str, signature: str, timestamp: int, secret: str) -> bool:
    secret = (secret or '').strip()
    if not secret:
        logger.warning('SEPAY_WEBHOOK_SECRET is not configured')
        return False
    if not signature or not timestamp:
        return False
    if abs(time.time() - timestamp) > SEPAY_SIGNATURE_MAX_AGE_SEC:
        return False
    expected = (
        'sha256='
        + hmac.new(
            secret.encode('utf-8'),
            f'{timestamp}.{raw_body}'.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(signature, expected)


@router.get('/bank-info', response_model=SepayBankInfoRead)
def get_sepay_bank_info(
    request: FastAPIRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    cfg = get_sepay_config(db)
    account = cfg.bank_account
    bank = cfg.bank_name
    name = cfg.account_name
    webhook_url = build_sepay_webhook_url(db, request)
    if not account or not bank:
        raise HTTPException(
            status_code=503,
            detail='SEPay bank account is not configured on the server',
        )
    return SepayBankInfoRead(
        bank_account=account,
        bank_name=bank,
        account_name=name,
        webhook_url=webhook_url,
    )


@router.get('/webhook-url')
def get_sepay_webhook_url(
    request: FastAPIRequest,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    url = build_sepay_webhook_url(db, request)
    if not url:
        raise HTTPException(
            status_code=503,
            detail='Could not resolve public API base URL for webhook',
        )
    return {'webhook_url': url}


@router.post('/webhook')
async def sepay_webhook(request: FastAPIRequest, db: Session = Depends(get_db)):
    raw_body = (await request.body()).decode('utf-8')
    if not raw_body:
        raise HTTPException(status_code=400, detail='Empty body')

    signature = request.headers.get('x-sepay-signature', '')
    try:
        timestamp = int(request.headers.get('x-sepay-timestamp', '0') or '0')
    except ValueError:
        timestamp = 0

    sepay_cfg = get_sepay_config(db)
    if not _verify_sepay_hmac(raw_body, signature, timestamp, sepay_cfg.webhook_secret):
        raise HTTPException(status_code=401, detail='Invalid signature')

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='Invalid JSON') from exc

    sepay_id = data.get('id')
    if sepay_id is None:
        raise HTTPException(status_code=400, detail='Missing transaction id')

    transfer_type = (data.get('transferType') or '').strip().lower()
    if transfer_type != 'in':
        return {'success': True}

    payment_ref = str(sepay_id)
    if payment_repo.exists_by_reference(db, payment_ref):
        return {'success': True}

    code = data.get('code')
    if code is None or (isinstance(code, str) and not code.strip()):
        return {'success': True}

    invoice_number = str(code).strip()
    invoice = invoice_repo.get_by_number(db, invoice_number)
    if not invoice:
        logger.info('SEPay webhook: no invoice for code=%s', invoice_number)
        return {'success': True}

    try:
        transfer_amount = Decimal(str(data.get('transferAmount', 0)))
    except Exception:
        transfer_amount = Decimal('0')

    total = (invoice.total_amount or Decimal('0')).quantize(Decimal('0.01'))
    if transfer_amount < total:
        logger.warning(
            'SEPay webhook: underpayment invoice=%s expected>=%s got=%s',
            invoice_number,
            total,
            transfer_amount,
        )
        return {'success': True}

    pay_amount = transfer_amount if transfer_amount > 0 else total
    payment_repo.create(
        db,
        invoice_id=invoice.id,
        amount=pay_amount,
        payment_method=SEPAY_PAYMENT_METHOD,
        payment_reference=payment_ref,
        notes=f'SEPay auto: {data.get("content") or ""}'.strip()[:500] or None,
        created_by=None,
    )
    logger.info('SEPay webhook: recorded payment for invoice=%s sepay_id=%s', invoice_number, payment_ref)
    return {'success': True}

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.schemas.sepay import SepayBankInfoRead, SepaySyncResultRead
from app.services.sepay_config_service import get_sepay_config, resolve_sepay_bank, verify_cron_secret
from app.services.sepay_sync_service import sync_sepay_payments

logger = logging.getLogger('app.sepay')
router = APIRouter()


@router.get('/bank-info', response_model=SepayBankInfoRead)
def get_sepay_bank_info(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    cfg = get_sepay_config(db)
    resolved = resolve_sepay_bank(db)
    if not resolved:
        if not cfg.api_token:
            raise HTTPException(
                status_code=503,
                detail='Chưa cấu hình SEPay API token hoặc tài khoản ngân hàng',
            )
        raise HTTPException(
            status_code=503,
            detail='Không lấy được tài khoản ngân hàng từ SEPay API. Kiểm tra token và tài khoản trên my.sepay.vn',
        )
    return SepayBankInfoRead(
        bank_account=resolved.bank_account,
        bank_name=resolved.bank_name,
        account_name=resolved.account_name,
        sync_configured=bool(cfg.api_token),
    )


@router.post('/sync', response_model=SepaySyncResultRead)
def post_sepay_sync(
    invoice_number: Optional[str] = Query(None, description='Chỉ quét giao dịch cho một hóa đơn'),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Đồng bộ giao dịch từ SEPay API (JWT)."""
    result = sync_sepay_payments(db, invoice_number=invoice_number)
    return SepaySyncResultRead(**result)


@router.post('/sync/cron', response_model=SepaySyncResultRead)
def post_sepay_sync_cron(
    invoice_number: Optional[str] = Query(None),
    x_sepay_cron_secret: Optional[str] = Header(None, alias='X-Sepay-Cron-Secret'),
    db: Session = Depends(get_db),
):
    """Endpoint chỉ dành cho cron — bắt buộc X-Sepay-Cron-Secret."""
    if not verify_cron_secret(db, x_sepay_cron_secret):
        raise HTTPException(status_code=401, detail='Invalid cron secret')
    result = sync_sepay_payments(db, invoice_number=invoice_number)
    return SepaySyncResultRead(**result)

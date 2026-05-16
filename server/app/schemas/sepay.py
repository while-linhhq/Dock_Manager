from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SepayBankInfoRead(BaseModel):
    bank_account: str
    bank_name: str
    account_name: str
    sync_configured: bool = False


class InvoicePaymentStatusRead(BaseModel):
    payment_status: str
    paid_at: Optional[datetime] = None


class SepaySyncResultRead(BaseModel):
    ok: bool
    recorded: int = 0
    scanned: int = 0
    reason: Optional[str] = None
    since_id: Optional[int] = None
    max_txn_id: Optional[int] = None

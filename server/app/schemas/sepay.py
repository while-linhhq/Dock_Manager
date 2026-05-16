from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SepayBankInfoRead(BaseModel):
    bank_account: str
    bank_name: str
    account_name: str
    webhook_url: str = ''


class InvoicePaymentStatusRead(BaseModel):
    payment_status: str
    paid_at: Optional[datetime] = None

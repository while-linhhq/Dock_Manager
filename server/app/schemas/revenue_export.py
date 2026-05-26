from typing import List, Optional

from pydantic import BaseModel, Field


class RevenueInvoiceExportRequest(BaseModel):
    invoice_ids: List[int] = Field(..., min_length=1)
    list_kind: Optional[str] = Field(None, description='standard | ai')
    invoice_sub_tab: Optional[str] = Field(None, description='pending | paid | trash')


class RevenueFeeConfigExportRequest(BaseModel):
    fee_config_ids: List[int] = Field(..., min_length=1)


class RevenueInvoiceExportStatsRead(BaseModel):
    total_invoices: int

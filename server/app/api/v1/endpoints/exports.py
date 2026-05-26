from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.repositories.invoice_repository import invoice_repo
from app.schemas.revenue_export import (
    RevenueFeeConfigExportRequest,
    RevenueInvoiceExportRequest,
    RevenueInvoiceExportStatsRead,
)
from app.services.export_service import export_service

router = APIRouter()


def _excel_file_response(file_path: str) -> FileResponse:
    filename = file_path.split('/')[-1].split('\\')[-1]
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@router.get('/port-logs')
def export_port_logs(
    log_date: Optional[date] = None,
    ship_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    file_path = export_service.export_port_logs_excel(
        db,
        log_date=log_date,
        ship_id=ship_id,
        user_id=current_user.id,
    )
    return _excel_file_response(file_path)


@router.get('/revenue-invoices/stats', response_model=RevenueInvoiceExportStatsRead)
def revenue_invoice_export_stats(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return RevenueInvoiceExportStatsRead(
        total_invoices=invoice_repo.count_all_revenue_export(db),
    )


@router.post('/revenue-invoices/all')
def export_all_revenue_invoices(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        file_path = export_service.export_all_revenue_invoices_excel(
            db,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _excel_file_response(file_path)


@router.post('/revenue-invoices')
def export_revenue_invoices(
    body: RevenueInvoiceExportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        file_path = export_service.export_revenue_invoices_excel(
            db,
            body.invoice_ids,
            user_id=current_user.id,
            list_kind=body.list_kind,
            invoice_sub_tab=body.invoice_sub_tab,
            filters=body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _excel_file_response(file_path)


@router.post('/revenue-fee-configs')
def export_revenue_fee_configs(
    body: RevenueFeeConfigExportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        file_path = export_service.export_revenue_fee_configs_excel(
            db,
            body.fee_config_ids,
            user_id=current_user.id,
            filters=body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _excel_file_response(file_path)

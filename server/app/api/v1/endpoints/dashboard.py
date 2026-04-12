from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.stats import DashboardStats, DashboardSummaryRead
from app.repositories.vessel_repository import vessel_repo
from app.repositories.detection_repository import detection_repo
from app.repositories.order_repository import order_repo
from app.repositories.invoice_repository import invoice_repo
from app.repositories.camera_repository import camera_repo
from app.services.dashboard_summary_service import build_dashboard_summary

router = APIRouter()


@router.get('/summary', response_model=DashboardSummaryRead)
def get_dashboard_summary(
    period: Literal['day', 'month', 'year'] = Query('day'),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return build_dashboard_summary(db, period)


@router.get('/stats', response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    today = date.today()

    total_vessels = len(vessel_repo.get_all(db, limit=100000))
    detections_today = detection_repo.get_all(db, limit=100000)
    detections_today = [d for d in detections_today if d.created_at and d.created_at.date() == today]

    orders_today = [o for o in order_repo.get_all(db, limit=100000) if o.created_at and o.created_at.date() == today]
    completed_today = sum(1 for o in orders_today if o.status == 'COMPLETED')
    pending_orders = order_repo.count_by_status(db, 'PENDING')

    unpaid_invoices = invoice_repo.count_unpaid(db)

    # Revenue from completed orders today (simplified: count * avg fee placeholder)
    total_revenue_today = Decimal('0')

    active_cameras = len(camera_repo.get_active(db))

    return DashboardStats(
        total_vessels=total_vessels,
        total_detections_today=len(detections_today),
        pending_orders=pending_orders,
        completed_orders_today=completed_today,
        total_revenue_today=total_revenue_today,
        unpaid_invoices=unpaid_invoices,
        active_cameras=active_cameras,
    )

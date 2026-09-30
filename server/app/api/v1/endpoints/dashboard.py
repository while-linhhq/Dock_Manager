from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.stats import (
    DashboardDetectionAnalyticsRead,
    DashboardStats,
    DashboardSummaryRead,
    DashboardSystemOverviewRead,
)
from app.repositories.vessel_repository import vessel_repo
from app.repositories.detection_repository import detection_repo
from app.repositories.order_repository import order_repo
from app.repositories.invoice_repository import invoice_repo
from app.repositories.camera_repository import camera_repo
from app.services.dashboard_analytics_service import build_detection_analytics
from app.services.dashboard_summary_service import build_dashboard_summary
from app.services.dashboard_system_service import build_system_overview

router = APIRouter()


@router.get('/summary', response_model=DashboardSummaryRead)
def get_dashboard_summary(
    period: Literal['day', 'month', 'year'] = Query('day'),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return build_dashboard_summary(db, period)


@router.get('/system-overview', response_model=DashboardSystemOverviewRead)
def get_system_overview(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return build_system_overview(db)


@router.get('/detection-analytics', response_model=DashboardDetectionAnalyticsRead)
def get_detection_analytics(
    period: Literal['day', 'week', 'month', 'year'] = Query('day'),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Bốn widget phân tích của dashboard, tính bằng aggregate ở SQL.

    Endpoint chỉ kiểm tra tham số rồi gọi service — không có SQL ở đây. Xem
    `app/services/dashboard_analytics_service.py` để biết cửa sổ thời gian:
    `by_hour` cố định 24 giờ gần nhất, ba tổng hợp còn lại theo `period`.

    Bộ giá trị `period` khớp `/dashboard/summary` (`day` | `month` | `year`) và có
    thêm `week`; `year` là nhánh Task 18 thêm để nút "Năm" của client không 422.
    """
    return build_detection_analytics(db, period)


@router.get('/stats', response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    today = date.today()

    # Tất cả chỉ số đều là COUNT ở SQL — không nạp bảng nào về Python. Ngữ nghĩa
    # "hôm nay" giữ nguyên bản cũ: so phần ngày của `created_at` với ngày máy chủ,
    # row có `created_at IS NULL` không được đếm.
    total_vessels = vessel_repo.count_filtered(db)
    total_detections_today = detection_repo.count_created_on(db, today)
    completed_orders_today = order_repo.count_created_on(db, today, status='COMPLETED')
    pending_orders = order_repo.count_by_status(db, 'PENDING')

    unpaid_invoices = invoice_repo.count_unpaid(db)

    # Revenue from completed orders today (simplified: count * avg fee placeholder)
    total_revenue_today = Decimal('0')

    active_cameras = camera_repo.count_all(db, active_only=True)

    return DashboardStats(
        total_vessels=total_vessels,
        total_detections_today=total_detections_today,
        pending_orders=pending_orders,
        completed_orders_today=completed_orders_today,
        total_revenue_today=total_revenue_today,
        unpaid_invoices=unpaid_invoices,
        active_cameras=active_cameras,
    )

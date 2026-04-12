"""Tổng hợp dashboard theo kỳ (ngày / tháng / năm), múi giờ Asia/Ho_Chi_Minh."""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, List, Literal, Tuple

from sqlalchemy import String, cast, func, literal
from sqlalchemy.orm import Session

from zoneinfo import ZoneInfo

from app.models.detection import Detection
from app.models.fee import FeeConfig
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.vessel import Vessel
from app.repositories.order_repository import order_repo

TZ = ZoneInfo('Asia/Ho_Chi_Minh')

Period = Literal['day', 'month', 'year']


def _period_bounds_utc(period: Period) -> Tuple[datetime, datetime, datetime, datetime]:
    """
    Trả (start_utc, end_utc, start_local, end_local).
    end_local là mốc đầu kỳ sau (exclusive khi so sánh < end_utc).
    """
    now = datetime.now(TZ)
    if period == 'day':
        start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
    elif period == 'month':
        start_local = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    else:
        start_local = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local.replace(year=start_local.year + 1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc, start_local, end_local


def _distinct_ships_detected(db: Session, start_utc: datetime, end_utc: datetime) -> int:
    ship_expr = func.coalesce(cast(Detection.vessel_id, String), Detection.track_id)
    q = db.query(func.count(func.distinct(ship_expr))).filter(
        Detection.created_at >= start_utc,
        Detection.created_at < end_utc,
    )
    return int(q.scalar() or 0)


def _transient_fee_revenue(db: Session, start_utc: datetime, end_utc: datetime) -> Decimal:
    raw = (
        db.query(func.coalesce(func.sum(InvoiceItem.amount), 0))
        .select_from(InvoiceItem)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .join(FeeConfig, InvoiceItem.fee_config_id == FeeConfig.id)
        .filter(
            FeeConfig.unit == 'per_hour',
            Invoice.deleted_at.is_(None),
            Invoice.created_at >= start_utc,
            Invoice.created_at < end_utc,
        )
        .scalar()
    )
    return Decimal(str(raw or 0)).quantize(Decimal('0.01'))


def _auto_invoices_count(db: Session, start_utc: datetime, end_utc: datetime) -> int:
    return int(
        db.query(func.count(Invoice.id))
        .filter(
            Invoice.creation_source == 'AI',
            Invoice.deleted_at.is_(None),
            Invoice.created_at >= start_utc,
            Invoice.created_at < end_utc,
        )
        .scalar()
        or 0
    )


def _top_ships(
    db: Session, start_utc: datetime, end_utc: datetime, limit: int = 8
) -> Tuple[List[str], List[int]]:
    ship_key = func.coalesce(Vessel.ship_id, Detection.track_id, literal('KHÔNG XÁC ĐỊNH'))
    rows = (
        db.query(ship_key, func.count(Detection.id))
        .outerjoin(Vessel, Detection.vessel_id == Vessel.id)
        .filter(
            Detection.created_at >= start_utc,
            Detection.created_at < end_utc,
        )
        .group_by(ship_key)
        .order_by(func.count(Detection.id).desc())
        .limit(limit)
        .all()
    )
    labels = [str(r[0]) for r in rows]
    counts = [int(r[1]) for r in rows]
    return labels, counts


def _revenue_series(
    db: Session,
    period: Period,
    start_utc: datetime,
    end_utc: datetime,
    start_local: datetime,
) -> Tuple[List[str], List[float], List[float], List[float]]:
    invoices = (
        db.query(Invoice)
        .filter(
            Invoice.deleted_at.is_(None),
            Invoice.created_at >= start_utc,
            Invoice.created_at < end_utc,
        )
        .all()
    )

    if period == 'day':
        labels = [f'{h:02d}h' for h in range(24)]
        totals = [Decimal(0)] * 24
        ai_amt = [Decimal(0)] * 24
        manual_amt = [Decimal(0)] * 24
        for inv in invoices:
            if not inv.created_at:
                continue
            lt = inv.created_at.astimezone(TZ)
            h = lt.hour
            amt = Decimal(inv.total_amount or 0)
            totals[h] += amt
            if (inv.creation_source or '').upper() == 'AI':
                ai_amt[h] += amt
            else:
                manual_amt[h] += amt
    elif period == 'month':
        year, month = start_local.year, start_local.month
        _, last_day = monthrange(year, month)
        labels = [str(d) for d in range(1, last_day + 1)]
        totals = [Decimal(0)] * last_day
        ai_amt = [Decimal(0)] * last_day
        manual_amt = [Decimal(0)] * last_day
        for inv in invoices:
            if not inv.created_at:
                continue
            lt = inv.created_at.astimezone(TZ)
            if lt.year != year or lt.month != month:
                continue
            idx = lt.day - 1
            if idx < 0 or idx >= last_day:
                continue
            amt = Decimal(inv.total_amount or 0)
            totals[idx] += amt
            if (inv.creation_source or '').upper() == 'AI':
                ai_amt[idx] += amt
            else:
                manual_amt[idx] += amt
    else:
        y = start_local.year
        labels = [f'Th.{m}' for m in range(1, 13)]
        totals = [Decimal(0)] * 12
        ai_amt = [Decimal(0)] * 12
        manual_amt = [Decimal(0)] * 12
        for inv in invoices:
            if not inv.created_at:
                continue
            lt = inv.created_at.astimezone(TZ)
            if lt.year != y:
                continue
            idx = lt.month - 1
            amt = Decimal(inv.total_amount or 0)
            totals[idx] += amt
            if (inv.creation_source or '').upper() == 'AI':
                ai_amt[idx] += amt
            else:
                manual_amt[idx] += amt

    def _f(xs: List[Decimal]) -> List[float]:
        return [float(x) for x in xs]

    return labels, _f(totals), _f(ai_amt), _f(manual_amt)


def build_dashboard_summary(db: Session, period: Period) -> dict[str, Any]:
    start_utc, end_utc, start_local, _ = _period_bounds_utc(period)

    distinct_ships = _distinct_ships_detected(db, start_utc, end_utc)
    transient_rev = _transient_fee_revenue(db, start_utc, end_utc)
    auto_cnt = _auto_invoices_count(db, start_utc, end_utc)
    pending = order_repo.count_by_status(db, 'PENDING')
    top_labels, top_counts = _top_ships(db, start_utc, end_utc, 8)
    r_labels, r_tot, r_ai, r_man = _revenue_series(db, period, start_utc, end_utc, start_local)

    return {
        'period': period,
        'period_start': start_utc,
        'period_end': end_utc,
        'distinct_ships_detected': distinct_ships,
        'transient_fee_revenue': transient_rev,
        'auto_invoices_created': auto_cnt,
        'pending_orders': pending,
        'revenue_chart_labels': r_labels,
        'revenue_chart_totals': r_tot,
        'revenue_chart_ai': r_ai,
        'revenue_chart_manual': r_man,
        'top_ship_labels': top_labels,
        'top_ship_counts': top_counts,
    }

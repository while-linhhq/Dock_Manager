"""`/dashboard/stats` đếm bằng COUNT ở SQL — tương đương số liệu với bản Python cũ.

Test chạy qua đúng tầng FastAPI trên PostgreSQL thật, dùng **chung một session
chưa commit** với test (`dependency_overrides[get_db]`) và rollback ở teardown —
không để lại rác. Vì bảng thật đã có dữ liệu, assert của ca "biên ngày" là
**delta** trước/sau khi seed; ca tương đương thì so trực tiếp với bản port nguyên
văn logic cũ (`_legacy_stats`) đọc qua chính các repository.

Ngữ nghĩa phải giữ nguyên: `created_at.date()` (phần ngày của timestamp lưu trong
DB) so với `date.today()` (ngày theo giờ máy chủ), row có `created_at IS NULL` bị
bỏ qua. `created_at` của `detections`/`orders` là `timestamp without time zone`
nên phần ngày đọc ra chính là phần ngày đã lưu.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, insert, select

from app.api.deps import get_current_user
from app.db.session import SessionLocal, engine, get_db
from app.main import app
from app.models.camera import Camera
from app.models.detection import Detection
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.vessel import Vessel
from app.repositories.camera_repository import camera_repo
from app.repositories.detection_repository import detection_repo
from app.repositories.invoice_repository import invoice_repo
from app.repositories.order_repository import order_repo
from app.repositories.vessel_repository import vessel_repo

STATS_URL = '/api/v1/dashboard/stats'

# Số row tối đa một query được phép trả về: mọi thứ endpoint cần đều là COUNT
# (1 row/query), nên "một nhúm" là đủ rộng mà vẫn bắt được việc nạp cả bảng.
MAX_ROWS_PER_QUERY = 5


def _legacy_stats(db) -> dict:
    """Port nguyên văn `get_dashboard_stats` trước Task 9 (đọc qua repository).

    Đây là mốc so sánh: endpoint mới phải trả đúng những con số này.
    """
    today = date.today()

    total_vessels = len(vessel_repo.get_all(db, limit=100000))
    detections_today = detection_repo.get_all(db, limit=100000)
    detections_today = [
        d for d in detections_today if d.created_at and d.created_at.date() == today
    ]

    orders_today = [
        o for o in order_repo.get_all(db, limit=100000)
        if o.created_at and o.created_at.date() == today
    ]
    completed_today = sum(1 for o in orders_today if o.status == 'COMPLETED')
    pending_orders = order_repo.count_by_status(db, 'PENDING')

    unpaid_invoices = invoice_repo.count_unpaid(db)

    active_cameras = len(camera_repo.get_active(db))

    return {
        'total_vessels': total_vessels,
        'total_detections_today': len(detections_today),
        'pending_orders': pending_orders,
        'completed_orders_today': completed_today,
        'unpaid_invoices': unpaid_invoices,
        'active_cameras': active_cameras,
    }


def _naive_at(day: date, hour: int = 9) -> datetime:
    """Mốc naive đúng kiểu cột `created_at` (`timestamp without time zone`)."""
    return datetime.combine(day, time(hour=hour))


def _seed(session) -> SimpleNamespace:
    """Seed 1 bộ nhỏ (flush, KHÔNG commit): 3 detection + 5 đơn + camera/hoá đơn.

    Ba detection/đơn cố tình trải đủ ba trường hợp biên: tạo "hôm nay" (ngày máy
    chủ), tạo "hôm qua", và `created_at IS NULL`. Row `created_at IS NULL` phải
    insert bằng Core: gán `created_at=None` qua ORM sẽ bị `server_default now()`
    ghi đè nên test sẽ mất ý nghĩa.
    """
    tag = uuid4().hex[:12]
    today = date.today()
    yesterday = today - timedelta(days=1)

    vessel = Vessel(
        ship_id=f'dashstats-{tag}',
        name='Dashboard Stats Test',
        classification='unclassified',
    )
    session.add(vessel)
    session.flush()  # có id nhưng chưa commit

    camera = Camera(
        camera_name=f'dashstats-{tag}',
        rtsp_url=f'rtsp://dashstats/{tag}',
        is_active=True,
    )
    session.add(camera)
    session.add(
        Invoice(
            invoice_number=f'DASHSTATS-{tag}',
            subtotal=Decimal('10.00'),
            total_amount=Decimal('10.00'),
            payment_status='UNPAID',
            created_at=_naive_at(today),
            updated_at=_naive_at(today),
        )
    )
    session.flush()

    detection_today = Detection(
        vessel_id=vessel.id,
        track_id=f'dashstats-today-{tag}',
        start_time=_naive_at(today),
        created_at=_naive_at(today),
        confidence=0.9,
    )
    detection_yesterday = Detection(
        vessel_id=vessel.id,
        track_id=f'dashstats-yesterday-{tag}',
        start_time=_naive_at(yesterday),
        created_at=_naive_at(yesterday),
        confidence=0.9,
    )
    session.add_all([detection_today, detection_yesterday])
    session.flush()
    detection_null_id = session.execute(
        insert(Detection)
        .values(vessel_id=vessel.id, track_id=f'dashstats-null-{tag}', created_at=None)
        .returning(Detection.id)
    ).scalar()

    order_today = Order(
        order_number=f'DASHSTATS-TODAY-{tag}',
        vessel_id=vessel.id,
        status='COMPLETED',
        created_at=_naive_at(today, hour=10),
    )
    order_yesterday = Order(
        order_number=f'DASHSTATS-YESTERDAY-{tag}',
        vessel_id=vessel.id,
        status='COMPLETED',
        created_at=_naive_at(yesterday, hour=10),
    )
    order_pending_today = Order(
        order_number=f'DASHSTATS-PENDING-{tag}',
        vessel_id=vessel.id,
        status='PENDING',
        created_at=_naive_at(today, hour=11),
    )
    session.add_all([order_today, order_yesterday, order_pending_today])
    session.flush()
    order_null_id = session.execute(
        insert(Order)
        .values(
            order_number=f'DASHSTATS-NULL-{tag}',
            vessel_id=vessel.id,
            status='COMPLETED',
            created_at=None,
        )
        .returning(Order.id)
    ).scalar()

    return SimpleNamespace(
        detection_today_id=detection_today.id,
        detection_yesterday_id=detection_yesterday.id,
        detection_null_id=detection_null_id,
        order_today_id=order_today.id,
        order_yesterday_id=order_yesterday.id,
        order_null_id=order_null_id,
        pending_order_id=order_pending_today.id,
    )


@contextmanager
def _stats_client():
    """Session dùng chung với test + TestClient không lifespan (không bật pipeline)."""
    session = SessionLocal()
    try:
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1, is_active=True
        )
        # không dùng context manager: bỏ qua lifespan (không bật pipeline/GPU)
        client = TestClient(app)
        try:
            yield SimpleNamespace(session=session, client=client)
        finally:
            client.close()
    finally:
        session.rollback()
        session.close()
        app.dependency_overrides.clear()


@pytest.fixture()
def ctx():
    with _stats_client() as context:
        yield context


def _get_stats(client) -> dict:
    response = client.get(STATS_URL)
    assert response.status_code == 200, response.text[:300]
    return response.json()


def test_stats_match_legacy_python_implementation(ctx) -> None:
    """Số liệu endpoint trả về phải trùng **từng trường** với bản Python cũ."""
    _seed(ctx.session)

    legacy = _legacy_stats(ctx.session)
    body = _get_stats(ctx.client)

    for field, expected in legacy.items():
        assert body[field] == expected, f'{field}: endpoint={body[field]} legacy={expected}'
    assert Decimal(str(body['total_revenue_today'])) == Decimal('0')


def test_only_today_rows_are_counted_and_null_created_at_is_skipped(ctx) -> None:
    """Biên ngày theo giờ máy chủ: hôm nay +1, hôm qua và NULL không tính."""
    session = ctx.session
    before = _get_stats(ctx.client)

    seeded = _seed(session)

    # Bảo hiểm cho chính phép seed: đúng 1 detection + 1 đơn thật sự có
    # `created_at IS NULL` (nếu không, assert delta bên dưới mất ý nghĩa).
    null_detections = session.execute(
        select(func.count())
        .select_from(Detection)
        .where(Detection.id.in_([seeded.detection_null_id]), Detection.created_at.is_(None))
    ).scalar()
    null_orders = session.execute(
        select(func.count())
        .select_from(Order)
        .where(Order.id.in_([seeded.order_null_id]), Order.created_at.is_(None))
    ).scalar()
    assert null_detections == 1 and null_orders == 1

    after = _get_stats(ctx.client)

    # 3 detection seed (hôm nay/hôm qua/NULL) nhưng chỉ 1 row được tính.
    assert after['total_detections_today'] == before['total_detections_today'] + 1
    # 4 đơn seed: chỉ đơn COMPLETED tạo hôm nay được tính; đơn PENDING hôm nay
    # vào `pending_orders` (đếm theo status, không theo ngày).
    assert after['completed_orders_today'] == before['completed_orders_today'] + 1
    assert after['pending_orders'] == before['pending_orders'] + 1
    assert after['total_vessels'] == before['total_vessels'] + 1
    assert after['unpaid_invoices'] == before['unpaid_invoices'] + 1
    assert after['active_cameras'] == before['active_cameras'] + 1


def test_stats_does_not_load_whole_tables(ctx) -> None:
    """`GET /dashboard/stats` chỉ được phát COUNT, không query nào trả nhiều row."""
    _seed(ctx.session)  # có row thật trong bảng để bản nạp-cả-bảng lộ nguyên hình

    captured: list[tuple[int, str]] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        captured.append((cursor.rowcount, ' '.join(statement.split())))

    event.listen(engine, 'after_cursor_execute', _capture)
    try:
        response = ctx.client.get(STATS_URL)
    finally:
        event.remove(engine, 'after_cursor_execute', _capture)

    assert response.status_code == 200, response.text[:300]
    assert captured, 'không ghi nhận query nào cho /dashboard/stats'

    not_count = [stmt for _, stmt in captured if 'count(' not in stmt.lower()]
    assert not not_count, f'query không phải COUNT: {not_count[0][:300]}'

    worst = max(rowcount for rowcount, _ in captured)
    assert worst <= MAX_ROWS_PER_QUERY, [
        (rowcount, stmt[:200]) for rowcount, stmt in captured if rowcount > MAX_ROWS_PER_QUERY
    ]

    # 6 chỉ số ⇒ 6 COUNT; nhiều hơn là round-trip thừa.
    assert len(captured) <= 6, [(rowcount, stmt[:120]) for rowcount, stmt in captured]

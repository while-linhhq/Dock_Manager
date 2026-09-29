"""Phân trang danh sách: header `X-Total-Count` và kẹp `limit`.

Test đi qua đúng tầng FastAPI trên PostgreSQL thật, nhưng mọi bản ghi seed đều
nằm trong một transaction **chưa commit** và bị rollback ở teardown — không để
lại rác trong DB. Phần `detections` khoanh vùng assert theo `vessel_id` vừa
seed; phần `invoices` (bảng đang có dữ liệu thật) chỉ so **delta** của tổng
trước/sau khi seed nên không phụ thuộc số row sẵn có của môi trường.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.detection import Detection
from app.models.invoice import Invoice
from app.models.vessel import Vessel
from app.utils.pagination import MAX_PAGE_SIZE

LIST_URL = '/api/v1/detections/'
BASE_TIME = datetime(2026, 9, 30, 3, 0, 0, tzinfo=timezone.utc)

INVOICE_LIST_URL = '/api/v1/invoices/'
DISCOUNT_REQUESTS_URL = '/api/v1/invoices/discount-requests'


def _seed(session, *, visible: int, soft_deleted: int) -> SimpleNamespace:
    """Tạo 1 vessel + detection rows (flush, KHÔNG commit) và trả metadata.

    Row đã xoá mềm được đặt `created_at` mới nhất: nếu tầng truy vấn quên lọc
    `deleted_at`, chúng sẽ chen vào đầu cửa sổ phân trang và làm test đỏ.
    """
    vessel = Vessel(
        ship_id=f'test-pagination-{uuid4().hex[:12]}',
        name='Pagination Test',
        classification='unclassified',
    )
    session.add(vessel)
    session.flush()  # có id nhưng chưa commit

    visible_rows = [
        Detection(
            vessel_id=vessel.id,
            track_id=f'pagination-{uuid4().hex}',
            start_time=BASE_TIME - timedelta(seconds=i),
            created_at=BASE_TIME - timedelta(seconds=i),
            confidence=0.9,
        )
        for i in range(visible)
    ]
    deleted_rows = [
        Detection(
            vessel_id=vessel.id,
            track_id=f'pagination-{uuid4().hex}',
            start_time=BASE_TIME + timedelta(seconds=i + 1),
            created_at=BASE_TIME + timedelta(seconds=i + 1),
            confidence=0.9,
            deleted_at=BASE_TIME + timedelta(hours=1),
        )
        for i in range(soft_deleted)
    ]
    session.add_all(visible_rows + deleted_rows)
    session.flush()

    # id sắp theo created_at giảm dần = đúng thứ tự endpoint trả về.
    return SimpleNamespace(
        vessel_id=vessel.id,
        ship_id=vessel.ship_id,
        visible_count=visible,
        visible_ids=[row.id for row in visible_rows],
        soft_deleted_ids=[row.id for row in deleted_rows],
    )


@contextmanager
def _seeded_client(*, visible: int, soft_deleted: int):
    session = SessionLocal()
    try:
        seeded = _seed(session, visible=visible, soft_deleted=soft_deleted)
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, is_active=True)
        # không dùng context manager: bỏ qua lifespan (không bật pipeline/GPU)
        client = TestClient(app)
        try:
            seeded.client = client
            yield seeded
        finally:
            client.close()
    finally:
        session.rollback()
        session.close()
        app.dependency_overrides.clear()


@pytest.fixture()
def seeded():
    """Bộ nhỏ: 5 row hiển thị + 1 row đã xoá mềm."""
    with _seeded_client(visible=5, soft_deleted=1) as seeded_rows:
        yield seeded_rows


@pytest.fixture()
def client(seeded):
    return seeded.client


@pytest.fixture()
def seeded_bulk():
    """Bộ lớn hơn `MAX_PAGE_SIZE` để việc kẹp limit quan sát được thật."""
    with _seeded_client(visible=MAX_PAGE_SIZE + 5, soft_deleted=1) as seeded_rows:
        yield seeded_rows


@pytest.fixture()
def bulk_client(seeded_bulk):
    return seeded_bulk.client


def _total_header(response) -> int:
    raw = response.headers.get('X-Total-Count')
    assert raw is not None, 'thiếu header X-Total-Count'
    return int(raw)


def test_total_header_matches_unpaginated_count(client, seeded) -> None:
    response = client.get(LIST_URL, params={'vessel_id': seeded.vessel_id, 'limit': MAX_PAGE_SIZE})

    assert response.status_code == 200, response.text[:300]
    items = response.json()
    # tổng < MAX_PAGE_SIZE nên trang này chứa đủ, và header phải bằng đúng tổng.
    assert len(items) == seeded.visible_count
    assert _total_header(response) == seeded.visible_count


def test_window_returns_expected_slice(client, seeded) -> None:
    response = client.get(
        LIST_URL,
        params={'vessel_id': seeded.vessel_id, 'skip': 1, 'limit': 2},
    )

    assert response.status_code == 200, response.text[:300]
    assert [item['id'] for item in response.json()] == seeded.visible_ids[1:3]


def test_limit_over_max_is_clamped(bulk_client, seeded_bulk) -> None:
    response = bulk_client.get(
        LIST_URL,
        params={'vessel_id': seeded_bulk.vessel_id, 'limit': 9999},
    )

    assert response.status_code == 200, response.text[:300]
    items = response.json()
    assert len(items) == MAX_PAGE_SIZE
    # header là tổng thật, không phải số row của trang đã kẹp.
    assert _total_header(response) == seeded_bulk.visible_count


def test_limit_zero_is_clamped_to_one(client, seeded) -> None:
    response = client.get(LIST_URL, params={'vessel_id': seeded.vessel_id, 'limit': 0})

    assert response.status_code == 200, response.text[:300]
    assert len(response.json()) == 1
    assert _total_header(response) == seeded.visible_count


def test_skip_past_end_returns_empty_with_total(client, seeded) -> None:
    response = client.get(LIST_URL, params={'vessel_id': seeded.vessel_id, 'skip': 10**6})

    assert response.status_code == 200, response.text[:300]
    assert response.json() == []
    assert _total_header(response) == seeded.visible_count


def test_soft_deleted_rows_excluded_from_items_and_total(client, seeded) -> None:
    response = client.get(LIST_URL, params={'vessel_id': seeded.vessel_id, 'limit': MAX_PAGE_SIZE})

    assert response.status_code == 200, response.text[:300]
    ids = [item['id'] for item in response.json()]
    assert ids == seeded.visible_ids
    assert not set(seeded.soft_deleted_ids) & set(ids)
    assert _total_header(response) == seeded.visible_count


def test_total_header_matches_items_with_ship_id_filter(client, seeded) -> None:
    """Bộ lọc `ship_id` có JOIN nên tổng đếm được phải khớp đúng danh sách."""
    response = client.get(
        LIST_URL,
        params={'ship_id': seeded.ship_id.upper(), 'limit': MAX_PAGE_SIZE},
    )

    assert response.status_code == 200, response.text[:300]
    assert [item['id'] for item in response.json()] == seeded.visible_ids
    assert _total_header(response) == seeded.visible_count


# --------------------------------------------------------------------------- #
# Hoá đơn: bảng `invoices` đã có dữ liệu thật nên mọi assert là **delta**:
# đọc tổng trước khi seed, seed trong transaction chưa commit, rồi so tổng sau.
# --------------------------------------------------------------------------- #


@contextmanager
def _invoice_client():
    """Client dùng chung session với test để seed được **sau** khi đọc tổng gốc."""
    session = SessionLocal()
    try:
        app.dependency_overrides[get_db] = lambda: session
        # `username='admin'` để `require_discount_approver` cho qua ở endpoint discount.
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1, is_active=True, username='admin'
        )
        # không dùng context manager: bỏ qua lifespan (không bật pipeline/GPU)
        client = TestClient(app)
        try:
            yield session, client
        finally:
            client.close()
    finally:
        session.rollback()
        session.close()
        app.dependency_overrides.clear()


def _seed_invoices(
    session,
    *,
    unpaid: int,
    paid: int = 0,
    soft_deleted: int = 0,
) -> SimpleNamespace:
    """Seed hoá đơn tối thiểu (flush, KHÔNG commit) và trả metadata.

    `created_at` nằm ở tương lai nên các row vừa seed chắc chắn đứng đầu thứ tự
    `created_at desc` mặc định; row đã xoá mềm còn mới hơn nữa để nếu tầng truy
    vấn quên lọc `deleted_at` thì chúng chen lên đầu và test đỏ ngay.
    """
    future = datetime.now(timezone.utc) + timedelta(days=30)
    rows: list[Invoice] = []

    def _add(*, payment_status: str, deleted: bool) -> Invoice:
        idx = len(rows)
        row = Invoice(
            invoice_number=f'PAGINATION-{uuid4().hex[:20]}',
            subtotal=Decimal('10.00'),
            total_amount=Decimal('10.00'),
            payment_status=payment_status,
            created_at=(
                future + timedelta(hours=2) - timedelta(seconds=idx)
                if deleted
                else future - timedelta(seconds=idx)
            ),
            updated_at=future - timedelta(seconds=idx),
            deleted_at=(
                future + timedelta(hours=1) - timedelta(seconds=idx) if deleted else None
            ),
        )
        rows.append(row)
        return row

    unpaid_rows = [_add(payment_status='UNPAID', deleted=False) for _ in range(unpaid)]
    paid_rows = [_add(payment_status='PAID', deleted=False) for _ in range(paid)]
    soft_deleted_rows = [_add(payment_status='UNPAID', deleted=True) for _ in range(soft_deleted)]
    session.add_all(rows)
    session.flush()

    # id tăng dần = thứ tự `created_at desc` (và `deleted_at desc`) của endpoint.
    return SimpleNamespace(
        visible_ids=[row.id for row in unpaid_rows + paid_rows],
        unpaid_ids=[row.id for row in unpaid_rows],
        paid_ids=[row.id for row in paid_rows],
        soft_deleted_ids=[row.id for row in soft_deleted_rows],
    )


def _seed_discount_requests(
    session,
    *,
    pending: int,
    approved: int = 0,
) -> SimpleNamespace:
    """Seed hoá đơn có `discount_status` (flush, KHÔNG commit), mới nhất ở đầu."""
    future = datetime.now(timezone.utc) + timedelta(days=30)
    rows: list[Invoice] = []

    def _add(*, discount_status: str) -> Invoice:
        idx = len(rows)
        row = Invoice(
            invoice_number=f'PAGINATION-DR-{uuid4().hex[:17]}',
            subtotal=Decimal('10.00'),
            total_amount=Decimal('10.00'),
            payment_status='UNPAID',
            discount_status=discount_status,
            discount_requested_amount=Decimal('2.00'),
            created_at=future - timedelta(seconds=idx),
            updated_at=future - timedelta(seconds=idx),
        )
        rows.append(row)
        return row

    pending_rows = [_add(discount_status='pending') for _ in range(pending)]
    approved_rows = [_add(discount_status='approved') for _ in range(approved)]
    session.add_all(rows)
    session.flush()

    # id tăng dần = thứ tự `updated_at desc` của endpoint.
    return SimpleNamespace(
        pending_ids=[row.id for row in pending_rows],
        approved_ids=[row.id for row in approved_rows],
    )


def test_invoice_total_header() -> None:
    """`X-Total-Count` = tổng hoá đơn chưa xoá, không phải số row của trang."""
    with _invoice_client() as (session, client):
        before = _total_header(client.get(INVOICE_LIST_URL, params={'limit': 1}))
        seeded = _seed_invoices(session, unpaid=4, paid=1, soft_deleted=1)

        response = client.get(INVOICE_LIST_URL, params={'limit': MAX_PAGE_SIZE})

        assert response.status_code == 200, response.text[:300]
        ids = [item['id'] for item in response.json()]
        assert ids[: len(seeded.visible_ids)] == seeded.visible_ids
        assert not set(seeded.soft_deleted_ids) & set(ids)
        assert _total_header(response) == before + len(seeded.visible_ids)


def test_invoice_awaiting_payment_filter_keeps_total_consistent() -> None:
    """Tổng của `awaiting_payment=true` phải đếm đúng tập đã lọc (loại PAID)."""
    with _invoice_client() as (session, client):
        params = {'awaiting_payment': 'true', 'limit': 1}
        before = _total_header(client.get(INVOICE_LIST_URL, params=params))
        seeded = _seed_invoices(session, unpaid=3, paid=2)

        response = client.get(
            INVOICE_LIST_URL,
            params={'awaiting_payment': 'true', 'limit': MAX_PAGE_SIZE},
        )

        assert response.status_code == 200, response.text[:300]
        items = response.json()
        ids = [item['id'] for item in items]
        assert ids[: len(seeded.unpaid_ids)] == seeded.unpaid_ids
        assert not set(seeded.paid_ids) & set(ids)
        assert all(item['payment_status'] != 'PAID' for item in items)
        assert _total_header(response) == before + len(seeded.unpaid_ids)


def test_invoice_deleted_only_total() -> None:
    """`deleted_only=true` đếm riêng tập hoá đơn đã xoá mềm."""
    with _invoice_client() as (session, client):
        params = {'deleted_only': 'true', 'limit': 1}
        before = _total_header(client.get(INVOICE_LIST_URL, params=params))
        seeded = _seed_invoices(session, unpaid=2, soft_deleted=3)

        response = client.get(
            INVOICE_LIST_URL,
            params={'deleted_only': 'true', 'limit': MAX_PAGE_SIZE},
        )

        assert response.status_code == 200, response.text[:300]
        ids = [item['id'] for item in response.json()]
        assert ids[: len(seeded.soft_deleted_ids)] == seeded.soft_deleted_ids
        assert not set(seeded.visible_ids) & set(ids)
        assert _total_header(response) == before + len(seeded.soft_deleted_ids)


def test_discount_requests_total_header() -> None:
    """Tổng của `/discount-requests` đếm theo `discount_status`, không phải mọi hoá đơn."""
    with _invoice_client() as (session, client):
        pending_before = _total_header(
            client.get(DISCOUNT_REQUESTS_URL, params={'status': 'pending', 'limit': 1})
        )
        approved_before = _total_header(
            client.get(DISCOUNT_REQUESTS_URL, params={'status': 'approved', 'limit': 1})
        )
        seeded = _seed_discount_requests(session, pending=3, approved=2)

        pending = client.get(
            DISCOUNT_REQUESTS_URL,
            params={'status': 'pending', 'limit': MAX_PAGE_SIZE},
        )
        approved = client.get(
            DISCOUNT_REQUESTS_URL,
            params={'status': 'approved', 'limit': MAX_PAGE_SIZE},
        )

        assert pending.status_code == 200, pending.text[:300]
        assert approved.status_code == 200, approved.text[:300]
        pending_ids = [item['id'] for item in pending.json()]
        assert pending_ids[: len(seeded.pending_ids)] == seeded.pending_ids
        assert not set(seeded.approved_ids) & set(pending_ids)
        assert _total_header(pending) == pending_before + len(seeded.pending_ids)
        assert _total_header(approved) == approved_before + len(seeded.approved_ids)

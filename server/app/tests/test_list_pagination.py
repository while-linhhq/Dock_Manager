"""Phân trang danh sách nhận diện: header `X-Total-Count` và kẹp `limit`.

Test đi qua đúng tầng FastAPI trên PostgreSQL thật, nhưng mọi bản ghi seed đều
nằm trong một transaction **chưa commit** và bị rollback ở teardown — không để
lại rác trong DB. Mọi assert đều khoanh vùng theo `vessel_id` vừa seed nên
không phụ thuộc dữ liệu sẵn có của môi trường.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.detection import Detection
from app.models.vessel import Vessel
from app.utils.pagination import MAX_PAGE_SIZE

LIST_URL = '/api/v1/detections/'
BASE_TIME = datetime(2026, 9, 30, 3, 0, 0, tzinfo=timezone.utc)


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

"""`X-Total-Count` cho đơn hàng, port-log, audit-log và các danh mục nhỏ.

Cùng công thức với `test_list_pagination.py`: một session `SessionLocal()` **chưa
commit** được tiêm qua `dependency_overrides[get_db]` và rollback ở teardown, nên
không để lại rác trong DB thật.

Khoanh vùng assert (bảng đã có dữ liệu thật nên không thể so tổng tuyệt đối):
- `port-logs`: lọc theo `ship_id` marker duy nhất → tổng đúng bằng số row vừa seed.
- `audit-logs`: lọc theo `user_id` **có thật** → so delta trên tổng của user đó.
- `vessels`: lọc theo `q` (marker uuid) → tổng đúng bằng số row vừa seed.
- `fee-configs`: nhánh `vessel_id` → tổng đúng bằng số row vừa seed.
- Các danh mục không có bộ lọc khoanh vùng → so delta trước/sau khi seed, đồng thời
  kiểm tra row vừa seed thật sự nằm trong trang trả về.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_group import CameraGroup
from app.models.fee import FeeConfig
from app.models.order import Order
from app.models.port import PortConfig
from app.models.port_log import PortLog
from app.models.role import Role
from app.models.user import User
from app.models.vessel import Vessel
from app.models.vessel_type import VesselType
from app.utils.pagination import (
    DEFAULT_CATALOG_LIMIT,
    DEFAULT_PAGE_SIZE,
    MAX_CATALOG_LIMIT,
    MAX_PAGE_SIZE,
)

ORDERS_URL = '/api/v1/orders/'
PORT_LOGS_URL = '/api/v1/port-logs/'
AUDIT_LOGS_URL = '/api/v1/audit-logs/'
VESSELS_URL = '/api/v1/vessels/'
USERS_URL = '/api/v1/users/'
CAMERAS_URL = '/api/v1/cameras/'
ROLES_URL = '/api/v1/roles/'
FEE_CONFIGS_URL = '/api/v1/fee-configs/'
VESSEL_TYPES_URL = '/api/v1/vessel-types/'
PORT_CONFIGS_URL = '/api/v1/port-configs/'
CAMERA_GROUPS_URL = '/api/v1/camera-groups/'

# `created_at` (hoặc cột sắp xếp tương ứng) ở tương lai ⇒ row vừa seed luôn đứng
# đầu thứ tự `... desc` mặc định, không bị dữ liệu thật đẩy ra khỏi trang.
FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


@contextmanager
def _api_client():
    """Client dùng chung session với test để seed được **sau** khi đọc tổng gốc."""
    session = SessionLocal()
    try:
        app.dependency_overrides[get_db] = lambda: session
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


def _total(response) -> int:
    raw = response.headers.get('X-Total-Count')
    assert raw is not None, 'thiếu header X-Total-Count'
    return int(raw)


def _items(response) -> list[dict]:
    assert response.status_code == 200, response.text[:300]
    return response.json()


def _delta_total(client, url: str, params: dict) -> int:
    """Tổng "trước" của đúng bộ lọc sẽ dùng ở assert (đọc từ header)."""
    return _total(client.get(url, params={**params, 'limit': 1}))


def _assert_catalog_page(response, seeded_ids: list[int]) -> int:
    """Trang danh mục nhỏ (trần 1000) phải chứa đủ row vừa seed và trả tổng thật."""
    items = _items(response)
    total = _total(response)
    assert len(items) == min(total, MAX_CATALOG_LIMIT)
    assert set(seeded_ids) <= {item['id'] for item in items}
    return total


# --------------------------------------------------------------------------- #
# Task 4 — /orders/, /port-logs/, /audit-logs/
# --------------------------------------------------------------------------- #


def _seed_orders(session, *, count: int, status: str = 'PENDING') -> list[int]:
    rows = [
        Order(
            order_number=f'PAGINATION-{uuid4().hex[:20]}',
            status=status,
            created_at=FUTURE - timedelta(seconds=index),
            updated_at=FUTURE - timedelta(seconds=index),
        )
        for index in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_orders_total_header() -> None:
    """`X-Total-Count` = tổng đơn hàng khớp bộ lọc, không phải số row của trang."""
    with _api_client() as (session, client):
        before = _delta_total(client, ORDERS_URL, {})
        seeded_ids = _seed_orders(session, count=4)

        response = client.get(ORDERS_URL, params={'limit': MAX_PAGE_SIZE})

        items = _items(response)
        assert [item['id'] for item in items][: len(seeded_ids)] == seeded_ids
        assert _total(response) == before + len(seeded_ids)


def test_orders_total_header_with_status_filter() -> None:
    """Tổng của `status=pending` phải đếm đúng tập đã lọc (bỏ qua đơn COMPLETED)."""
    with _api_client() as (session, client):
        params = {'status': 'pending'}
        before = _delta_total(client, ORDERS_URL, params)
        pending_ids = _seed_orders(session, count=3, status='PENDING')
        completed_ids = _seed_orders(session, count=2, status='COMPLETED')

        response = client.get(ORDERS_URL, params={**params, 'limit': MAX_PAGE_SIZE})

        items = _items(response)
        ids = [item['id'] for item in items]
        assert ids[: len(pending_ids)] == pending_ids
        assert not set(completed_ids) & set(ids)
        assert _total(response) == before + len(pending_ids)


def _seed_port_logs(
    session, *, ship_id: str, count: int, day_offset: int = 0
) -> tuple[list[int], datetime]:
    """Seed port-log của **một** mã tàu marker; trả (ids, ngày neo) để test `log_date`."""
    base = (datetime.now() + timedelta(days=30 + day_offset)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    rows = [
        PortLog(
            seq=i,
            track_id=f'pagination-{uuid4().hex}',
            voted_ship_id=ship_id,
            logged_at=base - timedelta(seconds=i),
            first_seen_at=base - timedelta(seconds=i),
            last_seen_at=base - timedelta(seconds=i),
            confidence=0.9,
            ocr_attempts=0,
            vote_summary={},
            schema_version=3,
        )
        for i in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows], base


def test_port_logs_total_header_with_ship_id_filter() -> None:
    """`ship_id` marker duy nhất ⇒ tổng tuyệt đối được, không cần delta."""
    with _api_client() as (session, client):
        ship_id = f'PAGINATION-{uuid4().hex[:12].upper()}'
        seeded_ids, _ = _seed_port_logs(session, ship_id=ship_id, count=3)

        response = client.get(PORT_LOGS_URL, params={'ship_id': ship_id, 'limit': MAX_PAGE_SIZE})

        items = _items(response)
        assert [item['id'] for item in items] == seeded_ids
        assert _total(response) == len(seeded_ids)


def test_port_logs_total_header_with_log_date_filter() -> None:
    """Tổng phải đếm theo đúng bộ lọc `log_date`, không phải mọi log của tàu."""
    with _api_client() as (session, client):
        ship_id = f'PAGINATION-{uuid4().hex[:12].upper()}'
        day_ids, base = _seed_port_logs(session, ship_id=ship_id, count=3)
        _seed_port_logs(session, ship_id=ship_id, count=2, day_offset=1)

        response = client.get(
            PORT_LOGS_URL,
            params={'ship_id': ship_id, 'log_date': str(base.date()), 'limit': MAX_PAGE_SIZE},
        )

        items = _items(response)
        assert [item['id'] for item in items] == day_ids
        assert _total(response) == len(day_ids)


def _seed_audit_logs(session, *, user_id: int, count: int) -> list[int]:
    rows = [
        AuditLog(
            user_id=user_id,
            action='UPDATE',
            entity_type='pagination-test',
            entity_id=index,
            created_at=FUTURE - timedelta(seconds=index),
        )
        for index in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_audit_logs_supports_skip_and_total() -> None:
    """`skip=1&limit=1` trả bản ghi thứ 2 và header vẫn là tổng của cả user."""
    with _api_client() as (session, client):
        user_id = session.query(User.id).order_by(User.id).first()
        assert user_id is not None, 'cần ít nhất một user thật để khoanh vùng audit_logs'
        user_id = user_id[0]

        before = _delta_total(client, AUDIT_LOGS_URL, {'user_id': user_id})
        seeded_ids = _seed_audit_logs(session, user_id=user_id, count=3)

        response = client.get(
            AUDIT_LOGS_URL,
            params={'user_id': user_id, 'skip': 1, 'limit': 1},
        )

        items = _items(response)
        assert [item['id'] for item in items] == [seeded_ids[1]]
        assert _total(response) == before + len(seeded_ids)


# --------------------------------------------------------------------------- #
# Task 5 — danh mục: /vessels/, /users/, /cameras/, /roles/, /fee-configs/,
# /vessel-types/, /port-configs/, /camera-groups/
# --------------------------------------------------------------------------- #


def _seed_vessels(session, *, marker: str, count: int, name_only: bool = False) -> list[int]:
    """`name_only=True`: marker chỉ nằm ở `name` để test nhánh tìm theo tên."""
    rows = []
    for index in range(count):
        rows.append(
            Vessel(
                ship_id=(
                    f'PAGE-{uuid4().hex[:10]}-{index:03d}'
                    if name_only
                    else f'{marker}-{index:03d}'
                ),
                name=(f'Catalog {marker.upper()} {index}' if name_only else f'Catalog {index}'),
                classification='unclassified',
                is_active=True,
            )
        )
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_vessels_total_header_and_catalog_cap() -> None:
    """`limit=5000` không bị 422 và bị kẹp ở trần danh mục 1000, không phải 200."""
    with _api_client() as (session, client):
        marker = f'testpage{uuid4().hex[:10]}'
        # Nhiều hơn MAX_PAGE_SIZE: nếu trần bị đặt nhầm thành 200 thì trang sẽ hụt row.
        seeded_ids = _seed_vessels(session, marker=marker, count=MAX_PAGE_SIZE + 5)

        response = client.get(
            VESSELS_URL,
            params={'q': marker.upper(), 'limit': 5000},
        )

        items = _items(response)
        assert len(items) == len(seeded_ids) > MAX_PAGE_SIZE
        assert len(items) <= MAX_CATALOG_LIMIT
        assert {item['id'] for item in items} == set(seeded_ids)
        assert _total(response) == len(seeded_ids)


def test_vessels_q_matches_name_case_insensitive() -> None:
    """`q` tìm cả `name` (không phân biệt hoa thường), không chỉ `ship_id`."""
    with _api_client() as (session, client):
        marker = f'testpage{uuid4().hex[:10]}'
        seeded_ids = _seed_vessels(session, marker=marker, count=2, name_only=True)

        response = client.get(VESSELS_URL, params={'q': marker, 'limit': MAX_CATALOG_LIMIT})

        items = _items(response)
        assert {item['id'] for item in items} == set(seeded_ids)
        assert _total(response) == len(seeded_ids)


def test_vessels_q_escapes_like_wildcards() -> None:
    """`%` và `_` trong `q` là ký tự thường, không được thành wildcard khớp tất cả."""
    with _api_client() as (session, client):
        marker = f'testpage{uuid4().hex[:10]}'
        literal_percent = _seed_vessels(session, marker=f'{marker}%z', count=1)
        _seed_vessels(session, marker=f'{marker}Az', count=1)
        literal_underscore = _seed_vessels(session, marker=f'{marker}_b', count=1)
        _seed_vessels(session, marker=f'{marker}Xb', count=1)

        percent = client.get(VESSELS_URL, params={'q': f'{marker}%z', 'limit': MAX_CATALOG_LIMIT})
        underscore = client.get(VESSELS_URL, params={'q': f'{marker}_b', 'limit': MAX_CATALOG_LIMIT})

        assert [item['id'] for item in _items(percent)] == literal_percent
        assert _total(percent) == 1
        assert [item['id'] for item in _items(underscore)] == literal_underscore
        assert _total(underscore) == 1


def test_vessels_q_matches_owner_and_registration_number() -> None:
    """`q` phủ đủ các trường `matchesAnyField` cũ của trang tàu, không chỉ mã/tên.

    Hồi quy Task 14: bộ lọc client cũ khớp `ship_id`, `name`, `owner`,
    `owner_info`, `registration_number`; bản server-side đầu tiên chỉ OR `ship_id`
    + `name` nên gõ tên chủ tàu ra "không có kết quả" dù tàu tồn tại.
    (`owner_info` chỉ là alias của form client — `toApiVesselPayload` gửi nó vào
    cột `owner` và API không trả về — nên phía server chỉ có 4 cột thật.)
    """
    with _api_client() as (session, client):
        owner_marker = f'testowner{uuid4().hex[:10]}'
        reg_marker = f'testreg{uuid4().hex[:10]}'
        by_owner = Vessel(
            ship_id=f'PAGE-{uuid4().hex[:10]}',
            name='Tàu thử chủ tàu',
            owner=f'Công ty TNHH {owner_marker}',
            classification='unclassified',
            is_active=True,
        )
        by_registration = Vessel(
            ship_id=f'PAGE-{uuid4().hex[:10]}',
            name='Tàu thử đăng kiểm',
            registration_number=f'DK-{reg_marker}',
            classification='unclassified',
            is_active=True,
        )
        session.add_all([by_owner, by_registration])
        session.flush()

        by_owner_response = client.get(
            VESSELS_URL, params={'q': owner_marker, 'limit': MAX_CATALOG_LIMIT}
        )
        assert [item['id'] for item in _items(by_owner_response)] == [by_owner.id]
        assert _total(by_owner_response) == 1

        # Không phân biệt hoa thường, và `q` được trim (như `matchesAnyField`).
        assert [
            item['id']
            for item in _items(
                client.get(
                    VESSELS_URL,
                    params={'q': f'  {owner_marker.upper()}  ', 'limit': MAX_CATALOG_LIMIT},
                )
            )
        ] == [by_owner.id]

        by_reg_response = client.get(
            VESSELS_URL, params={'q': reg_marker, 'limit': MAX_CATALOG_LIMIT}
        )
        assert [item['id'] for item in _items(by_reg_response)] == [by_registration.id]
        assert _total(by_reg_response) == 1

        # Từ khóa không khớp gì vẫn phải rỗng — OR thêm cột không được thành "khớp tất cả".
        no_match = client.get(
            VESSELS_URL,
            params={'q': f'khong-co-tau-nao-{owner_marker}', 'limit': MAX_CATALOG_LIMIT},
        )
        assert _items(no_match) == []
        assert _total(no_match) == 0


def _seed_users(session, *, count: int) -> list[int]:
    rows = [
        User(
            username=f'pagination-{uuid4().hex[:14]}',
            hashed_password='x',
            full_name='Pagination Test',
            is_active=True,
        )
        for _ in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_users_total_header() -> None:
    with _api_client() as (session, client):
        before = _delta_total(client, USERS_URL, {})
        seeded_ids = _seed_users(session, count=3)

        response = client.get(USERS_URL, params={'limit': MAX_CATALOG_LIMIT})

        assert _assert_catalog_page(response, seeded_ids) == before + len(seeded_ids)


def _seed_cameras(session, *, count: int) -> list[int]:
    rows = [
        Camera(
            camera_name=f'Pagination {index}',
            rtsp_url=f'rtsp://127.0.0.1:1/pagination-{uuid4().hex}',
            is_active=True,
        )
        for index in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_cameras_total_header() -> None:
    with _api_client() as (session, client):
        before = _delta_total(client, CAMERAS_URL, {})
        seeded_ids = _seed_cameras(session, count=3)

        response = client.get(CAMERAS_URL, params={'limit': MAX_CATALOG_LIMIT})

        assert _assert_catalog_page(response, seeded_ids) == before + len(seeded_ids)


def _seed_roles(session, *, count: int) -> list[int]:
    rows = [
        Role(role_name=f'pagination-{uuid4().hex[:14]}', description='Pagination Test')
        for _ in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_roles_total_header() -> None:
    with _api_client() as (session, client):
        before = _delta_total(client, ROLES_URL, {})
        seeded_ids = _seed_roles(session, count=2)

        response = client.get(ROLES_URL, params={'limit': MAX_CATALOG_LIMIT})

        assert _assert_catalog_page(response, seeded_ids) == before + len(seeded_ids)


def _seed_vessel_types(session, *, count: int) -> list[int]:
    rows = [
        VesselType(type_name=f'pagination-{uuid4().hex[:14]}', description='Pagination Test')
        for _ in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_vessel_types_total_header() -> None:
    with _api_client() as (session, client):
        before = _delta_total(client, VESSEL_TYPES_URL, {})
        seeded_ids = _seed_vessel_types(session, count=2)

        response = client.get(VESSEL_TYPES_URL, params={'limit': MAX_CATALOG_LIMIT})

        assert _assert_catalog_page(response, seeded_ids) == before + len(seeded_ids)


def _seed_port_configs(session, *, count: int) -> list[int]:
    rows = [
        PortConfig(key=f'pagination_{uuid4().hex[:14]}', value=str(index))
        for index in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_port_configs_total_header() -> None:
    with _api_client() as (session, client):
        before = _delta_total(client, PORT_CONFIGS_URL, {})
        seeded_ids = _seed_port_configs(session, count=3)

        response = client.get(PORT_CONFIGS_URL, params={'limit': MAX_CATALOG_LIMIT})

        assert _assert_catalog_page(response, seeded_ids) == before + len(seeded_ids)


def test_port_configs_default_limit_is_catalog_default() -> None:
    """Không truyền `limit` ⇒ mặc định danh mục 100, không phải 50 của nhóm phân trang."""
    with _api_client() as (session, client):
        before = _delta_total(client, PORT_CONFIGS_URL, {})
        # > DEFAULT_PAGE_SIZE để phân biệt được mặc định 100 và 50.
        seeded_ids = _seed_port_configs(session, count=DEFAULT_PAGE_SIZE + 10)

        response = client.get(PORT_CONFIGS_URL)

        items = _items(response)
        total = _total(response)
        assert total == before + len(seeded_ids) > DEFAULT_PAGE_SIZE
        assert len(items) == min(total, DEFAULT_CATALOG_LIMIT)


def _seed_camera_groups(session, *, count: int) -> list[int]:
    rows = [
        CameraGroup(name=f'pagination-{uuid4().hex[:14]}', is_active=True)
        for _ in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_camera_groups_total_header() -> None:
    with _api_client() as (session, client):
        before = _delta_total(client, CAMERA_GROUPS_URL, {})
        seeded_ids = _seed_camera_groups(session, count=2)

        response = client.get(CAMERA_GROUPS_URL, params={'limit': MAX_CATALOG_LIMIT})

        assert _assert_catalog_page(response, seeded_ids) == before + len(seeded_ids)


def _seed_fee_configs(session, *, vessel_id: int, count: int) -> list[int]:
    rows = [
        FeeConfig(
            vessel_id=vessel_id,
            fee_name=f'Pagination {index}',
            base_fee=Decimal('10.00'),
            unit='per_month',
            is_active=True,
        )
        for index in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return [row.id for row in rows]


def test_fee_configs_total_header() -> None:
    with _api_client() as (session, client):
        before = _delta_total(client, FEE_CONFIGS_URL, {})
        vessel_ids = _seed_vessels(session, marker=f'testpage{uuid4().hex[:10]}', count=1)
        seeded_ids = _seed_fee_configs(session, vessel_id=vessel_ids[0], count=3)

        response = client.get(FEE_CONFIGS_URL, params={'limit': MAX_CATALOG_LIMIT})

        assert _assert_catalog_page(response, seeded_ids) == before + len(seeded_ids)


def test_fee_configs_total_scoped_by_vessel() -> None:
    """Nhánh lọc theo `vessel_id` cũng phải trả tổng của đúng tập đã lọc."""
    with _api_client() as (session, client):
        vessel_ids = _seed_vessels(session, marker=f'testpage{uuid4().hex[:10]}', count=1)
        seeded_ids = _seed_fee_configs(session, vessel_id=vessel_ids[0], count=2)

        response = client.get(
            FEE_CONFIGS_URL,
            params={'vessel_id': vessel_ids[0], 'limit': MAX_CATALOG_LIMIT},
        )

        items = _items(response)
        assert [item['id'] for item in items] == seeded_ids
        assert _total(response) == len(seeded_ids)

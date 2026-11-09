"""Bộ lọc + sắp xếp danh sách hoá đơn: 8 bộ lọc của trang thu nhập chạy ở SQL.

Test đi qua đúng tầng FastAPI trên PostgreSQL thật, nhưng mọi row seed nằm trong
một transaction **chưa commit** và bị rollback ở teardown — không để lại rác.
Mọi assert đều **khoanh vùng theo marker**: `q=<tag>` chỉ khớp hoá đơn vừa seed
(tag ngẫu nhiên nằm trong `invoice_number`), nên không phụ thuộc số row sẵn có
của môi trường (bảng `invoices` đang có dữ liệu thật).

Mốc thời gian seed là **naive UTC** — đúng như cột `created_at`
(`timestamp without time zone`) đang lưu trong DB; client đọc chuỗi API không
kèm offset và hiểu là UTC (xem `parseApiDate` của client).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
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
from app.models.order import Order
from app.models.user import User
from app.models.vessel import Vessel
from app.models.vessel_type import VesselType
from app.repositories.invoice_repository import invoice_repo
from app.utils.pagination import MAX_PAGE_SIZE

LIST_URL = '/api/v1/invoices/'

# Ngày 2026-12-01 theo giờ VN (+07) trải từ 2026-11-30T17:00Z tới 2026-12-01T16:59:59.999Z.
LOCAL_DAY_FROM = '2026-12-01T00:00:00+07:00'
LOCAL_DAY_TO = '2026-12-01T23:59:59.999000+07:00'


def _utc(*args: int) -> datetime:
    """Mốc UTC dạng naive, khớp kiểu cột `timestamp without time zone`."""
    return datetime(*args)


def _seed(session) -> SimpleNamespace:
    """Seed 2 loại tàu, 2 tàu, 1 user, 1 đơn, 4 detection, 6 hoá đơn; trả id để assert.

    Thời gian neo (đủ để kiểm tra biên ngày địa phương +07):
    * a1 = 2026-12-01T10:00Z (17:00 giờ VN 01/12) — trong ngày
    * a2 = 2026-12-01T09:59Z (16:59 giờ VN 01/12) — trong ngày
    * a3 = 2026-12-01T08:00Z (15:00 giờ VN 01/12) — trong ngày
    * n1 = 2026-11-30T16:59Z (23:59 giờ VN 30/11) — trước ngày
    * b1 = 2026-12-01T18:00Z (01:00 giờ VN 02/12) — sau ngày, đã xoá mềm
    * b2 = 2026-12-01T00:00Z (07:00 giờ VN 01/12) — trong ngày, đã xoá mềm
    """
    tag = uuid4().hex[:12]
    type_a = VesselType(type_name=f'filtertest-inv-a-{tag}')
    type_b = VesselType(type_name=f'filtertest-inv-b-{tag}')
    session.add_all([type_a, type_b])
    session.flush()  # có id nhưng chưa commit

    # Bảng `vessels` có CHECK: classification='monthly' ⇔ vessel_type_id NOT NULL.
    vessel_a = Vessel(
        ship_id=f'FILTERTEST-INV-A-{tag}',
        name='Filter Test Invoice A',
        classification='monthly',
        vessel_type_id=type_a.id,
    )
    vessel_b = Vessel(
        ship_id=f'FILTERTEST-INV-B-{tag}',
        name='Filter Test Invoice B',
        classification='monthly',
        vessel_type_id=type_b.id,
    )
    creator = User(username=f'filtertest-inv-{tag}', full_name=f'Filter Test {tag}')
    session.add_all([vessel_a, vessel_b, creator])
    session.flush()

    order = Order(
        order_number=f'FILTERTEST-INV-ORD-{tag}',
        vessel_id=vessel_a.id,
        created_by=creator.id,
    )
    session.add(order)
    session.flush()

    # d1 = 3600 giây (60 phút); d2 = 1200 giây (20 phút); d3 thiếu end_time.
    det_long = Detection(
        track_id=f'track-inv-{tag}-d1',
        vessel_id=vessel_a.id,
        start_time=_utc(2026, 12, 1, 10, 0, 0),
        end_time=_utc(2026, 12, 1, 11, 0, 0),
    )
    det_short = Detection(
        track_id=f'track-inv-{tag}-d2',
        vessel_id=vessel_a.id,
        start_time=_utc(2026, 12, 1, 9, 0, 0),
        end_time=_utc(2026, 12, 1, 9, 20, 0),
    )
    det_open = Detection(
        track_id=f'track-inv-{tag}-d3',
        vessel_id=vessel_b.id,
        start_time=_utc(2026, 12, 1, 8, 0, 0),
        end_time=None,
    )
    # d4 = 184 giây: 184/60 không biểu diễn được chính xác ở số thực double.
    det_odd = Detection(
        track_id=f'track-inv-{tag}-d4',
        vessel_id=vessel_b.id,
        start_time=_utc(2026, 12, 1, 6, 0, 0),
        end_time=_utc(2026, 12, 1, 6, 3, 4),
    )
    session.add_all([det_long, det_short, det_open, det_odd])
    session.flush()

    rows: dict[str, Invoice] = {}

    def add_row(key: str, **kwargs) -> Invoice:
        row = Invoice(
            invoice_number=f'INV-FILTERTEST-{tag}-{key.upper()}',
            subtotal=Decimal('10.00'),
            **kwargs,
        )
        rows[key] = row
        session.add(row)
        return row

    # a1: tàu A, neo 60 phút, có đơn, người tạo thật, tổng 100, chưa thanh toán.
    add_row(
        'a1',
        order_id=order.id,
        vessel_id=vessel_a.id,
        detection_id=det_long.id,
        total_amount=Decimal('100.00'),
        payment_status='UNPAID',
        creation_source='USER',
        created_by=creator.id,
        created_at=_utc(2026, 12, 1, 10, 0, 0),
        updated_at=_utc(2026, 12, 1, 10, 0, 0),
    )
    # a2: tàu A, neo 20 phút, hoá đơn AI (nhãn 'AI'), tổng 500, đã thanh toán,
    #     có snapshot ship_id (client ưu tiên snapshot khi tìm kiếm).
    add_row(
        'a2',
        vessel_id=vessel_a.id,
        detection_id=det_short.id,
        vessel_ship_id_snapshot=f'FILTERTEST-SNAP-{tag}',
        total_amount=Decimal('500.00'),
        payment_status='PAID',
        creation_source='AI',
        created_at=_utc(2026, 12, 1, 9, 59, 0),
        updated_at=_utc(2026, 12, 1, 9, 59, 0),
    )
    # n1: không gắn tàu, không có detection, có đơn, tổng 0.
    add_row(
        'n1',
        order_id=order.id,
        total_amount=Decimal('0.00'),
        payment_status='UNPAID',
        creation_source='USER',
        created_by=creator.id,
        created_at=_utc(2026, 11, 30, 16, 59, 0),
        updated_at=_utc(2026, 11, 30, 16, 59, 0),
    )
    # a3: hoá đơn AI thứ hai (tab AI sắp xếp theo ship_id/snapshot, không theo order_id),
    # neo 184 giây — số phút không biểu diễn chính xác được ở double.
    add_row(
        'a3',
        vessel_id=vessel_b.id,
        detection_id=det_odd.id,
        vessel_ship_id_snapshot=f'FILTERTEST-SNAP3-{tag}',
        total_amount=Decimal('250.00'),
        payment_status='UNPAID',
        creation_source='AI',
        created_at=_utc(2026, 12, 1, 8, 0, 0),
        updated_at=_utc(2026, 12, 1, 8, 0, 0),
    )
    # b1/b2: đã xoá mềm (thùng rác). b1 dùng lại d1 của a1 — chỉ số unique
    # `uq_invoices_active_detection_id` chỉ áp cho hoá đơn chưa xoá.
    add_row(
        'b1',
        vessel_id=vessel_b.id,
        detection_id=det_long.id,
        total_amount=Decimal('50.00'),
        payment_status='PARTIAL',
        creation_source='USER',
        created_by=creator.id,
        created_at=_utc(2026, 12, 1, 18, 0, 0),
        updated_at=_utc(2026, 12, 1, 18, 0, 0),
        deleted_at=_utc(2026, 12, 2, 0, 0, 0),
    )
    add_row(
        'b2',
        vessel_id=vessel_b.id,
        detection_id=det_open.id,
        total_amount=Decimal('300.00'),
        payment_status='UNPAID',
        creation_source='AI',
        created_at=_utc(2026, 12, 1, 0, 0, 0),
        updated_at=_utc(2026, 12, 1, 0, 0, 0),
        deleted_at=_utc(2026, 12, 1, 20, 0, 0),
    )
    session.flush()

    return SimpleNamespace(
        session=session,
        tag=tag,
        type_a_id=type_a.id,
        type_b_id=type_b.id,
        vessel_a_id=vessel_a.id,
        vessel_b_id=vessel_b.id,
        ship_a=vessel_a.ship_id,
        snap_a2=f'FILTERTEST-SNAP-{tag}',
        order_id=order.id,
        detection_long_id=det_long.id,
        detection_short_id=det_short.id,
        detection_open_id=det_open.id,
        creator_label=creator.full_name,
        creator_id=creator.id,
        ids=[rows[k].id for k in ('a1', 'a2', 'a3', 'n1', 'b1', 'b2')],
        **{f'{key}_id': rows[key].id for key in rows},
    )


@contextmanager
def _seeded_client():
    session = SessionLocal()
    try:
        seeded = _seed(session)
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
    with _seeded_client() as seeded_rows:
        yield seeded_rows


def _get(seeded, **params):
    response = seeded.client.get(LIST_URL, params={'limit': MAX_PAGE_SIZE, **params})
    assert response.status_code == 200, response.text[:300]
    return response


def _ids(response) -> list[int]:
    return [item['id'] for item in response.json()]


def _total(response) -> int:
    raw = response.headers.get('X-Total-Count')
    assert raw is not None, 'thiếu header X-Total-Count'
    return int(raw)


def test_invoice_search_matches_number_and_order_id(seeded) -> None:
    # `invoice_number`: khớp đúng một row, không phân biệt hoa thường.
    assert _ids(_get(seeded, q=f'{seeded.tag}-a1')) == [seeded.a1_id]

    # `order_id`/`vessel_id`/`detection_id` cast sang text; chỉ assert tập con vì
    # một id có thể là chuỗi con của trường khác trong dữ liệu thật.
    assert {seeded.a1_id, seeded.n1_id} <= set(_ids(_get(seeded, q=str(seeded.order_id))))
    assert {seeded.a1_id, seeded.a2_id} <= set(_ids(_get(seeded, q=str(seeded.vessel_a_id))))
    assert {seeded.a1_id} <= set(_ids(_get(seeded, q=str(seeded.detection_long_id))))

    # `vessel_ship_id` của client ưu tiên snapshot: a1 khớp ship_id thật, a2 khớp snapshot.
    assert set(_ids(_get(seeded, q=seeded.ship_a))) == {seeded.a1_id}
    assert set(_ids(_get(seeded, q=seeded.snap_a2))) == {seeded.a2_id}

    # `created_by_label`: nhãn người tạo thật, và nhãn 'AI' cho hoá đơn tự động.
    assert set(_ids(_get(seeded, q=seeded.creator_label))) == {seeded.a1_id, seeded.n1_id}
    assert set(_ids(_get(seeded, q='AI'))) & set(seeded.ids) == {seeded.a2_id, seeded.a3_id}

    # Needle được trim như client (`matchesAnyField`), chỉ khoảng trắng = không lọc.
    assert _ids(_get(seeded, q=f'  {seeded.tag}-a1  ')) == [seeded.a1_id]
    assert set(seeded.ids) - {seeded.b1_id, seeded.b2_id} <= set(_ids(_get(seeded, q='   ')))


def test_invoice_search_wildcards_are_escaped(seeded) -> None:
    """`%` và `_` trong `q` phải là ký tự thường, không phải wildcard của LIKE."""
    assert set(_ids(_get(seeded, q='%'))) & set(seeded.ids) == set()
    assert set(_ids(_get(seeded, q='_'))) & set(seeded.ids) == set()


def test_invoice_filter_vessel_and_type(seeded) -> None:
    assert set(_ids(_get(seeded, q=seeded.tag, vessel_id=seeded.vessel_a_id))) == {
        seeded.a1_id,
        seeded.a2_id,
    }
    assert set(_ids(_get(seeded, q=seeded.tag, vessel_type_id=seeded.type_a_id))) == {
        seeded.a1_id,
        seeded.a2_id,
    }
    # Loại B chỉ còn a3 chưa xoá; b1/b2 thuộc thùng rác.
    assert set(_ids(_get(seeded, q=seeded.tag, vessel_type_id=seeded.type_b_id))) == {
        seeded.a3_id
    }
    assert set(
        _ids(_get(seeded, q=seeded.tag, vessel_type_id=seeded.type_b_id, deleted_only=True))
    ) == {seeded.b1_id, seeded.b2_id}


def test_invoice_filter_created_range(seeded) -> None:
    """Biên ngày địa phương +07 quy đổi đúng sang instant UTC so với `created_at`."""
    whole_local_day = _get(
        seeded,
        q=seeded.tag,
        created_from=LOCAL_DAY_FROM,
        created_to=LOCAL_DAY_TO,
    )
    # n1 = 23:59 giờ VN 30/11 nằm ngoài ngày 01/12.
    assert set(_ids(whole_local_day)) == {seeded.a1_id, seeded.a2_id, seeded.a3_id}

    # Instant không kèm offset được hiểu là UTC (giống `parseApiDate` của client):
    # nếu bị hiểu là +07 thì a2 (09:59Z) và a3 (08:00Z) cũng lọt vào.
    from_only = _get(seeded, q=seeded.tag, created_from='2026-12-01T10:00:00')
    assert set(_ids(from_only)) == {seeded.a1_id}

    # Biên dưới tính cả giá trị bằng nhau.
    assert set(_ids(_get(seeded, q=seeded.tag, created_from='2026-12-01T09:59:00'))) == {
        seeded.a1_id,
        seeded.a2_id,
    }

    to_only = _get(seeded, q=seeded.tag, created_to='2026-11-30T16:59:00')
    assert set(_ids(to_only)) == {seeded.n1_id}
    assert _total(to_only) == 1


def test_invoice_min_max_total(seeded) -> None:
    # Biên tính cả giá trị bằng nhau (`total < min` / `total > max` mới bị loại).
    assert set(_ids(_get(seeded, q=seeded.tag, min_total=100))) == {
        seeded.a1_id,
        seeded.a2_id,
        seeded.a3_id,
    }
    assert set(_ids(_get(seeded, q=seeded.tag, max_total=100))) == {
        seeded.a1_id,
        seeded.n1_id,
    }
    assert set(_ids(_get(seeded, q=seeded.tag, min_total=100, max_total=500))) == {
        seeded.a1_id,
        seeded.a2_id,
        seeded.a3_id,
    }
    assert set(_ids(_get(seeded, q=seeded.tag, min_total=100.01))) == {
        seeded.a2_id,
        seeded.a3_id,
    }
    assert _ids(_get(seeded, q=seeded.tag, min_total=500.01)) == []


def test_invoice_min_berth_minutes(seeded) -> None:
    """Chuẩn là `getInvoiceBerthMinutes`: (end_time - start_time) / 60, thiếu dữ liệu → loại."""
    # d1 = 3600 giây = 60 phút, d2 = 1200 giây = 20 phút; biên tính cả giá trị bằng nhau.
    assert set(_ids(_get(seeded, q=seeded.tag, min_berth_minutes=60))) == {seeded.a1_id}
    assert set(_ids(_get(seeded, q=seeded.tag, min_berth_minutes=20))) == {
        seeded.a1_id,
        seeded.a2_id,
    }
    assert set(_ids(_get(seeded, q=seeded.tag, min_berth_minutes=20.1))) == {seeded.a1_id}
    assert _ids(_get(seeded, q=seeded.tag, min_berth_minutes=61)) == []

    # a3 = 184 giây. Client chia ở double (`184 / 60` = 3.066666666666667) rồi so với
    # ngưỡng cũng ở double; SQL phải so ở double chứ không được so ở numeric chính xác
    # (184/60 = 3.06666666666666666667 < 3.066666666666667 → sẽ loại oan row).
    assert set(_ids(_get(seeded, q=seeded.tag, min_berth_minutes='3.066666666666667'))) == {
        seeded.a1_id,
        seeded.a2_id,
        seeded.a3_id,
    }
    # Nhích lên đúng một double (3.0666666666666673) là a3 bị loại.
    assert set(_ids(_get(seeded, q=seeded.tag, min_berth_minutes='3.0666666666666671'))) == {
        seeded.a1_id,
        seeded.a2_id,
    }

    # `0` vẫn là một ngưỡng: n1 (không có detection) bị loại, khác hẳn "không lọc".
    assert set(_ids(_get(seeded, q=seeded.tag, min_berth_minutes=0))) == {
        seeded.a1_id,
        seeded.a2_id,
        seeded.a3_id,
    }
    # Thùng rác: b1 có d1 (60 phút) lọt, b2 có detection thiếu end_time nên bị loại.
    assert set(_ids(_get(seeded, q=seeded.tag, deleted_only=True, min_berth_minutes=0))) == {
        seeded.b1_id
    }
    assert _ids(_get(seeded, q=seeded.tag, deleted_only=True, min_berth_minutes=60.5)) == []


def test_invoice_new_filters_combine_with_mode_filters(seeded) -> None:
    """Bộ lọc mới là điều kiện độc lập, áp dụng trong mọi chế độ (không bị chế độ nuốt)."""
    # Thùng rác + khoảng tiền: b1 = 50 (dưới ngưỡng), b2 = 300.
    assert set(_ids(_get(seeded, q=seeded.tag, deleted_only=True, min_total=100))) == {
        seeded.b2_id
    }
    # Thùng rác + số phút neo: b1 = 60 phút, b2 thiếu end_time.
    assert set(_ids(_get(seeded, q=seeded.tag, deleted_only=True, min_berth_minutes=30))) == {
        seeded.b1_id
    }
    # Sub-tab "chờ thanh toán" (awaiting_payment) + tổng tiền.
    assert set(_ids(_get(seeded, q=seeded.tag, awaiting_payment=True, max_total=100))) == {
        seeded.a1_id,
        seeded.n1_id,
    }
    # payment_status=PAID + tổng tiền.
    assert set(_ids(_get(seeded, q=seeded.tag, payment_status='PAID', min_total=100))) == {
        seeded.a2_id
    }
    # Hai tab hoá đơn (nguồn tạo) + tìm kiếm.
    assert set(_ids(_get(seeded, q=seeded.tag, creation_source='AI'))) == {
        seeded.a2_id,
        seeded.a3_id,
    }
    assert set(_ids(_get(seeded, q=seeded.tag, exclude_creation_source='AI'))) == {
        seeded.a1_id,
        seeded.n1_id,
    }


def test_invoice_filters_apply_in_discount_mode(seeded) -> None:
    """Chế độ `discount_status` cũng nhận bộ lọc mới (không nằm trong chuỗi if/elif)."""
    response = _get(seeded, q=seeded.tag, min_total=100)
    assert set(_ids(response)) == {seeded.a1_id, seeded.a2_id, seeded.a3_id}

    # `/discount-requests` chưa expose bộ lọc mới, nên kiểm tra ở tầng repository:
    # cùng một query vừa lọc `discount_status` vừa lọc `q`/`min_total`.
    pending = invoice_repo._filtered_query(
        seeded.session,
        discount_status='none',
        q=seeded.tag,
        min_total=Decimal('100'),
    ).all()
    assert {row.id for row in pending} == {seeded.a1_id, seeded.a2_id, seeded.a3_id}


def test_invoice_total_reflects_filters(seeded) -> None:
    """Header `X-Total-Count` đếm đúng tập đã lọc, không phải cả bảng."""
    response = _get(seeded, q=seeded.tag, min_total=100)
    assert set(_ids(response)) == {seeded.a1_id, seeded.a2_id, seeded.a3_id}
    assert _total(response) == 3
    assert _total(_get(seeded, q=seeded.tag)) == 4

    window = _get(seeded, q=seeded.tag, min_total=100, skip=1, limit=1)
    assert _total(window) == 3
    assert len(_ids(window)) == 1

    assert _total(_get(seeded, q=seeded.tag, deleted_only=True, min_berth_minutes=0)) == 1


def test_invoice_sort_whitelist_and_order(seeded) -> None:
    # Mặc định `sort='time'` = `created_at desc`.
    assert _ids(_get(seeded, q=seeded.tag)) == [
        seeded.a1_id,
        seeded.a2_id,
        seeded.a3_id,
        seeded.n1_id,
    ]
    assert _ids(_get(seeded, q=seeded.tag, sort='created_at', order='asc')) == [
        seeded.n1_id,
        seeded.a3_id,
        seeded.a2_id,
        seeded.a1_id,
    ]

    # `total_amount` so theo số, không theo chuỗi.
    assert _ids(_get(seeded, q=seeded.tag, sort='total_amount', order='desc')) == [
        seeded.a2_id,
        seeded.a3_id,
        seeded.a1_id,
        seeded.n1_id,
    ]
    assert _ids(_get(seeded, q=seeded.tag, sort='total_amount', order='asc')) == [
        seeded.n1_id,
        seeded.a1_id,
        seeded.a3_id,
        seeded.a2_id,
    ]

    # `invoice_number` so theo chuỗi (cùng tiền tố, khác hậu tố A1/A2/A3/N1).
    assert _ids(_get(seeded, q=seeded.tag, sort='invoice_number', order='asc')) == [
        seeded.a1_id,
        seeded.a2_id,
        seeded.a3_id,
        seeded.n1_id,
    ]

    # `ship_order` ở tab thường = order_id; a1/n1 cùng đơn nên tiebreaker id desc,
    # còn a2/a3 không gắn đơn → giá trị rỗng luôn xuống cuối (id desc trong nhóm rỗng).
    tied = sorted([seeded.a1_id, seeded.n1_id], reverse=True)
    empty_tied = sorted([seeded.a2_id, seeded.a3_id], reverse=True)
    assert _ids(_get(seeded, q=seeded.tag, sort='ship_order', order='asc')) == [
        *tied,
        *empty_tied,
    ]
    # Tab AI (`creation_source=AI`): `ship_order` là ship_id (snapshot thắng), không
    # phải order_id — a2 = FILTERTEST-SNAP-…, a3 = FILTERTEST-SNAP3-….
    assert _ids(_get(seeded, q=seeded.tag, creation_source='AI', sort='ship_order')) == [
        seeded.a3_id,
        seeded.a2_id,
    ]

    # `payment_status`: PAID trước UNPAID khi tăng dần (trong nhóm bằng nhau: id desc).
    assert _ids(_get(seeded, q=seeded.tag, sort='payment_status', order='asc')) == [
        seeded.a2_id,
        *sorted([seeded.a1_id, seeded.a3_id, seeded.n1_id], reverse=True),
    ]

    # `deleted_at` chỉ có nghĩa ở thùng rác.
    assert _ids(_get(seeded, q=seeded.tag, deleted_only=True, sort='deleted_at', order='desc')) == [
        seeded.b1_id,
        seeded.b2_id,
    ]

    # `sort`/`order` lạ không được nội suy vào SQL, chỉ rơi về mặc định.
    default = _ids(_get(seeded, q=seeded.tag))
    assert _ids(_get(seeded, q=seeded.tag, sort="id; drop table invoices")) == default
    assert _ids(_get(seeded, q=seeded.tag, sort='total_amount', order='sideways')) == _ids(
        _get(seeded, q=seeded.tag, sort='total_amount', order='desc')
    )


def test_invoice_paging_with_equal_sort_keys_keeps_every_row(seeded) -> None:
    """Khóa sắp xếp bằng nhau (a1/n1 cùng order_id) vẫn phải có tiebreaker id.

    Đi từng trang `limit=1` như client sẽ đi: không lặp row ở trang sau, không mất
    row, và thứ tự trong nhóm bằng nhau là id giảm dần.
    """
    expected = [
        *sorted([seeded.a1_id, seeded.n1_id], reverse=True),
        *sorted([seeded.a2_id, seeded.a3_id], reverse=True),
    ]
    seen: list[int] = []
    skip = 0
    while True:
        response = _get(
            seeded,
            q=seeded.tag,
            sort='ship_order',
            order='asc',
            skip=skip,
            limit=1,
        )
        batch = _ids(response)
        seen.extend(batch)
        if not batch:
            break
        skip += 1

    assert seen == expected
    assert len(set(seen)) == 4
    assert _total(response) == 4

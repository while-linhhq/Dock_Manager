"""Bộ lọc + sắp xếp danh sách chạy ở SQL: trang bến, đơn hàng, port-log, audit-log.

Test đi qua đúng tầng FastAPI trên PostgreSQL thật, nhưng mọi row seed nằm trong
một transaction **chưa commit** và bị rollback ở teardown — không để lại rác.
Assert khoanh vùng theo `vessel_id` (hoặc theo `q` mang tag ngẫu nhiên) của dữ
liệu vừa seed nên không phụ thuộc số row sẵn có của môi trường.

Mốc thời gian seed là **naive UTC** — đúng như cột `start_time`/`created_at`
(`timestamp without time zone`) đang lưu trong DB; client đọc chuỗi API không
kèm offset và hiểu là UTC (xem `parseApiDate` của client). Riêng `berth_in_time`
là `timestamp with time zone` nên seed bằng datetime có tzinfo.

`test_sort_whitelist_orders_exactly` phủ **cả 6 khóa** của whitelist sắp xếp
(berth/time/ship_id/confidence/camera/status) theo đúng thứ tự id mong đợi, kèm
tiebreaker id: A/B cũng so thứ tự nhưng trên dữ liệu thật, còn test này ghim giá
trị kỳ vọng của từng khóa trên dữ liệu seed.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.boundary_crossing_event import BoundaryCrossingEvent
from app.models.camera import Camera
from app.models.detection import Detection
from app.models.order import Order
from app.models.port_log import PortLog
from app.models.user import User
from app.models.vessel import Vessel
from app.models.vessel_type import VesselType
from app.utils.pagination import MAX_PAGE_SIZE

LIST_URL = '/api/v1/detections/'
ORDERS_URL = '/api/v1/orders/'
PORT_LOGS_URL = '/api/v1/port-logs/'
AUDIT_LOGS_URL = '/api/v1/audit-logs/'

# Ngày 2026-09-30 theo giờ VN (+07) trải từ 2026-09-29T17:00Z tới 2026-09-30T16:59:59.999Z.
LOCAL_DAY_FROM = '2026-09-30T00:00:00+07:00'
LOCAL_DAY_TO = '2026-09-30T23:59:59.999000+07:00'
# 2026-09-30 17:00 giờ VN = 10:00Z — dùng để chứng minh offset được quy đổi.
LOCAL_5PM = '2026-09-30T17:00:00+07:00'

# `created_at` của đơn hàng / audit-log seed ở tương lai ⇒ row vừa seed luôn đứng
# đầu thứ tự `created_at desc` mặc định, không bị dữ liệu thật đẩy ra khỏi trang.
FUTURE = datetime.now(timezone.utc) + timedelta(days=30)

# Ngày 01/03/2032 theo giờ VN (+07) trải từ 2032-02-29T17:00Z tới 2032-03-01T16:59:59.999Z
# (2032 là năm nhuận — 29/02 tồn tại).
LOG_LOCAL_DAY_FROM = '2032-03-01T00:00:00+07:00'
LOG_LOCAL_DAY_TO = '2032-03-01T23:59:59.999000+07:00'


def _utc(*args: int) -> datetime:
    """Mốc UTC dạng naive, khớp kiểu cột `timestamp without time zone`."""
    return datetime(*args)


def _seed(session) -> SimpleNamespace:
    """Seed 2 vessel (2 loại tàu) + 8 detection + camera/event cho cột camera."""
    tag = uuid4().hex[:12]
    type_a = VesselType(type_name=f'filtertest-a-{tag}')
    type_b = VesselType(type_name=f'filtertest-b-{tag}')
    session.add_all([type_a, type_b])
    session.flush()  # có id nhưng chưa commit

    # Bảng `vessels` có CHECK: classification='monthly' ⇔ vessel_type_id NOT NULL.
    vessel_a = Vessel(
        ship_id=f'FILTERTEST-A-{tag}',
        name='Filter Test A',
        classification='monthly',
        vessel_type_id=type_a.id,
    )
    vessel_b = Vessel(
        ship_id=f'FILTERTEST-B-{tag}',
        name='Filter Test B',
        classification='monthly',
        vessel_type_id=type_b.id,
    )
    session.add_all([vessel_a, vessel_b])
    session.flush()

    rows: dict[str, Detection] = {}

    def add_row(key: str, **kwargs) -> Detection:
        row = Detection(track_id=f'track-{tag}-{key}', **kwargs)
        rows[key] = row
        session.add(row)
        return row

    # Vessel A: đủ biên ngày 30/09 giờ VN, đủ nhánh is_accepted và confidence.
    # created_at = start_time để thứ tự `time` xác định được; a2 có thêm
    # berth_in_time muộn hơn hẳn để thứ tự `berth` (mặc định) khác thứ tự `time`.
    add_row(
        'a1',
        vessel_id=vessel_a.id,
        start_time=_utc(2026, 9, 30, 10, 0, 0),  # 17:00 giờ VN ngày 30/09
        created_at=_utc(2026, 9, 30, 10, 0, 0),
        confidence=0.95,
        is_accepted=True,
    )
    add_row(
        'a2',
        vessel_id=vessel_a.id,
        start_time=_utc(2026, 9, 30, 9, 59, 0),  # 16:59 giờ VN ngày 30/09
        created_at=_utc(2026, 9, 30, 9, 59, 0),
        berth_in_time=datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc),
        confidence=0.75,
        is_accepted=False,
    )
    add_row(
        'a3',
        vessel_id=vessel_a.id,
        start_time=_utc(2026, 9, 30, 17, 0, 0),  # 00:00 giờ VN ngày 01/10
        created_at=_utc(2026, 9, 30, 17, 0, 0),
        confidence=0.50,
        is_accepted=None,
    )
    add_row(
        'a4',
        vessel_id=vessel_a.id,
        start_time=_utc(2026, 9, 29, 16, 59, 0),  # 23:59 giờ VN ngày 29/09
        created_at=_utc(2026, 9, 29, 16, 59, 0),
        confidence=0.95,  # bằng a1 → kiểm tra tiebreaker theo id
        is_accepted=None,
    )
    add_row(
        'a5',
        vessel_id=vessel_a.id,
        start_time=_utc(2026, 9, 30, 12, 0, 0),
        created_at=_utc(2026, 9, 30, 12, 0, 0),
        confidence=None,  # client coi confidence thiếu là 0
        is_accepted=True,
    )

    # Vessel B: loại tàu khác → bị `vessel_type_id` loại ra.
    add_row(
        'b1',
        vessel_id=vessel_b.id,
        start_time=_utc(2026, 9, 30, 13, 0, 0),
        created_at=_utc(2026, 9, 30, 13, 0, 0),
        confidence=0.60,
        is_accepted=True,
    )

    # Không gắn tàu: nhãn hiển thị rơi về id OCR (getDetectionShipLabel).
    add_row(
        'n1',
        vessel_id=None,
        start_time=_utc(2026, 9, 30, 11, 0, 0),
        created_at=_utc(2026, 9, 30, 11, 0, 0),
        confidence=0.30,
        is_accepted=None,
        ocr_results=[{'id': f'OCR-{tag}', 'conf': 1.0}],
    )
    # id OCR toàn khoảng trắng → trim rồi rỗng → nhãn mặc định (String.trim của JS).
    add_row(
        'n2',
        vessel_id=None,
        start_time=_utc(2026, 9, 30, 14, 0, 0),
        created_at=_utc(2026, 9, 30, 14, 0, 0),
        confidence=0.85,
        is_accepted=None,
        ocr_results=[{'id': '  \t ', 'conf': 1.0}],
    )

    # Cột `camera` lấy tên camera của event IN **sớm nhất** theo track_id.
    cam_x = Camera(camera_name='CAM-X', rtsp_url=f'rtsp://filtertest/{tag}/x')
    cam_y = Camera(camera_name='CAM-Y', rtsp_url=f'rtsp://filtertest/{tag}/y')
    session.add_all([cam_x, cam_y])
    session.flush()
    session.add_all(
        [
            # a1: một event IN → CAM-Y.
            BoundaryCrossingEvent(
                track_id=rows['a1'].track_id,
                camera_id=cam_y.id,
                direction='in',
                crossed_at=datetime(2026, 9, 30, 6, 0, tzinfo=timezone.utc),
            ),
            # a3: hai event IN → lấy cái sớm nhất (CAM-X), event muộn không được tính.
            BoundaryCrossingEvent(
                track_id=rows['a3'].track_id,
                camera_id=cam_y.id,
                direction='in',
                crossed_at=datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc),
            ),
            BoundaryCrossingEvent(
                track_id=rows['a3'].track_id,
                camera_id=cam_x.id,
                direction='in',
                crossed_at=datetime(2026, 9, 30, 8, 0, tzinfo=timezone.utc),
            ),
            # b1: chỉ có event OUT → không có camera IN → giá trị rỗng, xuống cuối.
            BoundaryCrossingEvent(
                track_id=rows['b1'].track_id,
                camera_id=cam_x.id,
                direction='out',
                crossed_at=datetime(2026, 9, 30, 7, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    session.flush()

    # --- Task 8: đơn hàng / port-log / audit-log ------------------------------
    # Mọi row mang tag ngẫu nhiên trong trường mà `q` tìm tới, nên `q=<tag>`
    # khoanh vùng được đúng tập vừa seed trên bảng đang có dữ liệu thật.
    orders: dict[str, Order] = {}

    def add_order(key: str, offset: int, **kwargs) -> Order:
        """`created_at` lệch nhau 100 giây ⇒ kiểm tra được khoảng thời gian."""
        row = Order(
            order_number=f'FILTERTEST-ORD-{tag}-{key.upper()}',
            created_at=FUTURE + timedelta(seconds=offset),
            updated_at=FUTURE + timedelta(seconds=offset),
            **kwargs,
        )
        orders[key] = row
        session.add(row)
        return row

    # ord1/ord2 cùng tàu A (2 loại tàu khác nhau), ord3 tàu B, ord4 không gắn tàu.
    add_order(
        'ord1', 300, vessel_id=vessel_a.id, status='PENDING',
        total_amount=Decimal('100.00'), description=f'FILTERTEST-CARGO-{tag}-A',
    )
    add_order(
        'ord2', 200, vessel_id=vessel_a.id, status='COMPLETED',
        total_amount=Decimal('500.00'), description='Gạo',
    )
    add_order(
        'ord3', 100, vessel_id=vessel_b.id, status='CANCELLED',
        total_amount=Decimal('0.00'), description=f'FILTERTEST-CARGO-{tag}-B',
    )
    add_order(
        'ord4', 0, vessel_id=None, status='PENDING',
        total_amount=Decimal('250.00'), description=f'FILTERTEST-CARGO-{tag}-N',
    )

    # pl1/pl2 = tàu A (17:00 và 16:59 giờ VN ngày 01/03/2032), pl3 = tàu B (23:59
    # giờ VN 29/02), pl4 = mã tàu không có trong `vessels` (00:00 giờ VN 02/03),
    # pl5 = thiếu `logged_at` (client luôn loại row này khi có khoảng ngày).
    logs: dict[str, PortLog] = {}

    def add_log(
        key: str,
        logged_at: Optional[datetime],
        *,
        track_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        logs[key] = PortLog(
            seq=0,
            track_id=track_id or f'filtertest-{tag}-{key}',
            logged_at=logged_at,
            first_seen_at=logged_at,
            last_seen_at=logged_at,
            vote_summary={},
            ocr_attempts=0,
            schema_version=3,
            **kwargs,
        )
        session.add(logs[key])

    # `PortLog.logged_at` có default (Python + `now()` phía DB) nên phải ghi bằng
    # Core insert mới tạo được row thiếu thời gian — đúng nhánh "thiếu ngày" mà
    # `isoInLocalDateRange` của client loại bỏ khi có khoảng.
    add_log('pl1', _utc(2032, 3, 1, 10, 0, 0), voted_ship_id=vessel_a.ship_id, confidence=0.95)
    # pl2 viết hoa phần hậu tố của track_id để chứng minh `q` không phân biệt hoa thường.
    add_log(
        'pl2',
        _utc(2032, 3, 1, 9, 59, 0),
        track_id=f'filtertest-{tag}-PL2',
        voted_ship_id=vessel_a.ship_id,
        confidence=0.50,
    )
    add_log('pl3', _utc(2032, 2, 29, 16, 59, 0), voted_ship_id=vessel_b.ship_id, confidence=None)
    add_log(
        'pl4', _utc(2032, 3, 1, 17, 0, 0),
        voted_ship_id=f'FILTERTEST-PL-UNMATCHED-{tag}', confidence=0.75,
    )
    session.flush()
    pl5_id = session.execute(
        insert(PortLog)
        .values(
            seq=0,
            track_id=f'filtertest-{tag}-pl5',
            logged_at=None,
            first_seen_at=None,
            last_seen_at=None,
            voted_ship_id=None,
            confidence=0.10,
            vote_summary={},
            ocr_attempts=0,
            schema_version=3,
        )
        .returning(PortLog.id)
    ).scalar_one()
    session.flush()

    # audit-log: cùng tag trong `action` (q/action) và `entity_type` (table_name).
    # al4 cố tình là action READ → bị `_AUDIT_LIST_SKIP_ACTIONS` ẩn, không được lọt
    # ra dù khớp `table_name`.
    live_user_id = session.query(User.id).order_by(User.id).first()
    assert live_user_id is not None, 'cần ít nhất một user thật để khoanh vùng audit_logs'
    live_user_id = live_user_id[0]
    record_marker = int(tag[:6], 16)  # 6 ký tự hex → số duy nhất theo tag
    audits: dict[str, AuditLog] = {}

    def add_audit(key: str, offset: int, action: str, entity_kind: str, **kwargs) -> AuditLog:
        row = AuditLog(
            action=action,
            entity_type=f'filtertest-{tag}-{entity_kind}',
            created_at=FUTURE + timedelta(seconds=offset),
            **kwargs,
        )
        audits[key] = row
        session.add(row)
        return row

    add_audit(
        'al1', 300, f'FILTERTEST-{tag}-CREATE',
        'orders', entity_id=1, user_id=live_user_id,
    )
    add_audit(
        'al2', 200, f'FILTERTEST-{tag}-DELETE',
        'orders', entity_id=None, user_id=None,
    )
    add_audit(
        'al3', 100, f'FILTERTEST-{tag}-UPDATE',
        'vessels', entity_id=record_marker, user_id=live_user_id,
    )
    add_audit(
        'al4', 250, 'READ',
        'vessels', entity_id=4, user_id=None,
    )
    session.flush()

    return SimpleNamespace(
        tag=tag,
        vessel_a_id=vessel_a.id,
        vessel_b_id=vessel_b.id,
        type_a_id=type_a.id,
        type_b_id=type_b.id,
        ship_a=vessel_a.ship_id,
        ship_b=vessel_b.ship_id,
        ocr_id=f'OCR-{tag}',
        track_a1=rows['a1'].track_id,
        a_ids=[rows[k].id for k in ('a1', 'a2', 'a3', 'a4', 'a5')],
        b_ids=[rows['b1'].id],
        n_ids=[rows['n1'].id],
        order_tag=f'FILTERTEST-CARGO-{tag}',
        order_ids=[orders[k].id for k in ('ord1', 'ord2', 'ord3', 'ord4')],
        log_ids=[logs[k].id for k in ('pl1', 'pl2', 'pl3', 'pl4')] + [pl5_id],
        audit_ids=[audits[k].id for k in ('al1', 'al2', 'al3', 'al4')],
        visible_audit_ids=[audits[k].id for k in ('al1', 'al2', 'al3')],
        audit_user_id=live_user_id,
        user_label='Admin',
        user_email='admin@gmail.com',
        record_marker=record_marker,
        **{f'{k}_id': rows[k].id for k in rows},
        **{f'{k}_id': orders[k].id for k in orders},
        **{f'{k}_id': logs[k].id for k in logs},
        pl5_id=pl5_id,
        **{f'{k}_id': audits[k].id for k in audits},
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


def _get_at(seeded, url: str, **params):
    """GET một endpoint danh sách bất kỳ, luôn xin đủ trang để so cả tập id."""
    response = seeded.client.get(url, params={'limit': MAX_PAGE_SIZE, **params})
    assert response.status_code == 200, response.text[:300]
    return response


def _ids_at(seeded, url: str, **params) -> list[int]:
    return _ids(_get_at(seeded, url, **params))


def test_search_matches_ship_id_and_track_id(seeded) -> None:
    assert set(_ids(_get(seeded, q=seeded.ship_a))) == set(seeded.a_ids)
    assert _ids(_get(seeded, q=seeded.track_a1)) == [seeded.a1_id]
    # `q` cũng khớp vessel_id (cast sang text); chỉ assert tập seed là tập con vì
    # một vessel_id có thể là chuỗi con của vessel_id khác trong dữ liệu thật.
    assert set(seeded.a_ids) <= set(_ids(_get(seeded, q=str(seeded.vessel_a_id))))
    # Needle được trim như client (`matchesAnyField`), chỉ khoảng trắng = không lọc.
    assert set(_ids(_get(seeded, vessel_id=seeded.vessel_a_id, q=f'  {seeded.ship_a}  '))) == set(
        seeded.a_ids
    )
    assert set(_ids(_get(seeded, vessel_id=seeded.vessel_a_id, q='   '))) == set(seeded.a_ids)


def test_search_matches_ocr_label_when_detection_has_no_vessel(seeded) -> None:
    """`getDetectionShipLabel` rơi về id OCR khi detection không có tàu."""
    assert _ids(_get(seeded, q=seeded.ocr_id)) == seeded.n_ids


def test_search_wildcards_are_escaped(seeded) -> None:
    """`q='%'` phải khớp đúng ký tự `%`, không được biến thành "khớp tất cả"."""
    scoped = _get(seeded, vessel_id=seeded.vessel_a_id)
    assert len(_ids(scoped)) == len(seeded.a_ids)  # phạm vi lọc có row thật

    response = _get(seeded, vessel_id=seeded.vessel_a_id, q='%')

    assert _ids(response) == []
    assert _total(response) == 0


def test_filter_is_accepted_true_and_false(seeded) -> None:
    accepted = _get(seeded, vessel_id=seeded.vessel_a_id, is_accepted=True)
    rejected = _get(seeded, vessel_id=seeded.vessel_a_id, is_accepted=False)

    # true chỉ lấy đúng is_accepted = true; false gồm cả row NULL (chưa duyệt).
    assert set(_ids(accepted)) == {seeded.a1_id, seeded.a5_id}
    assert set(_ids(rejected)) == {seeded.a2_id, seeded.a3_id, seeded.a4_id}
    assert _total(accepted) == 2
    assert _total(rejected) == 3


def test_filter_vessel_type_id(seeded) -> None:
    type_a = _get(seeded, q=seeded.tag, vessel_type_id=seeded.type_a_id)
    type_b = _get(seeded, q=seeded.tag, vessel_type_id=seeded.type_b_id)

    assert set(_ids(type_a)) == set(seeded.a_ids)
    assert set(_ids(type_b)) == set(seeded.b_ids)
    assert _total(type_b) == 1


def test_filter_occurred_range_is_utc_instant(seeded) -> None:
    """Biên ngày địa phương +07 quy đổi đúng sang instant UTC."""
    whole_local_day = _get(
        seeded,
        vessel_id=seeded.vessel_a_id,
        occurred_from=LOCAL_DAY_FROM,
        occurred_to=LOCAL_DAY_TO,
    )
    # a3 = 00:00 ngày 01/10 giờ VN và a4 = 23:59 ngày 29/09 giờ VN nằm ngoài ngày 30/09.
    assert set(_ids(whole_local_day)) == {seeded.a1_id, seeded.a2_id, seeded.a5_id}

    # 17:00 giờ VN = 10:00Z → chỉ còn các row từ 10:00Z trở đi.
    from_only = _get(seeded, vessel_id=seeded.vessel_a_id, occurred_from=LOCAL_5PM)
    assert set(_ids(from_only)) == {seeded.a1_id, seeded.a3_id, seeded.a5_id}
    # Instant không kèm offset được hiểu là UTC (giống `parseApiDate` của client).
    naive_from = _get(seeded, vessel_id=seeded.vessel_a_id, occurred_from='2026-09-30T10:00:00')
    assert set(_ids(naive_from)) == {seeded.a1_id, seeded.a3_id, seeded.a5_id}

    to_only = _get(
        seeded,
        vessel_id=seeded.vessel_a_id,
        occurred_to='2026-09-29T23:59:59.999000+07:00',
    )
    assert set(_ids(to_only)) == {seeded.a4_id}


def test_filter_min_confidence(seeded) -> None:
    # Endpoint nhận 0..1 (client chia phần trăm cho 100 trước khi gửi).
    high = _get(seeded, vessel_id=seeded.vessel_a_id, min_confidence=0.9)
    assert set(_ids(high)) == {seeded.a1_id, seeded.a4_id}

    # confidence NULL được client coi là 0 → chỉ lọt khi ngưỡng cũng là 0.
    above_zero = _get(seeded, vessel_id=seeded.vessel_a_id, min_confidence=0.05)
    assert set(_ids(above_zero)) == {seeded.a1_id, seeded.a2_id, seeded.a3_id, seeded.a4_id}
    zero = _get(seeded, vessel_id=seeded.vessel_a_id, min_confidence=0.0)
    assert set(_ids(zero)) == set(seeded.a_ids)


def test_sort_by_confidence_asc_and_desc(seeded) -> None:
    desc = _get(seeded, vessel_id=seeded.vessel_a_id, sort='confidence', order='desc')
    asc = _get(seeded, vessel_id=seeded.vessel_a_id, sort='confidence', order='asc')

    # a1/a4 cùng 0.95 → tiebreaker theo id cùng chiều với sort (không nhảy trang).
    assert _ids(desc) == [
        seeded.a4_id,
        seeded.a1_id,
        seeded.a2_id,
        seeded.a3_id,
        seeded.a5_id,
    ]
    assert _ids(asc) == [
        seeded.a5_id,
        seeded.a3_id,
        seeded.a2_id,
        seeded.a1_id,
        seeded.a4_id,
    ]


def test_sort_unknown_key_falls_back_to_default(seeded) -> None:
    """`sort`/`order` lạ không được nội suy vào SQL, chỉ rơi về mặc định."""
    default = _ids(_get(seeded, vessel_id=seeded.vessel_a_id))
    unknown = _get(seeded, vessel_id=seeded.vessel_a_id, sort="id; drop table detections")
    unknown_order = _get(
        seeded, vessel_id=seeded.vessel_a_id, sort='confidence', order='sideways'
    )

    assert _ids(unknown) == default
    # Mặc định là `berth desc` (đúng thứ tự client đang thấy): a2 (berth 18:00Z) →
    # a3 (17:00Z) → a5 (12:00Z) → a1 (10:00Z) → a4 (29/09 16:59Z).
    assert default == [
        seeded.a2_id,
        seeded.a3_id,
        seeded.a5_id,
        seeded.a1_id,
        seeded.a4_id,
    ]
    assert _ids(unknown_order) == _ids(
        _get(seeded, vessel_id=seeded.vessel_a_id, sort='confidence', order='desc')
    )


# Thứ tự id mong đợi cho từng khóa của whitelist, phạm vi `q=<tag>` (8 row seed:
# a1..a5 của tàu A, b1 của tàu B, n1 có nhãn OCR, n2 nhãn mặc định).
#
# Giá trị từng cột:
#   start_time : a1=30/09 10:00Z, a2=09:59Z, a3=17:00Z, a4=29/09 16:59Z, a5=12:00Z,
#                b1=13:00Z, n1=11:00Z, n2=14:00Z
#   berth      : như start_time, riêng a2 có berth_in_time=18:00Z
#   nhãn       : a*=FILTERTEST-A-<tag>, b1=FILTERTEST-B-<tag>, n1=OCR-<tag>,
#                n2=KHÔNG XÁC ĐỊNH
#   confidence : a1=0.95, a2=0.75, a3=0.50, a4=0.95, a5=NULL→0, b1=0.60,
#                n1=0.30, n2=0.85
#   camera     : a1=CAM-Y, a3=CAM-X (event IN sớm nhất), còn lại rỗng
#   status     : Đã Xác Nhận = a1/a5/b1, Chờ Duyệt = phần còn lại
ORDER_CASES: dict[tuple[str, str], list[str]] = {
    ('berth', 'desc'): ['a2', 'a3', 'n2', 'b1', 'a5', 'n1', 'a1', 'a4'],
    ('berth', 'asc'): ['a4', 'a1', 'n1', 'a5', 'b1', 'n2', 'a3', 'a2'],
    ('time', 'desc'): ['a3', 'n2', 'b1', 'a5', 'n1', 'a1', 'a2', 'a4'],
    ('time', 'asc'): ['a4', 'a2', 'a1', 'n1', 'a5', 'b1', 'n2', 'a3'],
    ('ship_id', 'asc'): ['a1', 'a2', 'a3', 'a4', 'a5', 'b1', 'n2', 'n1'],
    ('ship_id', 'desc'): ['n1', 'n2', 'b1', 'a5', 'a4', 'a3', 'a2', 'a1'],
    ('confidence', 'asc'): ['a5', 'n1', 'a3', 'b1', 'a2', 'n2', 'a1', 'a4'],
    ('confidence', 'desc'): ['a4', 'a1', 'n2', 'a2', 'b1', 'a3', 'n1', 'a5'],
    # camera rỗng luôn xuống cuối ở cả hai chiều; trong nhóm rỗng thì id quyết định.
    ('camera', 'asc'): ['a3', 'a1', 'a2', 'a4', 'a5', 'b1', 'n1', 'n2'],
    ('camera', 'desc'): ['a1', 'a3', 'n2', 'n1', 'b1', 'a5', 'a4', 'a2'],
    ('status', 'asc'): ['a2', 'a3', 'a4', 'n1', 'n2', 'a1', 'a5', 'b1'],
    ('status', 'desc'): ['b1', 'a5', 'a1', 'n2', 'n1', 'a4', 'a3', 'a2'],
}


@pytest.mark.parametrize(('sort', 'order'), sorted(ORDER_CASES))
def test_sort_whitelist_orders_exactly(seeded, sort: str, order: str) -> None:
    """Mỗi khóa whitelist trả về đúng dãy id, kết thúc bằng tiebreaker id cùng chiều."""
    expected = [getattr(seeded, f'{key}_id') for key in ORDER_CASES[(sort, order)]]

    assert _ids(_get(seeded, q=seeded.tag, sort=sort, order=order)) == expected


def test_search_unknown_label_when_ocr_id_is_blank(seeded) -> None:
    """id OCR toàn khoảng trắng: trim rồi rỗng nên nhãn rơi về 'KHÔNG XÁC ĐỊNH'."""
    assert seeded.n2_id in _ids(_get(seeded, q='KHÔNG XÁC ĐỊNH'))


def test_paging_with_equal_sort_keys_keeps_every_row(seeded) -> None:
    """Khóa sắp xếp bằng nhau (a1/a4 cùng 0.95) vẫn phải có tiebreaker id.

    Đi từng trang `limit=2` như client sẽ đi: không được lặp row ở trang sau cũng
    không được mất row, và thứ tự trong nhóm bằng nhau là id giảm dần.
    """
    seen: list[int] = []
    skip = 0
    while True:
        response = _get(
            seeded,
            vessel_id=seeded.vessel_a_id,
            sort='confidence',
            order='desc',
            skip=skip,
            limit=2,
        )
        batch = _ids(response)
        seen.extend(batch)
        if len(batch) < 2:
            break
        skip += 2

    assert seen == [
        seeded.a4_id,
        seeded.a1_id,
        seeded.a2_id,
        seeded.a3_id,
        seeded.a5_id,
    ]
    assert len(set(seen)) == len(seen)


def test_total_reflects_filters(seeded) -> None:
    """Header `X-Total-Count` đếm đúng tập đã lọc, không phải cả bảng."""
    response = _get(seeded, q=seeded.tag, is_accepted=True)

    assert set(_ids(response)) == {seeded.a1_id, seeded.a5_id, seeded.b1_id}
    assert _total(response) == 3

    window = _get(seeded, q=seeded.tag, is_accepted=True, skip=1, limit=2)
    assert _total(window) == 3
    assert len(_ids(window)) == 2


# --------------------------------------------------------------------------- #
# Task 8 — bộ lọc + sắp xếp của /orders/, /port-logs/, /audit-logs/
#
# Mỗi test port đúng bộ lọc của trang client tương ứng:
#   * `/orders/`     — `OrdersView.tsx:40-80` (q, status, vessel_id,
#     vessel_type_id, created_from/to, min/max total).
#   * `/port-logs/`  — `StatisticsView.tsx:34-61` (q, vessel_type_id,
#     logged_from/to, min_confidence) bên cạnh hai tham số cũ `ship_id`/`log_date`.
#   * `/audit-logs/` — `BackupView.tsx:19-43` (q, table_name, action,
#     created_from/to) bên cạnh tham số cũ `user_id`.
#
# Mọi assert đều khoanh vùng theo `q=<tag>` (hoặc theo tàu/tài khoản vừa seed),
# không phụ thuộc số row sẵn có của ba bảng thật.
# --------------------------------------------------------------------------- #


def test_orders_search_and_range(seeded) -> None:
    """`q` = 4 trường `matchesAnyField` của trang đơn hàng + khoảng `created_at`."""
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag)) == set(seeded.order_ids)

    # `String(order.id)`: chỉ assert tập con vì id có thể là chuỗi con của id khác.
    assert seeded.ord1_id in _ids_at(seeded, ORDERS_URL, q=str(seeded.ord1_id))
    # `order.vessel?.ship_id` (ord1/ord2 cùng tàu A).
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.ship_a)) == {seeded.ord1_id, seeded.ord2_id}
    # `order.vessel?.name`: ghim thêm `vessel_id` để không dính tàu trùng tên.
    assert set(
        _ids_at(seeded, ORDERS_URL, q='filter test a', vessel_id=seeded.vessel_a_id)
    ) == {seeded.ord1_id, seeded.ord2_id}
    # `order.cargo_details`, không phân biệt hoa thường và được trim như client.
    assert _ids_at(seeded, ORDERS_URL, q=f'  cargo-{seeded.tag}-a  ') == [seeded.ord1_id]
    # Wildcard của LIKE không được biến `q` thành "khớp tất cả".
    assert set(_ids_at(seeded, ORDERS_URL, q='%')) & set(seeded.order_ids) == set()
    assert set(_ids_at(seeded, ORDERS_URL, q='_')) & set(seeded.order_ids) == set()

    # `created_from`/`created_to` là instant UTC so với `orders.created_at`.
    mid = FUTURE + timedelta(seconds=150)
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag, created_from=mid.isoformat())) == {
        seeded.ord1_id,
        seeded.ord2_id,
    }
    # Cùng một instant nhưng ghi kèm offset +07:00 → vẫn đúng tập đó.
    assert set(
        _ids_at(
            seeded,
            ORDERS_URL,
            q=seeded.tag,
            created_from=mid.astimezone(timezone(timedelta(hours=7))).isoformat(),
        )
    ) == {seeded.ord1_id, seeded.ord2_id}
    # Instant không kèm offset được hiểu là UTC (giống `parseApiDate` của client).
    assert set(
        _ids_at(seeded, ORDERS_URL, q=seeded.tag, created_from=mid.replace(tzinfo=None).isoformat())
    ) == {seeded.ord1_id, seeded.ord2_id}
    # Biên trên tính cả giá trị bằng nhau (ord2 = FUTURE + 200s).
    assert set(
        _ids_at(seeded, ORDERS_URL, q=seeded.tag, created_to=(FUTURE + timedelta(seconds=200)).isoformat())
    ) == {seeded.ord2_id, seeded.ord3_id, seeded.ord4_id}


def test_orders_filter_vessel_status_and_amount(seeded) -> None:
    # `orderShipIdFilter` của client so đúng `order.vessel_id` (value của dropdown
    # là `vessel.id`, không phải ship_id).
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag, vessel_id=seeded.vessel_a_id)) == {
        seeded.ord1_id,
        seeded.ord2_id,
    }
    # `orderVesselTypeFilter` tra loại tàu qua `vessel_id`.
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag, vessel_type_id=seeded.type_b_id)) == {
        seeded.ord3_id
    }
    # `status` cũ giữ nguyên hành vi (`normalize_order_status`).
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag, status='pending')) == {
        seeded.ord1_id,
        seeded.ord4_id,
    }
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag, status='cancelled')) == {seeded.ord3_id}

    # `Number(order.total_amount ?? 0)`: biên tính cả giá trị bằng nhau.
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag, min_total=100)) == {
        seeded.ord1_id,
        seeded.ord2_id,
        seeded.ord4_id,
    }
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag, max_total=100)) == {
        seeded.ord1_id,
        seeded.ord3_id,
    }
    assert set(_ids_at(seeded, ORDERS_URL, q=seeded.tag, min_total=100.01)) == {
        seeded.ord2_id,
        seeded.ord4_id,
    }
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, min_total=500.01) == []


def test_orders_sort_whitelist_and_order(seeded) -> None:
    """5 khóa sắp xếp của bảng đơn hàng + tiebreaker `id desc` khi khóa bằng nhau."""
    # Mặc định `created_at desc` (đúng thứ tự trang đang thấy).
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag) == [
        seeded.ord1_id,
        seeded.ord2_id,
        seeded.ord3_id,
        seeded.ord4_id,
    ]
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort='created_at', order='asc') == [
        seeded.ord4_id,
        seeded.ord3_id,
        seeded.ord2_id,
        seeded.ord1_id,
    ]
    # `order_code` = `String(order.id)` (localeCompare numeric) → thứ tự số.
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort='order_code', order='asc') == [
        seeded.ord1_id,
        seeded.ord2_id,
        seeded.ord3_id,
        seeded.ord4_id,
    ]
    # `total_amount` so theo số; ord3 = 0, ord4 = 250.
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort='total_amount', order='desc') == [
        seeded.ord2_id,
        seeded.ord4_id,
        seeded.ord1_id,
        seeded.ord3_id,
    ]
    # `status` so theo chuỗi đã chuẩn hoá (cancelled < completed < pending);
    # ord1/ord4 cùng 'pending' → tiebreaker id desc.
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort='status', order='asc') == [
        seeded.ord3_id,
        seeded.ord2_id,
        seeded.ord4_id,
        seeded.ord1_id,
    ]
    # `vessel` = ship_id; đơn không gắn tàu (ord4) luôn xuống cuối ở cả hai chiều.
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort='vessel', order='asc') == [
        seeded.ord2_id,
        seeded.ord1_id,
        seeded.ord3_id,
        seeded.ord4_id,
    ]
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort='vessel', order='desc') == [
        seeded.ord3_id,
        seeded.ord2_id,
        seeded.ord1_id,
        seeded.ord4_id,
    ]
    # `sort`/`order` lạ không được nội suy vào SQL, chỉ rơi về mặc định.
    default = _ids_at(seeded, ORDERS_URL, q=seeded.tag)
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort="id; drop table orders") == default
    assert _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort='total_amount', order='sideways') == (
        _ids_at(seeded, ORDERS_URL, q=seeded.tag, sort='total_amount', order='desc')
    )


def test_port_logs_search_and_range(seeded) -> None:
    """`q` = nhãn tàu (`voted_ship_id`) + `track_id`; khoảng `logged_at` theo instant UTC."""
    assert set(_ids_at(seeded, PORT_LOGS_URL, q=seeded.tag)) == set(seeded.log_ids)

    assert set(_ids_at(seeded, PORT_LOGS_URL, q=seeded.ship_a)) == {seeded.pl1_id, seeded.pl2_id}
    # `track_id` của pl2 viết hoa hậu tố; `q` không phân biệt hoa thường.
    assert _ids_at(seeded, PORT_LOGS_URL, q=f'filtertest-{seeded.tag}-pl2') == [seeded.pl2_id]
    assert set(_ids_at(seeded, PORT_LOGS_URL, q='%')) & set(seeded.log_ids) == set()

    # Ngày 01/03/2032 giờ VN: pl3 = 23:59 giờ VN 29/02, pl4 = 00:00 giờ VN 02/03.
    whole_local_day = _ids_at(
        seeded,
        PORT_LOGS_URL,
        q=seeded.tag,
        logged_from=LOG_LOCAL_DAY_FROM,
        logged_to=LOG_LOCAL_DAY_TO,
    )
    assert set(whole_local_day) == {seeded.pl1_id, seeded.pl2_id}

    # Instant không kèm offset được hiểu là UTC; pl5 thiếu `logged_at` bị loại
    # (client: `isoInLocalDateRange(null)` = false khi có khoảng).
    naive_from = _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, logged_from='2032-03-01T10:00:00')
    assert set(naive_from) == {seeded.pl1_id, seeded.pl4_id}
    assert set(
        _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, logged_to='2032-03-01T09:59:00')
    ) == {seeded.pl2_id, seeded.pl3_id}
    # Cùng instant ghi kèm offset +07:00 = 03:00Z (không phải 10:00Z), nên pl2
    # (09:59Z) cũng lọt — chứng minh offset được quy đổi chứ không đọc trần.
    assert set(
        _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, logged_from='2032-03-01T10:00:00+07:00')
    ) == {seeded.pl1_id, seeded.pl2_id, seeded.pl4_id}


def test_port_logs_filter_vessel_type_and_confidence(seeded) -> None:
    # "Loại tàu" tra tàu theo `ship_id` = nhãn tàu; pl4 không có tàu nên bị loại.
    assert set(_ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, vessel_type_id=seeded.type_a_id)) == {
        seeded.pl1_id,
        seeded.pl2_id,
    }
    assert set(_ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, vessel_type_id=seeded.type_b_id)) == {
        seeded.pl3_id
    }
    # pl3 thiếu `confidence` → client coi là 0.
    assert set(_ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, min_confidence=0.2)) == {
        seeded.pl1_id,
        seeded.pl2_id,
        seeded.pl4_id,
    }
    assert _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, min_confidence=0.95) == [seeded.pl1_id]
    assert _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, min_confidence=0.96) == []
    # Ngưỡng 0 vẫn là một ngưỡng: pl3 (NULL → 0) và pl5 (0,10) đều lọt.
    assert set(_ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, min_confidence=0)) == set(
        seeded.log_ids
    )


def test_port_logs_keeps_existing_ship_id_and_log_date_filters(seeded) -> None:
    """Hai tham số cũ của endpoint vẫn đúng ngữ nghĩa (khớp đúng / theo ngày)."""
    assert set(_ids_at(seeded, PORT_LOGS_URL, ship_id=seeded.ship_a)) == {
        seeded.pl1_id,
        seeded.pl2_id,
    }
    # `log_date` là ngày lịch của cột `logged_at` (naive), khác khoảng instant
    # theo giờ địa phương ở trên: ngày 01/03 gồm cả pl4 (17:00Z).
    assert set(
        _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, log_date=date(2032, 3, 1).isoformat())
    ) == {seeded.pl1_id, seeded.pl2_id, seeded.pl4_id}


def test_port_logs_sort_whitelist_and_order(seeded) -> None:
    """`time` (mặc định) và `voted_ship_id` — hai cột sắp xếp được của bảng."""
    assert _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag) == [
        seeded.pl4_id,
        seeded.pl1_id,
        seeded.pl2_id,
        seeded.pl3_id,
        seeded.pl5_id,
    ]
    # Thiếu `logged_at` luôn xuống cuối ở cả hai chiều (giống `sortRows`).
    assert _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, sort='time', order='asc') == [
        seeded.pl3_id,
        seeded.pl2_id,
        seeded.pl1_id,
        seeded.pl4_id,
        seeded.pl5_id,
    ]
    # pl1/pl2 cùng nhãn tàu → tiebreaker id desc, pl5 thiếu nhãn xuống cuối.
    assert _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, sort='voted_ship_id', order='asc') == [
        seeded.pl2_id,
        seeded.pl1_id,
        seeded.pl3_id,
        seeded.pl4_id,
        seeded.pl5_id,
    ]
    assert _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, sort='voted_ship_id', order='desc') == [
        seeded.pl4_id,
        seeded.pl3_id,
        seeded.pl2_id,
        seeded.pl1_id,
        seeded.pl5_id,
    ]
    default = _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag)
    assert _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, sort='logged_at; --') == default
    assert _ids_at(seeded, PORT_LOGS_URL, q=seeded.tag, sort='time', order='sideways') == default


def test_audit_logs_action_filter_and_range(seeded) -> None:
    """`action` + `table_name` + `q` + khoảng `created_at` của trang lịch sử."""
    # `q` = 4 trường `matchesAnyField`: action, record_id, user.full_name, user.email.
    assert set(_ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag)) == set(seeded.visible_audit_ids)
    assert set(_ids_at(seeded, AUDIT_LOGS_URL, q=f'  {seeded.tag.upper()}  ')) == set(
        seeded.visible_audit_ids
    )
    # `record_id` = `str(entity_id)`, và '—' khi thiếu entity_id.
    assert _ids_at(
        seeded,
        AUDIT_LOGS_URL,
        q=str(seeded.record_marker),
        table_name=f'filtertest-{seeded.tag}-vessels',
    ) == [seeded.al3_id]
    assert _ids_at(
        seeded,
        AUDIT_LOGS_URL,
        q='—',
        table_name=f'filtertest-{seeded.tag}-orders',
    ) == [seeded.al2_id]
    # Nhánh `user.full_name` / `user.email` của `q`.
    assert _ids_at(
        seeded, AUDIT_LOGS_URL, q=seeded.user_email, table_name=f'filtertest-{seeded.tag}-orders'
    ) == [seeded.al1_id]
    assert _ids_at(
        seeded, AUDIT_LOGS_URL, q=seeded.user_label, table_name=f'filtertest-{seeded.tag}-orders'
    ) == [seeded.al1_id]

    # `action` khớp chứa, không phân biệt hoa thường; al4 là READ nên luôn bị ẩn.
    assert set(_ids_at(seeded, AUDIT_LOGS_URL, action=f'filtertest-{seeded.tag}')) == set(
        seeded.visible_audit_ids
    )
    assert _ids_at(seeded, AUDIT_LOGS_URL, action=f'FILTERTEST-{seeded.tag}-DEL') == [seeded.al2_id]
    # `table_name` = `entity_type` đã trim; al4 khớp nhưng bị `_AUDIT_LIST_SKIP_ACTIONS` ẩn.
    assert set(
        _ids_at(seeded, AUDIT_LOGS_URL, table_name=f'FILTERTEST-{seeded.tag}-ORDERS')
    ) == {seeded.al1_id, seeded.al2_id}
    assert _ids_at(seeded, AUDIT_LOGS_URL, table_name=f'filtertest-{seeded.tag}-vessels') == [
        seeded.al3_id
    ]
    assert set(_ids_at(seeded, AUDIT_LOGS_URL, q='%')) & set(seeded.audit_ids) == set()

    # `user_id` cũ vẫn lọc được, và là điều kiện độc lập với bộ lọc mới.
    assert set(
        _ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag, user_id=seeded.audit_user_id)
    ) == {seeded.al1_id, seeded.al3_id}

    # Khoảng `created_at` là instant UTC; al4 (FUTURE + 250s) luôn bị ẩn.
    mid = FUTURE + timedelta(seconds=150)
    assert set(_ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag, created_from=mid.isoformat())) == {
        seeded.al1_id,
        seeded.al2_id,
    }
    assert set(_ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag, created_to=mid.isoformat())) == {
        seeded.al3_id
    }


def test_audit_logs_sort_whitelist_and_order(seeded) -> None:
    """`created_at` (mặc định) / `action` / `table_name`, luôn kèm tiebreaker id desc."""
    assert _ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag) == [
        seeded.al1_id,
        seeded.al2_id,
        seeded.al3_id,
    ]
    assert _ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag, sort='created_at', order='asc') == [
        seeded.al3_id,
        seeded.al2_id,
        seeded.al1_id,
    ]
    # CREATE < DELETE < UPDATE
    assert _ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag, sort='action', order='asc') == [
        seeded.al1_id,
        seeded.al2_id,
        seeded.al3_id,
    ]
    assert _ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag, sort='action', order='desc') == [
        seeded.al3_id,
        seeded.al2_id,
        seeded.al1_id,
    ]
    # al1/al2 cùng `filtertest-<tag>-orders` → tiebreaker id desc.
    assert _ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag, sort='table_name', order='asc') == [
        seeded.al2_id,
        seeded.al1_id,
        seeded.al3_id,
    ]
    default = _ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag)
    assert _ids_at(seeded, AUDIT_LOGS_URL, q=seeded.tag, sort='table_name; --') == default


def test_each_endpoint_total_reflects_filters(seeded) -> None:
    """`X-Total-Count` của cả ba endpoint đếm đúng tập đã lọc, không phải cả bảng."""
    mid = FUTURE + timedelta(seconds=150)
    cases = [
        (ORDERS_URL, {'q': seeded.tag}, 4),
        (ORDERS_URL, {'q': seeded.tag, 'min_total': 100}, 3),
        (PORT_LOGS_URL, {'q': seeded.tag}, 5),
        (PORT_LOGS_URL, {'q': seeded.tag, 'min_confidence': 0.2}, 3),
        (AUDIT_LOGS_URL, {'q': seeded.tag}, 3),
        (AUDIT_LOGS_URL, {'q': seeded.tag, 'created_from': mid.isoformat()}, 2),
    ]

    for url, params, expected_total in cases:
        response = _get_at(seeded, url, **params)
        assert _total(response) == expected_total, (url, params)
        assert len(_ids(response)) == expected_total, (url, params)

        window = _get_at(seeded, url, skip=1, limit=1, **params)
        assert _total(window) == expected_total, (url, params)
        assert len(_ids(window)) == min(1, expected_total), (url, params)


def test_list_sort_paging_keeps_every_row_with_equal_keys(seeded) -> None:
    """Khóa sắp xếp bằng nhau vẫn đi hết trang không lặp, không mất row.

    pl1/pl2 cùng `voted_ship_id` và ord1/ord4 cùng `status` — đúng những chỗ
    tiebreaker `id desc` quyết định thứ tự.
    """
    pl_filter = {'q': seeded.tag, 'sort': 'voted_ship_id', 'order': 'asc'}
    expected_logs = _ids_at(seeded, PORT_LOGS_URL, **pl_filter)
    page_one = _ids_at(seeded, PORT_LOGS_URL, skip=0, limit=3, **pl_filter)
    page_two = _ids_at(seeded, PORT_LOGS_URL, skip=3, limit=3, **pl_filter)

    assert page_one + page_two == expected_logs
    assert len(set(page_one + page_two)) == len(expected_logs) == 5

    seen: list[int] = []
    skip = 0
    while True:
        batch = _ids_at(
            seeded, ORDERS_URL, q=seeded.tag, sort='status', order='asc', skip=skip, limit=1
        )
        seen.extend(batch)
        if not batch:
            break
        skip += 1

    assert seen == [
        seeded.ord3_id,
        seeded.ord2_id,
        seeded.ord4_id,
        seeded.ord1_id,
    ]
    assert len(set(seen)) == 4

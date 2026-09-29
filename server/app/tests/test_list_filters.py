"""Bộ lọc + sắp xếp danh sách nhận diện: 7 bộ lọc của trang bến chạy ở SQL.

Test đi qua đúng tầng FastAPI trên PostgreSQL thật, nhưng mọi row seed nằm trong
một transaction **chưa commit** và bị rollback ở teardown — không để lại rác.
Assert khoanh vùng theo `vessel_id` (hoặc theo `q` mang tag ngẫu nhiên) của dữ
liệu vừa seed nên không phụ thuộc số row sẵn có của môi trường.

Mốc thời gian seed là **naive UTC** — đúng như cột `start_time`/`created_at`
(`timestamp without time zone`) đang lưu trong DB; client đọc chuỗi API không
kèm offset và hiểu là UTC (xem `parseApiDate` của client).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.detection import Detection
from app.models.vessel import Vessel
from app.models.vessel_type import VesselType
from app.utils.pagination import MAX_PAGE_SIZE

LIST_URL = '/api/v1/detections/'

# Ngày 2026-09-30 theo giờ VN (+07) trải từ 2026-09-29T17:00Z tới 2026-09-30T16:59:59.999Z.
LOCAL_DAY_FROM = '2026-09-30T00:00:00+07:00'
LOCAL_DAY_TO = '2026-09-30T23:59:59.999000+07:00'
# 2026-09-30 17:00 giờ VN = 10:00Z — dùng để chứng minh offset được quy đổi.
LOCAL_5PM = '2026-09-30T17:00:00+07:00'


def _utc(*args: int) -> datetime:
    """Mốc UTC dạng naive, khớp kiểu cột `timestamp without time zone`."""
    return datetime(*args)


def _seed(session) -> SimpleNamespace:
    """Seed 2 vessel (2 loại tàu) + 7 detection; trả id/khóa để assert."""
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
    # created_at = start_time để thứ tự mặc định (`time`) xác định được.
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
        **{f'{k}_id': rows[k].id for k in rows},
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
    # `time desc` mặc định: a3 (17:00Z) → a5 (12:00Z) → a1 (10:00Z) → a2 (09:59Z) → a4.
    assert default == [
        seeded.a3_id,
        seeded.a5_id,
        seeded.a1_id,
        seeded.a2_id,
        seeded.a4_id,
    ]
    assert _ids(unknown_order) == _ids(
        _get(seeded, vessel_id=seeded.vessel_a_id, sort='confidence', order='desc')
    )


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

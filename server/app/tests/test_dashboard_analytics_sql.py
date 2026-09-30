"""`/dashboard/detection-analytics` — bốn widget phân tích đếm bằng aggregate ở SQL.

Task 17: bốn widget của dashboard (`buildDetectionsByHourLast24h`,
`buildTopShipCounts`, `buildAcceptanceSplit`, `buildConfidenceBuckets` phía client)
trước đây tự đếm trên 120 row mới nhất mà sidebar tải về. Endpoint mới trả số tổng
hợp để sidebar cắt còn 18 row mà biểu đồ không đổi hình dạng, và biểu đồ "24 giờ
qua" thôi mô tả "120 row gần nhất".

Test chạy qua đúng tầng FastAPI trên PostgreSQL thật, dùng **chung một session chưa
commit** với test (`dependency_overrides[get_db]`) và rollback ở teardown — không để
lại rác. Bảng thật đã có dữ liệu nên:

- Ca "số chính xác" seed row với nhãn riêng (có uuid) rồi so **delta** trước/sau, nên
  không đụng dữ liệu sẵn có.
- Ca "tương đương" so trực tiếp với bản port nguyên văn bốn hàm `build*` của client
  đọc qua chính repository (`detection_repo.get_all`) — cách này miễn nhiễm với dữ
  liệu sẵn có vì hai bên cùng nhìn một cửa sổ.
- Ca "hình dạng SQL" bắt truy vấn bằng event listener như `test_dashboard_stats_sql.py`.

Ngữ nghĩa cửa sổ: `by_hour` LUÔN là 24 khung giờ gần nhất (không phụ thuộc `period`);
`top_ships`/`acceptance`/`confidence_buckets` theo `period` với cùng quy ước như
`/dashboard/summary` (biên kỳ theo Asia/Ho_Chi_Minh, nửa khoảng `[start, end)` trên
`created_at`).

Task 18 thêm nhánh `year` (năm dương lịch VN) để client truyền thẳng `DashboardPeriod`
(`day` | `month` | `year`) mà tab "Năm" không 422; `week` vẫn giữ nguyên.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, insert

from app.api.deps import get_current_user
from app.db.session import SessionLocal, engine, get_db
from app.main import app
from app.models.detection import Detection
from app.models.vessel import Vessel
from app.repositories.detection_repository import (
    CONFIDENCE_BUCKET_LABELS,
    UNKNOWN_SHIP_LABEL,
    detection_repo,
)

ANALYTICS_URL = '/api/v1/dashboard/detection-analytics'
TZ = ZoneInfo('Asia/Ho_Chi_Minh')

HOURS = 24
TOP_SHIPS_LIMIT = 8

# Số row tối đa một truy vấn được phép trả về: trục giờ 24 điểm là query "to" nhất,
# còn lại 8/3/3. Vượt ngưỡng này nghĩa là đang nạp row về Python để đếm.
MAX_ROWS_PER_QUERY = HOURS

# Nhãn bucket độ tin cậy — chép nguyên văn `buildConfidenceBuckets` của client
# (client/src/features/dashboard/utils/dashboard-analytics-data.ts), viết bằng
# escape để không phụ thuộc encoding của file: '50–75%' dùng en-dash U+2013,
# '≥ 75%' dùng U+2265.
CLIENT_CONFIDENCE_LABELS = ('< 50%', '50\u201375%', '\u2265 75%')


# --- Tiện ích thời gian ----------------------------------------------------


def _naive_utc(moment: datetime) -> datetime:
    """Mốc naive đúng kiểu cột `created_at`/`start_time` (`timestamp without time zone`, chứa giờ UTC)."""
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _trunc_hour(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _hour_key(moment: datetime) -> str:
    """Khóa bucket đúng như chuỗi ISO-8601 UTC endpoint trả về."""
    return _trunc_hour(moment).isoformat().replace('+00:00', 'Z')


def _parse_hour(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _expected_window_utc(period: str) -> tuple[datetime, datetime]:
    """Bản port độc lập của quy ước kỳ trong `/dashboard/summary` (giờ VN → UTC).

    Viết lại trong test (không import service) để bắt được lỗi ở chính hàm biên kỳ.
    """
    now = datetime.now(TZ)
    if period == 'week':
        start_local = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_local = start_local + timedelta(days=7)
    elif period == 'month':
        start_local = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start_local.month == 12:
            end_local = start_local.replace(year=start_local.year + 1, month=1)
        else:
            end_local = start_local.replace(month=start_local.month + 1)
    elif period == 'year':
        start_local = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local.replace(year=start_local.year + 1)
    else:
        start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


# --- Bản port bốn hàm `build*` của client (mốc so sánh) --------------------


def _legacy_ship_label(det: Detection) -> str:
    """Port `getDetectionShipLabel`: vessels.ship_id → id OCR đầu tiên → nhãn mặc định."""
    vessel = det.vessel
    from_vessel = (vessel.ship_id or '').strip() if vessel is not None else ''
    if from_vessel:
        return from_vessel
    items = det.ocr_results
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            ocr_id = first.get('id')
            if isinstance(ocr_id, str) and ocr_id.strip():
                return ocr_id.strip()
    return UNKNOWN_SHIP_LABEL


def _window_rows(db, start_utc: datetime, end_utc: datetime) -> list[Detection]:
    """Row trong kỳ, đọc kiểu cũ (nạp rồi lọc ở Python) — chỉ dùng làm mốc so sánh."""
    start_naive = _naive_utc(start_utc)
    end_naive = _naive_utc(end_utc)
    return [
        det
        for det in detection_repo.get_all(db, limit=100000)
        if det.created_at is not None and start_naive <= det.created_at < end_naive
    ]


def _legacy_top_ships(rows: list[Detection], limit: int = TOP_SHIPS_LIMIT) -> list[dict]:
    """Port `buildTopShipCounts` (sắp count giảm dần, tiebreaker nhãn tăng dần)."""
    counts: dict[str, int] = {}
    for det in rows:
        label = _legacy_ship_label(det)
        counts[label] = counts.get(label, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [{'label': label, 'count': count} for label, count in ordered]


def _legacy_acceptance(rows: list[Detection]) -> dict[str, int]:
    """Port `buildAcceptanceSplit`: TRUE / FALSE / NULL."""
    out = {'accepted': 0, 'rejected': 0, 'pending': 0}
    for det in rows:
        if det.is_accepted is True:
            out['accepted'] += 1
        elif det.is_accepted is False:
            out['rejected'] += 1
        else:
            out['pending'] += 1
    return out


def _legacy_confidence_buckets(rows: list[Detection]) -> list[dict]:
    """Port `buildConfidenceBuckets`: bỏ `confidence` NULL, biên 0.5 / 0.75."""
    counts = {label: 0 for label in CLIENT_CONFIDENCE_LABELS}
    for det in rows:
        value = det.confidence
        if value is None:
            continue
        number = float(value)
        if number != number:  # NaN — client cũng bỏ qua
            continue
        if number < 0.5:
            counts[CLIENT_CONFIDENCE_LABELS[0]] += 1
        elif number < 0.75:
            counts[CLIENT_CONFIDENCE_LABELS[1]] += 1
        else:
            counts[CLIENT_CONFIDENCE_LABELS[2]] += 1
    return [{'bucket': label, 'count': counts[label]} for label in CLIENT_CONFIDENCE_LABELS]


def _legacy_by_hour(db, anchor: datetime, hours: int = HOURS) -> list[dict]:
    """Port `buildDetectionsByHourLast24h` với trục 24 khung giờ UTC kết thúc ở `anchor`."""
    anchor = _trunc_hour(anchor)
    axis = [anchor - timedelta(hours=hours - 1 - index) for index in range(hours)]
    counts = {moment: 0 for moment in axis}
    for det in detection_repo.get_all(db, limit=100000):
        raw = det.start_time if det.start_time is not None else det.created_at
        if raw is None:
            continue
        bucket = raw.replace(tzinfo=timezone.utc).replace(minute=0, second=0, microsecond=0)
        if bucket in counts:
            counts[bucket] += 1
    return [{'hour': moment, 'count': counts[moment]} for moment in axis]


def _legacy_analytics(db, period: str, *, anchor: datetime) -> dict:
    start_utc, end_utc = _expected_window_utc(period)
    rows = _window_rows(db, start_utc, end_utc)
    return {
        'by_hour': _legacy_by_hour(db, anchor),
        'top_ships': _legacy_top_ships(rows),
        'acceptance': _legacy_acceptance(rows),
        'confidence_buckets': _legacy_confidence_buckets(rows),
    }


# --- Seed ------------------------------------------------------------------


def _add_vessel(session, ship_id: str) -> Vessel:
    vessel = Vessel(ship_id=ship_id, name='Analytics Test', classification='unclassified')
    session.add(vessel)
    session.flush()
    return vessel


def _add_detection(
    session,
    tag: str,
    *,
    when: datetime,
    confidence: float | None = 0.9,
    is_accepted: bool | None = None,
    vessel: Vessel | None = None,
    ocr_id: str | None = None,
    deleted: bool = False,
) -> Detection:
    """Thêm 1 detection có `created_at`/`start_time` = `when` (instant aware).

    Row đã xoá mềm đặt `deleted_at = now` để chắc chắn nằm trong mọi cửa sổ nếu
    không lọc soft-delete.
    """
    det = Detection(
        vessel_id=vessel.id if vessel is not None else None,
        track_id=f'analytics-{tag}-{uuid4().hex[:10]}',
        start_time=_naive_utc(when),
        created_at=_naive_utc(when),
        confidence=confidence,
        is_accepted=is_accepted,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
        ocr_results=[{'id': ocr_id}] if ocr_id is not None else None,
    )
    session.add(det)
    session.flush()
    return det


# --- Client/harness --------------------------------------------------------


@contextmanager
def _analytics_client():
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
    with _analytics_client() as context:
        yield context


def _get_analytics(client, period: str = 'day') -> dict:
    response = client.get(f'{ANALYTICS_URL}?period={period}')
    assert response.status_code == 200, response.text[:300]
    return response.json()


def _counts(rows: list[dict], key: str) -> dict[str, int]:
    return {row[key]: row['count'] for row in rows}


def _hour_series(rows: list[dict]) -> list[tuple[datetime, int]]:
    """`[{hour, count}]` → `[(instant, count)]`: response trả chuỗi ISO, bản port trả datetime."""
    return [
        (_parse_hour(row['hour']) if isinstance(row['hour'], str) else row['hour'], row['count'])
        for row in rows
    ]


# --- Hình dạng trục giờ ----------------------------------------------------


def test_by_hour_is_24_ascending_utc_buckets_ending_at_the_current_hour(ctx) -> None:
    """`by_hour` cố định 24 khung giờ, tăng dần, khung cuối là giờ hiện tại (UTC)."""
    before = datetime.now(timezone.utc)
    body = _get_analytics(ctx.client)
    after = datetime.now(timezone.utc)

    points = body['by_hour']
    assert len(points) == HOURS, points
    assert all(set(point) == {'hour', 'count'} for point in points)
    # ISO-8601 UTC: pydantic serialize instant UTC bằng hậu tố 'Z'.
    assert all(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:00:00Z', point['hour']) for point in points)

    hours = [_parse_hour(point['hour']) for point in points]
    assert all(hour.utcoffset() == timedelta(0) for hour in hours)
    assert hours == sorted(hours)
    assert all(later - earlier == timedelta(hours=1) for earlier, later in zip(hours, hours[1:]))
    assert hours[0] == hours[-1] - timedelta(hours=HOURS - 1)
    assert hours[-1] in {_trunc_hour(before), _trunc_hour(after)}
    assert all(point['count'] >= 0 for point in points)


def test_by_hour_counts_rows_in_their_utc_bucket_and_skips_deleted(ctx) -> None:
    """Đếm theo bucket giờ UTC; row xoá mềm bị loại, row `created_at` NULL vẫn đếm theo `start_time`."""
    session = ctx.session
    tag = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    before = _counts(_get_analytics(ctx.client)['by_hour'], 'hour')

    _add_detection(session, tag, when=now - timedelta(hours=2), confidence=0.9)
    _add_detection(session, tag, when=now - timedelta(hours=2), confidence=0.9)
    _add_detection(session, tag, when=now - timedelta(hours=5), confidence=0.9)
    _add_detection(session, tag, when=now - timedelta(hours=3), confidence=0.9, deleted=True)
    # `created_at IS NULL` phải insert bằng Core: gán None qua ORM sẽ bị server_default ghi đè.
    null_created_id = session.execute(
        insert(Detection)
        .values(
            track_id=f'analytics-{tag}-nullcreated',
            start_time=_naive_utc(now - timedelta(hours=4)),
            created_at=None,
            confidence=0.9,
        )
        .returning(Detection.id)
    ).scalar()
    session.flush()

    after = _counts(_get_analytics(ctx.client)['by_hour'], 'hour')

    assert null_created_id is not None
    # Bảo hiểm cho phép seed: row "null created_at" thật sự NULL trong DB.
    assert session.get(Detection, null_created_id).created_at is None

    assert after[_hour_key(now - timedelta(hours=2))] - before.get(_hour_key(now - timedelta(hours=2)), 0) == 2
    # Client cũ dùng `start_time ?? created_at` nên row này vẫn thuộc bucket 4 giờ trước.
    assert after[_hour_key(now - timedelta(hours=4))] - before.get(_hour_key(now - timedelta(hours=4)), 0) == 1
    assert after[_hour_key(now - timedelta(hours=5))] - before.get(_hour_key(now - timedelta(hours=5)), 0) == 1
    # Row đã xoá mềm: không xuất hiện ở bucket của nó.
    assert after[_hour_key(now - timedelta(hours=3))] - before.get(_hour_key(now - timedelta(hours=3)), 0) == 0


# --- Tương đương với bốn hàm `build*` của client ---------------------------


def _seed_equivalence_rows(session, *, now: datetime, tag: str) -> int:
    """Seed một cửa sổ "đủ nhiễu" cho ca so tương đương; trả số nhãn tàu trong kỳ."""
    vessel_a = _add_vessel(session, f'analytics-{tag}-A')
    vessel_b = _add_vessel(session, f'analytics-{tag}-B')
    # ship_id toàn khoảng trắng: phải rơi về id OCR (JS trim), không thành nhãn trắng.
    vessel_blank = _add_vessel(session, f'   analytics-{tag}-D   ')

    plan = [
        (3, dict(vessel=vessel_a, confidence=0.9, is_accepted=True)),
        (2, dict(vessel=vessel_b, confidence=0.6, is_accepted=False)),
        (2, dict(ocr_id=f'analytics-{tag}-C', confidence=0.4, is_accepted=None)),
        (2, dict(vessel=vessel_blank, ocr_id=f'  analytics-{tag}-D  ', confidence=0.5, is_accepted=True)),
        (1, dict(confidence=None, is_accepted=True)),  # không nhãn -> KHÔNG XÁC ĐỊNH
        (1, dict(ocr_id=f'analytics-{tag}-E', confidence=0.75, is_accepted=False)),
        (1, dict(ocr_id=f'analytics-{tag}-F', confidence=0.49999, is_accepted=True)),
        (1, dict(ocr_id=f'analytics-{tag}-G', confidence=0.9, is_accepted=True)),
        (1, dict(ocr_id=f'analytics-{tag}-H', confidence=0.9, is_accepted=True)),
        (1, dict(ocr_id=f'analytics-{tag}-I', confidence=0.9, is_accepted=True)),
        # confidence = NaN: client bỏ qua (`Number.isNaN`) — PostgreSQL lại coi NaN lớn
        # hơn mọi số nên nếu không lọc, row này rơi nhầm vào bucket "≥ 75%".
        (1, dict(ocr_id=f'analytics-{tag}-NAN', confidence=float('nan'), is_accepted=True)),
    ]
    for index, (times, kwargs) in enumerate(plan):
        for _ in range(times):
            _add_detection(
                session,
                tag,
                when=now - timedelta(minutes=5 + index),
                **kwargs,
            )

    # Ngoài kỳ / đã xoá mềm: không được lọt vào bất kỳ tổng hợp nào của kỳ.
    _add_detection(
        session, tag, when=now - timedelta(days=40), confidence=0.2,
        is_accepted=False, ocr_id=f'analytics-{tag}-OLD',
    )
    _add_detection(
        session, tag, when=now - timedelta(minutes=8), confidence=0.9,
        is_accepted=True, vessel=vessel_a, deleted=True,
    )
    # `created_at` NULL nhưng có `start_time`: chỉ `by_hour` đếm (period lọc theo created_at).
    session.execute(
        insert(Detection).values(
            track_id=f'analytics-{tag}-nullcreated',
            start_time=_naive_utc(now - timedelta(minutes=30)),
            created_at=None,
            confidence=0.95,
            is_accepted=True,
            ocr_results=[{'id': f'analytics-{tag}-NULLCREATED'}],
        )
    )
    session.flush()

    # 10 nhãn trong kỳ (A, B, C, D, KHÔNG XÁC ĐỊNH, E, F, G, H, I) > TOP_SHIPS_LIMIT.
    return 10


def test_aggregates_match_client_builders_over_the_period_window(ctx) -> None:
    """Số của endpoint phải trùng bản port bốn hàm `build*` cho cả ba kỳ."""
    session = ctx.session
    tag = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    in_window_labels = _seed_equivalence_rows(session, now=now, tag=tag)
    assert in_window_labels > TOP_SHIPS_LIMIT

    for period in ('day', 'week', 'month', 'year'):
        body = _get_analytics(ctx.client, period)
        # Trục giờ lấy từ chính response để ca này không phụ thuộc việc test có chạy
        # vắt qua mốc giờ hay không (trục được kiểm riêng ở test phía trên).
        expected = _legacy_analytics(
            session, period, anchor=_parse_hour(body['by_hour'][-1]['hour'])
        )

        assert body['top_ships'] == expected['top_ships'], period
        # Cửa sổ có 10 nhãn nên cap 8 phải thật sự cắt bớt.
        assert len(body['top_ships']) == TOP_SHIPS_LIMIT, period
        assert body['acceptance'] == expected['acceptance'], period
        assert body['confidence_buckets'] == expected['confidence_buckets'], period
        # `hour` của response là chuỗi ISO, bản port trả datetime — so theo instant.
        assert _hour_series(body['by_hour']) == _hour_series(expected['by_hour']), period


def test_day_window_is_the_local_calendar_day(ctx) -> None:
    """Biên kỳ `day` là nửa đêm giờ VN: 00:30 VN hôm nay được tính, 23:30 VN hôm qua thì không."""
    session = ctx.session
    tag = uuid4().hex[:8]
    local_midnight = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)

    before = _get_analytics(ctx.client)
    _add_detection(
        session, tag, when=local_midnight - timedelta(minutes=30), confidence=0.9,
        is_accepted=True, ocr_id=f'analytics-{tag}-BEFORE',
    )
    _add_detection(
        session, tag, when=local_midnight + timedelta(minutes=30), confidence=0.9,
        is_accepted=True, ocr_id=f'analytics-{tag}-AFTER',
    )
    after = _get_analytics(ctx.client)

    before_ships = _counts(before['top_ships'], 'label')
    after_ships = _counts(after['top_ships'], 'label')
    assert after_ships.get(f'analytics-{tag}-AFTER', 0) - before_ships.get(f'analytics-{tag}-AFTER', 0) == 1
    assert after_ships.get(f'analytics-{tag}-BEFORE', 0) - before_ships.get(f'analytics-{tag}-BEFORE', 0) == 0
    assert after['acceptance']['accepted'] - before['acceptance']['accepted'] == 1


# --- Số chính xác trên row tự seed ----------------------------------------


def test_seeded_counts_are_exact_for_every_aggregate(ctx) -> None:
    """Seed 24 row biết trước → delta từng nhãn / từng bucket / từng trạng thái phải khớp."""
    session = ctx.session
    tag = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    before = _get_analytics(ctx.client)

    vessel_a = _add_vessel(session, f'analytics-{tag}-A')
    vessel_b = _add_vessel(session, f'analytics-{tag}-B')

    # 12 row A: accepted, conf 0.9 (bucket ≥75%), giờ hiện tại (now - 30 phút).
    for _ in range(12):
        _add_detection(
            session, tag, when=now - timedelta(minutes=30), confidence=0.9,
            is_accepted=True, vessel=vessel_a,
        )
    # 7 row B: rejected, conf 0.6 (bucket 50–75%), cách đây 2 giờ.
    for _ in range(7):
        _add_detection(
            session, tag, when=now - timedelta(hours=2), confidence=0.6,
            is_accepted=False, vessel=vessel_b,
        )
    # 3 row C: pending (NULL), conf 0.4 (bucket <50%), cách đây 5 giờ.
    for _ in range(3):
        _add_detection(
            session, tag, when=now - timedelta(hours=5), confidence=0.4,
            is_accepted=None, ocr_id=f'analytics-{tag}-C',
        )
    # 1 row không nhãn, không confidence: đếm vào donut (accepted) nhưng không vào bucket nào.
    _add_detection(
        session, tag, when=now - timedelta(minutes=30), confidence=None,
        is_accepted=True,
    )
    # confidence = NaN: client bỏ qua (`Number.isNaN`); PostgreSQL coi NaN lớn hơn mọi
    # số nên nếu không lọc, row này sẽ rơi nhầm vào bucket "≥ 75%".
    _add_detection(
        session, tag, when=now - timedelta(minutes=30), confidence=float('nan'),
        is_accepted=True, ocr_id=f'analytics-{tag}-NAN',
    )
    # 2 row đã xoá mềm ngay trong bucket giờ hiện tại + 1 row 40 ngày trước: phải bị loại.
    _add_detection(
        session, tag, when=now - timedelta(minutes=30), confidence=0.9,
        is_accepted=True, vessel=vessel_a, deleted=True,
    )
    _add_detection(
        session, tag, when=now - timedelta(minutes=30), confidence=0.1,
        is_accepted=False, ocr_id=f'analytics-{tag}-C', deleted=True,
    )
    _add_detection(
        session, tag, when=now - timedelta(days=40), confidence=0.2,
        is_accepted=False, ocr_id=f'analytics-{tag}-OLD',
    )
    # `created_at` NULL: `by_hour` đếm theo `start_time`, ba tổng hợp theo kỳ thì không.
    session.execute(
        insert(Detection).values(
            track_id=f'analytics-{tag}-nullcreated',
            start_time=_naive_utc(now - timedelta(minutes=30)),
            created_at=None,
            confidence=0.9,
            is_accepted=True,
            ocr_results=[{'id': f'analytics-{tag}-D'}],
        )
    )
    session.flush()

    after = _get_analytics(ctx.client)

    before_ships = _counts(before['top_ships'], 'label')
    after_ships = _counts(after['top_ships'], 'label')
    assert {
        label: after_ships.get(label, 0) - before_ships.get(label, 0)
        for label in (
            f'analytics-{tag}-A',
            f'analytics-{tag}-B',
            f'analytics-{tag}-C',
            f'analytics-{tag}-NAN',
            UNKNOWN_SHIP_LABEL,
            f'analytics-{tag}-D',
            f'analytics-{tag}-OLD',
        )
    } == {
        f'analytics-{tag}-A': 12,
        f'analytics-{tag}-B': 7,
        f'analytics-{tag}-C': 3,
        f'analytics-{tag}-NAN': 1,
        UNKNOWN_SHIP_LABEL: 1,
        # Row `created_at` NULL và row 40 ngày trước không thuộc kỳ `day`.
        f'analytics-{tag}-D': 0,
        f'analytics-{tag}-OLD': 0,
    }

    assert {
        key: after['acceptance'][key] - before['acceptance'][key]
        for key in ('accepted', 'rejected', 'pending')
    } == {'accepted': 14, 'rejected': 7, 'pending': 3}

    before_buckets = _counts(before['confidence_buckets'], 'bucket')
    after_buckets = _counts(after['confidence_buckets'], 'bucket')
    assert {
        label: after_buckets[label] - before_buckets[label]
        for label in CLIENT_CONFIDENCE_LABELS
    } == {
        # NaN và NULL đều không vào bucket nào (giống client).
        CLIENT_CONFIDENCE_LABELS[0]: 3,   # conf 0.4
        CLIENT_CONFIDENCE_LABELS[1]: 7,   # conf 0.6
        CLIENT_CONFIDENCE_LABELS[2]: 12,  # conf 0.9
    }

    before_hours = _counts(before['by_hour'], 'hour')
    after_hours = _counts(after['by_hour'], 'hour')
    assert {
        _hour_key(now - timedelta(minutes=30)): 15,  # 12 A + không nhãn + NaN + created_at NULL
        _hour_key(now - timedelta(hours=2)): 7,
        _hour_key(now - timedelta(hours=5)): 3,
    } == {
        key: after_hours[key] - before_hours.get(key, 0)
        for key in (
            _hour_key(now - timedelta(minutes=30)),
            _hour_key(now - timedelta(hours=2)),
            _hour_key(now - timedelta(hours=5)),
        )
    }
    # Tổng delta trên cả trục = số row thật sự được đếm (row xoá mềm + row 40 ngày trước bị loại).
    assert sum(after_hours[key] - before_hours.get(key, 0) for key in after_hours) == 25


def test_year_period_has_the_same_shape_as_the_other_periods(ctx) -> None:
    """`year` (nhánh Task 18 cho tab "Năm") trả CÙNG hình dạng như `day`/`week`/`month`.

    Không chỉ "200 OK": cùng bộ khóa, cùng 24 khung giờ ISO-UTC tăng dần cách nhau 1
    giờ, cùng thứ tự ba nhãn bucket, cùng ba khóa `acceptance`. Client ánh xạ thẳng ba
    nhãn tiếng Việt và đọc `by_hour` theo vị trí nên số phần tử + thứ tự là hợp đồng.
    """
    shapes = {
        period: _get_analytics(ctx.client, period)
        for period in ('day', 'week', 'month', 'year')
    }
    reference = shapes['day']
    for period, body in shapes.items():
        assert set(body) == set(reference) == {
            'by_hour',
            'top_ships',
            'acceptance',
            'confidence_buckets',
        }, period
        assert len(body['by_hour']) == len(reference['by_hour']) == HOURS, period
        assert all(set(point) == {'hour', 'count'} for point in body['by_hour']), period
        hours = [_parse_hour(point['hour']) for point in body['by_hour']]
        assert hours == sorted(hours), period
        assert all(
            later - earlier == timedelta(hours=1) for earlier, later in zip(hours, hours[1:])
        ), period
        assert [row['bucket'] for row in body['confidence_buckets']] == [
            row['bucket'] for row in reference['confidence_buckets']
        ] == list(CLIENT_CONFIDENCE_LABELS), period
        assert set(body['acceptance']) == {'accepted', 'rejected', 'pending'}, period
        assert all(isinstance(value, int) for value in body['acceptance'].values()), period
        assert len(body['top_ships']) <= TOP_SHIPS_LIMIT, period
        assert all(set(row) == {'label', 'count'} for row in body['top_ships']), period

    # Trước Task 18 enum chỉ có day|week|month nên chính request này trả 422.
    assert ctx.client.get(f'{ANALYTICS_URL}?period=year').status_code == 200


def test_year_window_is_the_local_calendar_year(ctx) -> None:
    """`year` = năm dương lịch VN: row trong năm được đếm, row trước giao thừa 1 giờ thì không.

    Row "năm trước" vẫn nằm trong 365 ngày gần nhất, nên nếu ai đó cài `year` thành
    cửa sổ cuộn 365 ngày (thay vì 01/01 → 01/01 năm sau như `/dashboard/summary`) thì
    `rejected` sẽ tăng và test này đỏ.
    """
    session = ctx.session
    tag = uuid4().hex[:8]
    year_start = datetime.now(TZ).replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    )

    before = _get_analytics(ctx.client, 'year')
    _add_detection(
        session, tag, when=year_start + timedelta(hours=1), confidence=0.9, is_accepted=True
    )
    _add_detection(
        session, tag, when=year_start - timedelta(hours=1), confidence=0.9, is_accepted=False
    )
    after = _get_analytics(ctx.client, 'year')

    assert after['acceptance']['accepted'] - before['acceptance']['accepted'] == 1
    assert after['acceptance']['rejected'] - before['acceptance']['rejected'] == 0

    # Biên năm của bản port độc lập trong test: 01/01 00:00 VN → 01/01 năm sau 00:00 VN.
    start_utc, end_utc = _expected_window_utc('year')
    assert start_utc == year_start.astimezone(timezone.utc)
    assert end_utc == year_start.replace(year=year_start.year + 1).astimezone(timezone.utc)


# --- Hình dạng SQL --------------------------------------------------------


def test_analytics_is_four_group_by_queries_and_top_ships_is_capped(ctx) -> None:
    """Mỗi tổng hợp đúng MỘT truy vấn GROUP BY, không truy vấn nào nạp bảng về Python."""
    session = ctx.session
    tag = uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    vessel = _add_vessel(session, f'analytics-{tag}-A')
    for index in range(3):
        _add_detection(
            session, tag, when=now - timedelta(minutes=10 + index), confidence=0.9,
            is_accepted=True, vessel=vessel,
        )

    captured: list[tuple[int, str, dict]] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        captured.append((cursor.rowcount, ' '.join(statement.split()), parameters))

    event.listen(engine, 'after_cursor_execute', _capture)
    try:
        response = ctx.client.get(f'{ANALYTICS_URL}?period=day')
    finally:
        event.remove(engine, 'after_cursor_execute', _capture)

    assert response.status_code == 200, response.text[:300]
    assert len(captured) == 4, [(rowcount, stmt[:160]) for rowcount, stmt, _ in captured]

    for rowcount, statement, _ in captured:
        assert 'group by' in statement.lower(), statement[:300]
        assert rowcount <= MAX_ROWS_PER_QUERY, (rowcount, statement[:200])

    hour_queries = [(rc, stmt) for rc, stmt, _ in captured if 'generate_series' in stmt]
    assert len(hour_queries) == 1
    # Trục 24 giờ sinh ngay trong SQL: query trả đúng 24 dòng.
    assert hour_queries[0][0] == HOURS, hour_queries[0][1][:300]

    ship_queries = [
        (rc, stmt, params)
        for rc, stmt, params in captured
        if 'jsonb_extract_path_text' in stmt
    ]
    assert len(ship_queries) == 1
    ship_rowcount, ship_statement, ship_params = ship_queries[0]
    assert ship_rowcount <= TOP_SHIPS_LIMIT, ship_statement[:300]
    assert ' limit ' in ship_statement.lower()
    assert TOP_SHIPS_LIMIT in list(ship_params.values())


# --- Nhãn + hợp đồng tham số ----------------------------------------------


def test_confidence_labels_and_unknown_ship_label_match_the_client() -> None:
    """Nhãn bucket và nhãn "không xác định" phải trùng từng ký tự với client."""
    assert CONFIDENCE_BUCKET_LABELS == CLIENT_CONFIDENCE_LABELS
    assert CONFIDENCE_BUCKET_LABELS == ('< 50%', '50\u201375%', '\u2265 75%')
    assert UNKNOWN_SHIP_LABEL == 'KH\u00d4NG X\u00c1C \u0110\u1ecaNH'


def test_response_shape_is_complete_for_every_period(ctx) -> None:
    """Ba giá trị `period` đều trả đủ bốn khóa; donut/bucket luôn đủ nhóm."""
    for period in ('day', 'week', 'month', 'year'):
        body = _get_analytics(ctx.client, period)
        assert set(body) == {'by_hour', 'top_ships', 'acceptance', 'confidence_buckets'}
        assert len(body['by_hour']) == HOURS
        assert len(body['top_ships']) <= TOP_SHIPS_LIMIT
        assert all(set(row) == {'label', 'count'} for row in body['top_ships'])
        assert set(body['acceptance']) == {'accepted', 'rejected', 'pending'}
        assert all(isinstance(value, int) for value in body['acceptance'].values())
        assert [row['bucket'] for row in body['confidence_buckets']] == list(
            CLIENT_CONFIDENCE_LABELS
        )

    # Mặc định là `day`, và giá trị lạ bị từ chối chứ không âm thầm rơi về `day`.
    assert _get_analytics(ctx.client, 'day') == ctx.client.get(ANALYTICS_URL).json()
    assert ctx.client.get(f'{ANALYTICS_URL}?period=hour').status_code == 422

"""Payload `/detections/`: cờ opt-in `include_ocr_results` (Task 19).

Vì sao có cờ này: mảng `ocr_results` chiếm **98,98 %** khối lượng phản hồi (đo trên
DB thật: `limit=18` → 2 122 689 B, trong đó `ocr_results` 2 101 119 B; nhánh rút
gọn còn 22 126 B, tức 96 lần nhỏ hơn) trong khi sidebar dashboard chỉ cần **id OCR
đầu tiên** làm nhãn tàu dự phòng
(`client/src/utils/detection-display.ts`). Cờ phải **opt-in** (`= True`) để mọi
caller khác giữ nguyên payload từng byte — vì vậy test ghim cả hai nhánh: mặc
định không đổi, và nhánh tắt bỏ hẳn trường nặng nhưng vẫn giữ nhãn dự phòng.

Test đi qua đúng tầng FastAPI trên PostgreSQL thật (row seed trong transaction
**chưa commit**, rollback ở teardown) nên nó kiểm cả JSON serialize thật — chỗ
dễ vỡ nhất khi cắt trường, không chỉ hàm Python.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.detection import Detection
from app.models.user import User
from app.models.vessel import Vessel
from app.utils.pagination import MAX_PAGE_SIZE

LIST_URL = '/api/v1/detections/'

# 500 phần tử: đủ lớn để phép đo kích thước nói lên đúng lý do của Task 19 (một
# hàng thật đã từng có 35 798 phần tử OCR).
BIG_OCR_ELEMENTS = 500


def _utc(*args: int) -> datetime:
    """Mốc UTC dạng naive, khớp kiểu cột `timestamp without time zone`."""
    return datetime(*args)


def _seed(session) -> SimpleNamespace:
    """Seed mọi dạng `ocr_results` mà `getDetectionShipLabel` phân biệt.

    Thêm row `linked` đã gắn `Vessel` + duyệt đầy đủ để phép so hai nhánh đi qua cả
    object `vessel` lồng lẫn sáu trường duyệt (xem chú thích trong thân hàm).
    """
    tag = uuid4().hex[:12]
    rows: dict[str, Detection] = {}

    # Row 'linked' phải trỏ tới `Vessel`/`User` thật: để `vessel_id=None` và
    # `verified_by=None` như mọi row khác thì phép so "hai nhánh chỉ khác đúng một
    # khoá" không bao giờ đi qua object `vessel` lồng, cũng không so được sáu
    # trường luôn NULL (`audit_image_url`, `video_url`, `is_accepted`,
    # `rejection_reason`, `verified_at`, `verified_by`) — đột biến nhánh rút gọn ở
    # đúng những chỗ đó sẽ lọt qua test.
    vessel = Vessel(
        ship_id=f'OCRPAYLOAD-{tag}',
        name=f'payload {tag}',
        classification='unclassified',
    )
    verifier = User(
        username=f'ocrpayload-verifier-{tag}',
        full_name='OCR payload verifier',
        is_active=True,
    )
    session.add_all([vessel, verifier])
    session.flush()

    def add_row(key: str, ocr_results, **extra) -> Detection:
        extra.setdefault('vessel_id', None)  # mặc định không gắn tàu ⇒ nhãn rơi về id OCR
        row = Detection(
            track_id=f'ocrpayload-{tag}-{key}',
            start_time=_utc(2026, 9, 30, 10, 0, 0),
            created_at=_utc(2026, 9, 30, 10, 0, 0),
            ocr_results=ocr_results,
            confidence=0.5,
            **extra,
        )
        rows[key] = row
        session.add(row)
        return row

    add_row(
        'two',
        [{'id': f'OCR-{tag}', 'conf': 0.9}, {'id': f'OCR-{tag}-sau', 'conf': 0.8}],
    )
    add_row('blank', [{'id': '  \t '}])  # client trim → nhãn mặc định
    add_row('no_id', [{'conf': 0.5}])  # thiếu id → nhãn mặc định
    add_row('number_id', [{'id': 42}])  # `typeof id !== 'string'` → nhãn mặc định
    add_row('empty', [])  # mảng rỗng → nhãn mặc định
    add_row('null', None)  # null → nhãn mặc định
    add_row('big', [{'id': f'BIG-{i}', 'conf': 0.5} for i in range(BIG_OCR_ELEMENTS)])
    # Đường đi đầy đủ: `vessel` lồng đã điền + cả sáu trường duyệt khác NULL. Đường
    # dẫn `runs/...` (không phải `minio://`) để `audit_image_url`/`video_url` ổn định
    # giữa hai lần gọi — URL có token ký theo thời gian sẽ làm phép so byte loé đỏ.
    add_row(
        'linked',
        [{'id': f'LINKED-{tag}', 'conf': 0.7}],
        vessel_id=vessel.id,
        is_accepted=True,
        rejection_reason='ảnh audit mờ, đã duyệt tay',
        verified_at=_utc(2026, 9, 30, 10, 5, 0),
        verified_by=verifier.id,
        audit_image_path='runs/ocrpayload/audit.jpg',
        video_path='runs/ocrpayload/clip.mp4',
        berth_in_time=_utc(2026, 9, 30, 9, 55, 0),
    )
    session.flush()

    return SimpleNamespace(
        tag=tag,
        ids={key: row.id for key, row in rows.items()},
        total=len(rows),
        vessel_ship_id=vessel.ship_id,
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
    """Một trang chỉ chứa row vừa seed — khoanh vùng bằng `q=<tag>`.

    `q` truyền được đè để đo riêng một row (xem `test_lite_payload_is_much_smaller`).
    """
    params.setdefault('q', seeded.tag)
    response = seeded.client.get(LIST_URL, params={'limit': MAX_PAGE_SIZE, **params})
    assert response.status_code == 200, response.text[:300]
    return response


def _by_id(response) -> dict[int, dict]:
    rows = {item['id']: item for item in response.json()}
    assert len(rows) == len(response.json()), 'id trả về bị trùng'
    return rows


def test_default_keeps_ocr_results_and_adds_no_new_field(seeded) -> None:
    """Mặc định (không truyền cờ) vẫn là payload cũ: có `ocr_results`, không có trường mới."""
    rows = _by_id(_get(seeded))

    assert len(rows) == seeded.total
    assert len(rows[seeded.ids['big']]['ocr_results']) == BIG_OCR_ELEMENTS
    assert rows[seeded.ids['big']]['ocr_results'][0]['id'] == 'BIG-0'
    for row in rows.values():
        assert 'ocr_results' in row
        assert 'first_ocr_result_id' not in row, (
            'trường mới chỉ được xuất hiện ở nhánh tắt `ocr_results`, nếu không thì '
            'payload của mọi caller cũ đã đổi'
        )


def test_explicit_true_is_byte_identical_to_default(seeded) -> None:
    """`include_ocr_results=true` phải giống hệt mặc định, từng byte."""
    default = _get(seeded)
    explicit = _get(seeded, include_ocr_results='true')

    assert explicit.content == default.content


def test_include_ocr_results_false_drops_array_and_keeps_first_id(seeded) -> None:
    """Nhánh tắt: không còn `ocr_results`, nhưng id OCR đầu tiên vẫn được trả."""
    rows = _by_id(_get(seeded, include_ocr_results='false'))

    assert len(rows) == seeded.total
    for row in rows.values():
        assert 'ocr_results' not in row, 'mảng OCR phải biến mất hẳn khỏi payload'
        assert 'first_ocr_result_id' in row

    assert rows[seeded.ids['two']]['first_ocr_result_id'] == f'OCR-{seeded.tag}'
    # Chuỗi nguyên bản, KHÔNG trim ở server: client trim y như trước (nhãn mặc định).
    assert rows[seeded.ids['blank']]['first_ocr_result_id'] == '  \t '
    # Chỉ nhận chuỗi — client so `typeof id === 'string'` nên số/None phải rơi về nhãn mặc định.
    assert rows[seeded.ids['no_id']]['first_ocr_result_id'] is None
    assert rows[seeded.ids['number_id']]['first_ocr_result_id'] is None
    assert rows[seeded.ids['empty']]['first_ocr_result_id'] is None
    assert rows[seeded.ids['null']]['first_ocr_result_id'] is None


def test_lite_branch_keeps_total_count_header(seeded) -> None:
    """Nhánh rút gọn vẫn phải là một trang hợp lệ: `X-Total-Count` không được mất.

    Lỗi thật bắt được lúc đo qua HTTP thật: trả `JSONResponse` trực tiếp làm FastAPI
    **bỏ qua** `Response` được inject, nên header mà `set_total_header` đặt trên đó
    biến mất — client phân trang sẽ mất tổng số dòng.
    """
    for params in ({}, {'include_ocr_results': 'false'}):
        response = _get(seeded, **params)
        assert response.headers.get('X-Total-Count') == str(seeded.total), params


def test_lite_row_is_full_row_minus_ocr_results(seeded) -> None:
    """Nhánh tắt chỉ mất mảng OCR: mọi trường khác giữ nguyên giá trị và định dạng."""
    full = _by_id(_get(seeded))
    lite = _by_id(_get(seeded, include_ocr_results='false'))

    assert set(lite) == set(full), 'hai nhánh phải trả về đúng cùng tập row'
    # Chốt chống mù: row 'linked' phải thật sự mang object `vessel` lồng và sáu
    # trường duyệt khác NULL, nếu không vòng so ngay dưới đây không chạm tới chúng.
    linked = full[seeded.ids['linked']]
    for field in (
        'vessel',
        'audit_image_url',
        'video_url',
        'is_accepted',
        'rejection_reason',
        'verified_at',
        'verified_by',
    ):
        assert linked[field] is not None, f"row 'linked' phải có {field} khác NULL"
    assert linked['vessel']['ship_id'] == seeded.vessel_ship_id
    assert lite[seeded.ids['linked']]['vessel'] == linked['vessel']
    for row_id, row in lite.items():
        assert set(row) == (set(full[row_id]) - {'ocr_results'}) | {'first_ocr_result_id'}
        assert {k: v for k, v in row.items() if k != 'first_ocr_result_id'} == {
            k: v for k, v in full[row_id].items() if k != 'ocr_results'
        }


def test_lite_payload_is_much_smaller(seeded) -> None:
    """Lý do tồn tại của cờ: cùng row, payload nhỏ hơn ít nhất 10 lần.

    Đo trên **một row** (row `big`) vì mỗi row còn ~600 B trường cố định: đo cả
    trang 7 row thì phần cố định đó che mất tỉ lệ thật của mảng OCR.
    """
    only_big = f'{seeded.tag}-big'
    full = _get(seeded, q=only_big)
    lite = _get(seeded, q=only_big, include_ocr_results='false')

    assert [row['id'] for row in full.json()] == [seeded.ids['big']], 'phép đo phải khoanh đúng một row'
    assert len(lite.content) * 10 < len(full.content), (
        f'payload rút gọn {len(lite.content)} B không nhỏ hơn 10 lần {len(full.content)} B'
    )

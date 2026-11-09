#!/usr/bin/env python3
"""Spot-check **chỉ đọc** cho bộ lọc Task 8: `/orders/`, `/port-logs/`, `/audit-logs/`.

Cổng A/B của spec chỉ áp cho `/detections/` và `/invoices/` (xem
`scripts/ab_list_filters.py`), nên ba endpoint này chỉ cần một lưới đối chiếu nhẹ:

* **A (client)** — port trung thực logic lọc của trình duyệt
  (`client/src/features/orders/views/OrdersView.tsx:40-80`,
  `client/src/features/statistics/views/StatisticsView.tsx:34-61`,
  `client/src/features/backup/views/BackupView.tsx:19-43`,
  `client/src/utils/table-filters.ts`) trên **toàn bộ** row mà API trả cho trình
  duyệt khi không lọc (lấy hết bằng `limit=200` + `skip`).
* **B (SQL)** — gọi chính ba endpoint với cùng bộ lọc (cũng lấy hết bằng
  `limit=200` + `skip`).

So **tập id** của hai bên cho từng tổ hợp, in `✓`/`LỆCH` từng dòng và tổng kết
`Lệch: 0 mục · ✓ ĐẠT`; lệch thì in phần id chênh lệch và thoát mã 1.

Riêng `/orders/`: bảng `orders` của môi trường này đang **trống**, nên lượt đối
chiếu trên dữ liệu thật là 0 == 0. Vì vậy script chạy thêm **pha seed** — 4 đơn +
2 tàu + 2 loại tàu trong một transaction **rollback** — rồi mới đối chiếu đủ các
nhánh `q`/`vessel_id`/`vessel_type_id`/`status`/`min_total`/`max_total`/khoảng
ngày. Pha này không để lại row nào.

Mỗi endpoint còn được kiểm tra **thứ tự**: đi hết bảng bằng `limit=37` (cắt vào
giữa các nhóm khóa bằng nhau) phải trả đúng dãy id của lượt lấy một lần, không
lặp, không mất row — chỗ tiebreaker `id desc` phát huy tác dụng.

Hai điểm ngữ nghĩa cần nhớ khi đọc kết quả:

* `/port-logs/` có **hai điều khiển độc lập, AND với nhau**: select "Mã tàu
  (voted_ship_id)" (giá trị là mã tàu đầy đủ → tham số cũ `ship_id`, khớp đúng)
  và ô "Track ID (chứa)" (→ tham số `q`, khớp chứa **chỉ** trên `track_id`).
  Phía A port đúng hai vị từ đó; phép so vì thế không còn vòng tròn — bản đầu port
  chính phép OR của server nên không thể bất đồng với server (finding của review
  vòng 1). Tổ hợp có cả `q` lẫn `ship_id` nằm trong lưới, và
  `check_q_is_track_only` in phần chênh giữa "chỉ nhãn tàu" với "chỉ `track_id`"
  để chứng minh phép so có teeth.
* Khoảng ngày của client là **ngày địa phương**; client đổi thành instant rồi mới
  gửi lên, nên pha seed gửi đúng instant của biên ngày địa phương đó.

Script chỉ **ĐỌC**: pha 1 chạy trong transaction `READ ONLY`, pha seed rollback ở
cuối; không ghi gì xuống DB.
"""
from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional
from uuid import uuid4

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

with warnings.catch_warnings():
    # fastapi.testclient cảnh báo httpx2 ngay lúc import — không liên quan spot-check.
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.order import Order
from app.models.vessel import Vessel
from app.models.vessel_type import VesselType

ORDERS_URL = '/api/v1/orders/'
PORT_LOGS_URL = '/api/v1/port-logs/'
AUDIT_LOGS_URL = '/api/v1/audit-logs/'

# Đúng bằng `MAX_PAGE_SIZE` của server: đi hết dữ liệu bằng limit=200 + skip.
PAGE_SIZE = 200
# Cỡ trang lẻ để cắt vào giữa các nhóm khóa sắp xếp bằng nhau.
ODD_PAGE_SIZE = 37

# `_AUDIT_LIST_SKIP_ACTIONS` của repository: trang không bao giờ thấy các row này.
AUDIT_SKIP_ACTIONS = ('READ', 'HEAD', 'OPTIONS')
# Nhãn payload của `AuditLogRead.fill_legacy_aliases`.
MISSING_RECORD_ID = '—'
DEFAULT_TABLE_NAME = 'system'

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Port logic client (giữ nguyên ngữ nghĩa, kể cả các nhánh `?? ''`)
# --------------------------------------------------------------------------- #


def parse_api_date(value: Any) -> Optional[datetime]:
    """`client/src/utils/date-time.ts:11` — chuỗi không kèm offset được hiểu là UTC."""
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def epoch_ms(value: datetime) -> int:
    """Epoch ms như `Date.getTime()`: cắt bớt phần dưới mili-giây, không làm tròn."""
    delta = value.astimezone(timezone.utc) - EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1000 + delta.microseconds // 1000


def local_day_start(iso_date: str) -> datetime:
    """`dayStartMs` của client, trả về instant (client gửi instant lên API)."""
    return datetime.fromisoformat(f'{iso_date}T00:00:00').astimezone()


def local_day_end(iso_date: str) -> datetime:
    """`dayEndMs` của client, trả về instant."""
    return datetime.fromisoformat(f'{iso_date}T23:59:59.999').astimezone()


def iso_in_local_range(epoch: Optional[int], date_from: str, date_to: str) -> bool:
    """`isoInLocalDateRange` — thiếu thời gian thì bị loại khi có khoảng."""
    if not date_from and not date_to:
        return True
    if epoch is None:
        return False
    if date_from and epoch < epoch_ms(local_day_start(date_from)):
        return False
    if date_to and epoch > epoch_ms(local_day_end(date_to)):
        return False
    return True


def contains(haystack: Any, needle: str) -> bool:
    """`matchesAnyField`/`textMatches`: cắt khoảng trắng, thường hoá, `includes`."""
    trimmed = needle.strip().lower()
    if not trimmed:
        return True
    return trimmed in str(haystack if haystack is not None else '').lower()


def filter_ns(**overrides) -> SimpleNamespace:
    """Bộ lọc phía A; trường không dùng tới để None = không lọc.

    `instant_from`/`instant_to` dành cho các tổ hợp gửi **instant tuỳ ý** lên API
    (không phải biên ngày địa phương như client) — phía A khi đó so trực tiếp trên
    instant đã parse của payload, để kiểm tra việc quy đổi offset và việc cột
    `logged_at` (naive) được hiểu là UTC.
    """
    base = dict(
        q=None, status=None, vessel_id=None, vessel_type_id=None,
        date_from=None, date_to=None, min_total=None, max_total=None,
        ship_id=None, log_date=None, min_confidence=None,
        instant_from=None, instant_to=None,
        action_q=None, table_name_q=None, user_id=None,
    )
    return SimpleNamespace(**{**base, **overrides})


# --------------------------------------------------------------------------- #
# A — bộ lọc client của từng trang
# --------------------------------------------------------------------------- #


def orders_client_match(row: dict, f: SimpleNamespace) -> bool:
    """`OrdersView.tsx:40-80`.

    `matchedVessel` của client là `vessels.find(v => v.id === order.vessel_id)` trên
    danh sách `/vessels/` (ô "Mã tàu" lấy `value = vessel.id`, ô "Loại tàu" so với
    `matchedVessel.vessel_type_id`), nên phía A tra theo `VESSEL_BY_ID`.
    """
    vessel = row.get('vessel') or {}
    if f.q is not None and not any(
        contains(field, f.q)
        for field in (
            str(row.get('id')),
            vessel.get('ship_id'),
            vessel.get('name'),
            row.get('cargo_details'),
        )
    ):
        return False
    if f.status:
        status = str(row.get('status') or 'pending').lower()
        if status not in ('processing', 'completed', 'pending', 'cancelled'):
            status = 'pending'
        if status != f.status:
            return False
    matched_vessel = VESSEL_BY_ID.get(str(row.get('vessel_id')))
    if f.vessel_id and str(
        row.get('vessel_id') or (matched_vessel or {}).get('id') or ''
    ) != str(f.vessel_id):
        return False
    if f.vessel_type_id and str(
        (matched_vessel or {}).get('vessel_type_id') or ''
    ) != str(f.vessel_type_id):
        return False
    created = parse_api_date(row.get('created_at'))
    if not iso_in_local_range(
        epoch_ms(created) if created else None, f.date_from, f.date_to
    ):
        return False
    if f.instant_from is not None and (created is None or created < f.instant_from):
        return False
    if f.instant_to is not None and (created is None or created > f.instant_to):
        return False
    amount = float(row.get('total_amount') or 0)
    if f.min_total is not None and amount < float(f.min_total):
        return False
    if f.max_total is not None and amount > float(f.max_total):
        return False
    return True


def port_log_client_match(row: dict, f: SimpleNamespace) -> bool:
    """`StatisticsView.tsx:34-61` — hai điều khiển độc lập, AND với nhau.

    * select "Mã tàu (voted_ship_id)": option là `vessel.ship_id` đầy đủ, phía
      endpoint đi qua tham số cũ `ship_id` (khớp đúng, ngữ nghĩa không đổi theo
      ruling vòng sửa 1). Client dùng `includes` trên nhãn nên về lý thuyết còn
      khớp cả nhãn dài hơn chứa mã này; `check_ship_select_superset` đo phần chênh
      đó trên dữ liệu thật (không tính vào cổng — `ship_id` là hợp đồng cũ).
    * ô "Track ID (chứa)": khớp chứa, không phân biệt hoa thường, **chỉ** trên
      `track_id` → tham số `q`.
    """
    ship = row.get('voted_ship_id') or row.get('ship_id') or ''
    logged = parse_api_date(row.get('logged_at') or row.get('log_date'))
    if f.q is not None and not contains(row.get('track_id'), f.q):
        return False
    if f.ship_id and ship != f.ship_id:
        return False
    if f.vessel_type_id and str(
        (VESSEL_BY_SHIP_ID.get(ship) or {}).get('vessel_type_id') or ''
    ) != str(f.vessel_type_id):
        return False
    if f.log_date and (logged is None or logged.date().isoformat() != f.log_date):
        return False
    if f.min_confidence is not None and float(row.get('confidence') or 0) < float(f.min_confidence):
        return False
    if not iso_in_local_range(
        epoch_ms(logged) if logged else None, f.date_from, f.date_to
    ):
        return False
    if f.instant_from is not None and (logged is None or logged < f.instant_from):
        return False
    if f.instant_to is not None and (logged is None or logged > f.instant_to):
        return False
    return True


def audit_client_match(row: dict, f: SimpleNamespace) -> bool:
    """`BackupView.tsx:19-43` + nhãn payload của `AuditLogRead.fill_legacy_aliases`."""
    action = row.get('action') or ''
    if action in AUDIT_SKIP_ACTIONS:
        return False
    table_name = (row.get('entity_type') or DEFAULT_TABLE_NAME).strip() or DEFAULT_TABLE_NAME
    record_id = str(row['entity_id']) if row.get('entity_id') is not None else MISSING_RECORD_ID
    user = row.get('user') or {}
    if f.q is not None and not any(
        contains(field, f.q)
        for field in (action, record_id, user.get('full_name'), user.get('email'))
    ):
        return False
    if f.table_name_q is not None and not contains(table_name, f.table_name_q):
        return False
    if f.action_q is not None and not contains(action, f.action_q):
        return False
    if f.user_id and str(row.get('user_id') or '') != str(f.user_id):
        return False
    created = parse_api_date(row.get('created_at'))
    if not iso_in_local_range(
        epoch_ms(created) if created else None, f.date_from, f.date_to
    ):
        return False
    if f.instant_from is not None and (created is None or created < f.instant_from):
        return False
    if f.instant_to is not None and (created is None or created > f.instant_to):
        return False
    return True


# --------------------------------------------------------------------------- #
# Khung so sánh
# --------------------------------------------------------------------------- #


@dataclass
class Case:
    """Một tổ hợp: nhãn, tham số gửi API, và bộ lọc client tương ứng."""

    label: str
    params: dict
    filters: SimpleNamespace

    @classmethod
    def build(cls, label: str, params: dict, **overrides) -> 'Case':
        return cls(label, params, filter_ns(**overrides))


@dataclass
class EndpointCheck:
    name: str
    url: str
    match: Callable[[dict, SimpleNamespace], bool]
    cases: list[Case] = field(default_factory=list)


class Api:
    """TestClient dùng chung session với script (không cần token thật)."""

    def __init__(self, session) -> None:
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=1, is_active=True, username='admin'
        )
        self.client = TestClient(app)

    def fetch_all(self, url: str, params: Optional[dict] = None) -> list[dict]:
        """Đi hết các trang bằng `limit=PAGE_SIZE` + `skip`, trả về mọi row.

        Đồng thời khẳng định `X-Total-Count` không đổi giữa các trang và bằng đúng
        số row lấy được — hợp đồng "mảng trần + X-Total-Count" của Task 4-7.
        """
        rows: list[dict] = []
        skip = 0
        expected_total: Optional[int] = None
        while True:
            batch, total = self.fetch_page(url, params, skip=skip, limit=PAGE_SIZE)
            if expected_total is None:
                expected_total = total
            assert total == expected_total, (
                f'X-Total-Count đổi giữa các trang: {total} != {expected_total}'
            )
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            skip += PAGE_SIZE
        assert len(rows) == expected_total, (
            f'X-Total-Count={expected_total} nhưng lấy được {len(rows)} row'
        )
        return rows

    def fetch_page(
        self, url: str, params: Optional[dict], *, skip: int, limit: int
    ) -> tuple[list[dict], int]:
        """Đúng một lượt gọi API với `skip`/`limit` chỉ định, kèm `X-Total-Count`."""
        response = self.client.get(url, params={**(params or {}), 'skip': skip, 'limit': limit})
        assert response.status_code == 200, response.text[:300]
        total = response.headers.get('X-Total-Count')
        assert total is not None, 'thiếu header X-Total-Count'
        return response.json(), int(total)

    def fetch_ids(self, url: str, params: dict) -> list[int]:
        return [row['id'] for row in self.fetch_all(url, params)]

    def close(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()


def run_cases(api: Api, check: EndpointCheck, all_rows: list[dict]) -> int:
    """So tập id của từng tổ hợp; in từng dòng, trả về số mục lệch."""
    print(f'\n== {check.name} — {len(all_rows)} row lấy được từ API (không lọc) ==')
    mismatches = 0
    for case in check.cases:
        expected = {row['id'] for row in all_rows if check.match(row, case.filters)}
        actual = set(api.fetch_ids(check.url, case.params))
        ok = expected == actual
        mismatches += 0 if ok else 1
        print(f'  {"✓" if ok else "LỆCH":<4} {case.label:<62} A={len(expected):<5} B={len(actual):<5}')
        if not ok:
            print(f'       chỉ có ở A: {sorted(expected - actual)[:10]}')
            print(f'       chỉ có ở B: {sorted(actual - expected)[:10]}')
    print(f'  → Lệch: {mismatches}/{len(check.cases)} tổ hợp')
    return mismatches


def check_ordering(api: Api, name: str, url: str, params: dict) -> int:
    """Dãy id khi đi từng trang nhỏ phải bằng dãy id lấy một lần, không lặp/mất row."""
    single = api.fetch_ids(url, params)
    paged: list[int] = []
    totals: set[int] = set()
    for skip in range(0, len(single), ODD_PAGE_SIZE):
        batch, total = api.fetch_page(url, params, skip=skip, limit=ODD_PAGE_SIZE)
        totals.add(total)
        paged.extend(row['id'] for row in batch)
    ok = (
        single == paged
        and len(set(paged)) == len(paged)
        and totals == {len(single)}
    )
    print(
        f'  {"✓" if ok else "LỆCH":<4} thứ tự {name:<54} '
        f'1 lượt={len(single):<5} chia trang {ODD_PAGE_SIZE}={len(paged):<5}'
    )
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# Tổ hợp dựng từ dữ liệu thật
# --------------------------------------------------------------------------- #


def live_port_log_cases(rows: list[dict]) -> list[Case]:
    """Giá trị lấy từ chính dữ liệu thật, không hard-code số của môi trường."""
    ship_ids = sorted({row['voted_ship_id'] for row in rows if row.get('voted_ship_id')})
    track = next((row['track_id'] for row in rows if row.get('track_id')), '')
    confidence = sorted(
        {float(row['confidence']) for row in rows if row.get('confidence') is not None}
    )
    times = sorted(parse_api_date(row['logged_at']) for row in rows if row.get('logged_at'))
    middle = times[len(times) // 2]
    threshold = confidence[len(confidence) // 2]
    day = times[0].date().isoformat()
    middle_day = middle.astimezone().date().isoformat()

    # Cặp (nhãn tàu, mảnh track) lấy từ hai row KHÁC nhãn nhau để dựng tổ hợp
    # `q` + `ship_id` — đúng hai điều khiển độc lập của trang, AND với nhau.
    paired = next(
        (row for row in rows if row.get('track_id') and row.get('voted_ship_id')), None
    )
    label_a = (paired or {}).get('voted_ship_id') or ship_ids[0]
    frag_a = ((paired or {}).get('track_id') or track)[4:16].lower()
    paired_b = next(
        (
            row
            for row in rows
            if row.get('track_id') and row.get('voted_ship_id') and row['voted_ship_id'] != label_a
        ),
        None,
    )
    label_b = (paired_b or {}).get('voted_ship_id') or next(
        (sid for sid in ship_ids if sid != label_a), label_a
    )
    frag_b = ((paired_b or {}).get('track_id') or track)[4:16].lower()
    # Mốc thời gian/ngưỡng lấy ĐÚNG bằng row `paired` để tổ hợp AND bên dưới chắc
    # chắn có ít nhất 1 row (không rỗng một cách vô nghĩa).
    paired = paired or {}
    ping = parse_api_date(paired.get('logged_at'))
    ping_iso = ping.isoformat() if ping else times[0].isoformat()
    ping_conf = float(paired.get('confidence') or 0.0)

    return [
        Case.build('không lọc', {}),
        # Ô "Track ID (chứa)": chỉ khớp `track_id` (nhánh track, viết thường).
        Case.build(f'q={track[4:16].lower()!r} (nhánh track_id, viết thường)',
                   {'q': track[4:16].lower()}, q=track[4:16].lower()),
        # Nhãn tàu KHÔNG đi qua `q`: needle có thật trong nhãn nhưng không có trong
        # `track_id` nào → phải 0 row (nếu ai đó nối lại nhánh nhãn tàu thì LỆCH).
        Case.build(f'q={label_a!r} (chỉ có trong nhãn tàu, không có trong track_id)',
                   {'q': label_a}, q=label_a),
        Case.build(f"q='%' (wildcard bị escape)", {'q': '%'}, q='%'),
        Case.build(f"q={label_a[:3] + '_'!r} (wildcard '_' bị escape)",
                   {'q': f'{label_a[:3]}_'}, q=f'{label_a[:3]}_'),
        Case.build(f'ship_id={label_b!r} (select mã tàu, khớp đúng)',
                   {'ship_id': label_b}, ship_id=label_b),
        # Hai điều khiển ĐỘC LẬP, AND: track khớp + mã tàu khớp.
        Case.build(f'q={frag_a!r} + ship_id={label_a!r} (AND, cùng row)',
                   {'q': frag_a, 'ship_id': label_a}, q=frag_a, ship_id=label_a),
        Case.build(f'q={frag_b!r} + ship_id={label_a!r} (AND, khác nhãn → thường rỗng)',
                   {'q': frag_b, 'ship_id': label_a}, q=frag_b, ship_id=label_a),
        Case.build(f'q={frag_a!r} + ship_id={label_b!r} (AND, khác nhãn → thường rỗng)',
                   {'q': frag_a, 'ship_id': label_b}, q=frag_a, ship_id=label_b),
        Case.build(f'log_date={day} (tham số cũ)',
                   {'log_date': day}, log_date=day),
        Case.build('min_confidence=0 (thiếu confidence = 0)',
                   {'min_confidence': 0}, min_confidence=0.0),
        Case.build(f'min_confidence={threshold}', {'min_confidence': threshold},
                   min_confidence=threshold),
        Case.build(f'logged_from/to = ngày địa phương {middle_day} (client gửi instant)', {
            'logged_from': local_day_start(middle_day).isoformat(),
            'logged_to': local_day_end(middle_day).isoformat(),
        }, date_from=middle_day, date_to=middle_day),
        Case.build(f'logged_from={middle.isoformat()} (instant tuỳ ý)',
                   {'logged_from': middle.isoformat()}, instant_from=middle),
        Case.build('khoảng instant tuỳ ý quanh giữa bảng', {
            'logged_from': (middle - timedelta(hours=7)).isoformat(),
            'logged_to': (middle + timedelta(hours=7)).isoformat(),
        }, instant_from=middle - timedelta(hours=7), instant_to=middle + timedelta(hours=7)),
        Case.build('q (track) + ship_id + min_confidence + khoảng thời gian (AND)', {
            'q': frag_a,
            'ship_id': label_a,
            'min_confidence': ping_conf,
            'logged_from': ping_iso,
            'logged_to': ping_iso,
        }, q=frag_a, ship_id=label_a, min_confidence=ping_conf,
            instant_from=ping, instant_to=ping),
    ]


def live_audit_cases(rows: list[dict], user_id: Optional[int]) -> list[Case]:
    times = sorted(parse_api_date(row['created_at']) for row in rows if row.get('created_at'))
    middle = times[len(times) // 2]
    entity_types = sorted(
        {(row.get('entity_type') or '').strip() for row in rows if row.get('entity_type')}
    )
    entity = entity_types[0]
    middle_day = middle.astimezone().date().isoformat()
    cases = [
        Case.build('không lọc', {}),
        Case.build("q='CREATE' (nhánh action)", {'q': 'CREATE'}, q='CREATE'),
        Case.build("q='—' (nhánh record_id thiếu entity_id)",
                   {'q': MISSING_RECORD_ID}, q=MISSING_RECORD_ID),
        Case.build("q='%' (wildcard bị escape)", {'q': '%'}, q='%'),
        Case.build("action='DEL' (khớp chứa)", {'action': 'DEL'}, action_q='DEL'),
        Case.build(f'table_name={entity!r} (khớp chứa)', {'table_name': entity}, table_name_q=entity),
        Case.build('table_name viết HOA (không phân biệt hoa thường)',
                   {'table_name': entity.upper()}, table_name_q=entity.upper()),
        Case.build('action + table_name (AND)', {'action': 'CREATE', 'table_name': entity},
                   action_q='CREATE', table_name_q=entity),
        Case.build(f'created_from/to = ngày địa phương {middle_day} (client gửi instant)', {
            'created_from': local_day_start(middle_day).isoformat(),
            'created_to': local_day_end(middle_day).isoformat(),
        }, date_from=middle_day, date_to=middle_day),
        Case.build(f'created_from={middle.isoformat()} (instant tuỳ ý)',
                   {'created_from': middle.isoformat()}, instant_from=middle),
        Case.build('khoảng instant tuỳ ý quanh giữa bảng', {
            'created_from': (middle - timedelta(hours=7)).isoformat(),
            'created_to': (middle + timedelta(hours=7)).isoformat(),
        }, instant_from=middle - timedelta(hours=7), instant_to=middle + timedelta(hours=7)),
    ]
    if user_id is not None:
        cases.append(Case.build(f'user_id={user_id} (tham số cũ)', {'user_id': user_id},
                                user_id=str(user_id)))
        user_row = next((row for row in rows if str(row.get('user_id')) == str(user_id)), None)
        email = ((user_row or {}).get('user') or {}).get('email')
        if email:
            cases.append(Case.build(
                f'q={email!r} (nhánh email) + user_id', {'q': email, 'user_id': user_id},
                q=email, user_id=str(user_id),
            ))
    return cases


# --------------------------------------------------------------------------- #
# Pha 1 — dữ liệu thật (READ ONLY)
# --------------------------------------------------------------------------- #


def check_q_is_track_only(api: Api, rows: list[dict]) -> int:
    """Chứng minh phép so `q` không còn vòng tròn.

    Chọn một nhãn tàu có thật **không** xuất hiện trong `track_id` nào rồi so ba
    con số trên cùng tập row: số row khớp nhãn, số row khớp `track_id`, và số row
    SQL trả về. Nếu ai đó nối lại nhánh nhãn tàu vào `q` thì cột SQL sẽ bằng con số
    OR (lớn hơn) và lượt này báo LỆCH — đúng thứ bản port cũ (port chính phép OR
    của server) không thể phát hiện.

    Nếu không dựng được ca (mọi nhãn tàu đều nằm trong `track_id`) thì báo LỆCH
    chứ **không** bỏ qua: cổng này không được phép im lặng ĐẠT khi chưa kiểm tra gì.
    """
    needle = next(
        (
            label
            for label in sorted({row['voted_ship_id'] for row in rows if row.get('voted_ship_id')})
            if not any(contains(row.get('track_id'), label) for row in rows)
        ),
        None,
    )
    if needle is None:
        # Cổng chống OR: mọi nhãn tàu đều xuất hiện trong `track_id` nên không dựng
        # được ca phân biệt — lượt này KHÔNG kiểm tra được gì. Trước đây chỗ này in
        # "(bỏ qua: …)" rồi trả 0, tức cổng có thể im lặng ĐẠT mà không hề chạy;
        # giờ báo LỆCH để không bao giờ bỏ qua được.
        print('  LỆCH q chỉ có trong nhãn tàu: KHÔNG dựng được ca — mọi nhãn tàu đều '
              'xuất hiện trong `track_id`; cổng chống OR không được phép bỏ qua.')
        return 1
    by_label = sum(1 for row in rows if contains(row.get('voted_ship_id'), needle))
    by_track = sum(1 for row in rows if contains(row.get('track_id'), needle))
    or_count = sum(
        1
        for row in rows
        if contains(row.get('voted_ship_id'), needle) or contains(row.get('track_id'), needle)
    )
    sql_count = len(api.fetch_ids(PORT_LOGS_URL, {'q': needle}))
    ok = sql_count == by_track and by_track < or_count
    print(
        f'  {"✓" if ok else "LỆCH":<4} q={needle!r} chỉ có trong nhãn tàu: '
        f'nhãn={by_label:<5} track={by_track:<5} SQL={sql_count:<5} '
        f'(OR cũ sẽ trả {or_count})'
    )
    return 0 if ok else 1


def check_ship_select_superset(rows: list[dict]) -> None:
    """Thông tin (không tính vào cổng): client dùng `includes` cho select mã tàu.

    Select chỉ phát ra `vessel.ship_id` đầy đủ nên `includes` trùng khớp đúng, trừ
    khi có nhãn tàu **dài hơn** chứa mã đó (dữ liệu thật có vài cặp). Endpoint giữ
    `ship_id` khớp đúng theo ruling nên phần chênh này được in ra để Task 14 biết,
    không tính là lỗi của Task 8.
    """
    labels = sorted({row['voted_ship_id'] for row in rows if row.get('voted_ship_id')})
    pairs = [
        (vessel_id, label)
        for vessel_id in sorted(VESSEL_BY_SHIP_ID)
        for label in labels
        if label != vessel_id and contains(label, vessel_id)
    ]
    if not pairs:
        print('  (thông tin) không có cặp nhãn-dài-hơn-chứa-mã-tàu nào trong dữ liệu thật')
        return
    for vessel_id, label in pairs[:6]:
        includes = sum(1 for row in rows if contains(row.get('voted_ship_id'), vessel_id))
        exact = sum(1 for row in rows if (row.get('voted_ship_id') or '') == vessel_id)
        print(
            f'  (thông tin) ship_id={vessel_id!r}: client `includes`={includes} row, '
            f'khớp đúng={exact} row — chênh do nhãn {label!r}'
        )


def live_phase(api: Api) -> int:
    mismatches = 0

    port_rows = api.fetch_all(PORT_LOGS_URL, {})
    mismatches += run_cases(
        api,
        EndpointCheck('/port-logs/ (dữ liệu thật)', PORT_LOGS_URL,
                      port_log_client_match, live_port_log_cases(port_rows)),
        port_rows,
    )
    mismatches += check_q_is_track_only(api, port_rows)
    mismatches += check_ordering(api, 'mặc định (time desc)', PORT_LOGS_URL, {})
    check_ship_select_superset(port_rows)

    audit_rows = api.fetch_all(AUDIT_LOGS_URL, {})
    user_id = next((row.get('user_id') for row in audit_rows if row.get('user_id')), None)
    mismatches += run_cases(
        api,
        EndpointCheck('/audit-logs/ (dữ liệu thật)', AUDIT_LOGS_URL,
                      audit_client_match, live_audit_cases(audit_rows, user_id)),
        audit_rows,
    )
    mismatches += check_ordering(api, 'mặc định (created_at desc)', AUDIT_LOGS_URL, {})

    order_rows = api.fetch_all(ORDERS_URL, {})
    print(f'\n== /orders/ (dữ liệu thật) — {len(order_rows)} row ==')
    if order_rows:
        mismatches += run_cases(
            api,
            EndpointCheck('/orders/ (dữ liệu thật)', ORDERS_URL, orders_client_match,
                          [Case.build('không lọc', {})]),
            order_rows,
        )
    else:
        print('  bảng trống → lượt đối chiếu thật là 0 == 0, không kết luận được gì;')
        print('  xem pha seed bên dưới (cũng rollback nên không để lại row).')
    return mismatches


# --------------------------------------------------------------------------- #
# Pha 2 — seed rollback rồi đối chiếu /orders/ (bảng thật đang trống)
# --------------------------------------------------------------------------- #


def seeded_orders_phase() -> int:
    global VESSEL_BY_SHIP_ID, VESSEL_BY_ID
    session = SessionLocal()
    try:
        tag = uuid4().hex[:10]
        type_a = VesselType(type_name=f'spotcheck-a-{tag}')
        type_b = VesselType(type_name=f'spotcheck-b-{tag}')
        session.add_all([type_a, type_b])
        session.flush()
        vessel_a = Vessel(ship_id=f'SPOTCHECK-A-{tag}', name=f'Spot Check A {tag}',
                          classification='monthly', vessel_type_id=type_a.id)
        vessel_b = Vessel(ship_id=f'SPOTCHECK-B-{tag}', name=f'Spot Check B {tag}',
                          classification='monthly', vessel_type_id=type_b.id)
        session.add_all([vessel_a, vessel_b])
        session.flush()
        # Danh sách `/vessels/` mà client dùng được nạp lại sau khi seed để có cả
        # hai tàu vừa tạo (client nạp danh sách này lúc mở trang).
        VESSEL_BY_SHIP_ID, VESSEL_BY_ID = load_vessel_map(session)

        # `created_at` ở tương lai để row seed đứng đầu thứ tự `created_at desc`.
        base = datetime.now(timezone.utc) + timedelta(days=30)
        rows = [
            Order(order_number=f'SPOTCHECK-{tag}-1', vessel_id=vessel_a.id, status='PENDING',
                  total_amount=Decimal('100.00'), description=f'spotcheck-{tag}-A',
                  created_at=base + timedelta(seconds=300), updated_at=base + timedelta(seconds=300)),
            Order(order_number=f'SPOTCHECK-{tag}-2', vessel_id=vessel_a.id, status='COMPLETED',
                  total_amount=Decimal('500.00'), description='Gạo',
                  created_at=base + timedelta(seconds=200), updated_at=base + timedelta(seconds=200)),
            Order(order_number=f'SPOTCHECK-{tag}-3', vessel_id=vessel_b.id, status='CANCELLED',
                  total_amount=Decimal('0.00'), description=f'spotcheck-{tag}-B',
                  created_at=base + timedelta(seconds=100), updated_at=base + timedelta(seconds=100)),
            Order(order_number=f'SPOTCHECK-{tag}-4', vessel_id=None, status='PENDING',
                  total_amount=Decimal('250.00'), description=f'spotcheck-{tag}-N',
                  created_at=base, updated_at=base),
        ]
        session.add_all(rows)
        session.flush()
        marker_ids = {row.id for row in rows}

        # Ngày địa phương chứa 3 đơn đầu; client đổi biên ngày thành instant rồi gửi.
        local_day = (base + timedelta(seconds=150)).astimezone().date().isoformat()

        api = Api(session)
        try:
            all_rows = api.fetch_all(ORDERS_URL, {})
            assert len(all_rows) == len(rows), 'bảng orders thật không trống — pha seed cần bảng trống'
            marker_rows = [row for row in all_rows if row['id'] in marker_ids]
            assert len(marker_rows) == len(rows), 'row seed không lấy được qua API'
            cases = [
                Case.build('không lọc', {}),
                Case.build(f'q={tag!r} (nhánh mô tả + tên tàu)', {'q': tag}, q=tag),
                Case.build(f'q=<id {rows[0].id}> (nhánh id)', {'q': str(rows[0].id)}, q=str(rows[0].id)),
                Case.build(f'q={vessel_a.ship_id!r} (nhánh ship_id)',
                           {'q': vessel_a.ship_id}, q=vessel_a.ship_id),
                Case.build(f'q={vessel_a.name!r} (nhánh tên tàu)', {'q': vessel_a.name}, q=vessel_a.name),
                Case.build(f'q={f"spotcheck-{tag}-b"!r} (nhánh mô tả, viết thường)',
                           {'q': f'spotcheck-{tag}-b'}, q=f'spotcheck-{tag}-b'),
                Case.build("q='%' (wildcard bị escape)", {'q': '%'}, q='%'),
                Case.build("q='SPOTCHECK_' (wildcard '_' bị escape)",
                           {'q': 'SPOTCHECK_'}, q='SPOTCHECK_'),
                Case.build(f'vessel_id={vessel_a.id}', {'vessel_id': vessel_a.id}, vessel_id=vessel_a.id),
                Case.build(f'vessel_type_id={type_b.id}', {'vessel_type_id': type_b.id},
                           vessel_type_id=type_b.id),
                Case.build("status='pending' (tham số cũ)", {'status': 'pending'}, status='pending'),
                Case.build('min_total=100', {'min_total': 100}, min_total=100),
                Case.build('max_total=100', {'max_total': 100}, max_total=100),
                Case.build(f'created_from/to = ngày địa phương {local_day} (client gửi instant)', {
                    'created_from': local_day_start(local_day).isoformat(),
                    'created_to': local_day_end(local_day).isoformat(),
                }, date_from=local_day, date_to=local_day),
                Case.build(f'created_from={base + timedelta(seconds=100)} (instant tuỳ ý)',
                           {'created_from': (base + timedelta(seconds=100)).isoformat()},
                           instant_from=base + timedelta(seconds=100)),
            ]
            mismatches = run_cases(
                api,
                EndpointCheck('/orders/ (seed, rollback)', ORDERS_URL, orders_client_match, cases),
                marker_rows,
            )
            mismatches += check_ordering(api, 'mặc định (created_at desc)', ORDERS_URL, {'q': tag})
            return mismatches
        finally:
            api.close()
    finally:
        session.rollback()
        session.close()
        app.dependency_overrides.clear()


def load_vessel_map(session) -> tuple[dict, dict]:
    """Danh sách `/vessels/` mà client dùng: tra theo `ship_id` và theo `id`."""
    by_ship_id: dict[str, dict] = {}
    by_id: dict[str, dict] = {}
    for vessel in session.query(Vessel).order_by(Vessel.id.asc()).all():
        row = {
            'id': vessel.id, 'ship_id': vessel.ship_id, 'vessel_type_id': vessel.vessel_type_id,
        }
        by_ship_id.setdefault(vessel.ship_id, row)
        by_id.setdefault(str(vessel.id), row)
    return by_ship_id, by_id


VESSEL_BY_SHIP_ID: dict[str, dict] = {}
VESSEL_BY_ID: dict[str, dict] = {}


def main() -> int:
    global VESSEL_BY_SHIP_ID, VESSEL_BY_ID
    print('Spot-check bộ lọc Task 8 — chỉ đọc, dữ liệu thật của PostgreSQL.')
    print(f'Timezone của máy chạy script: {datetime.now().astimezone().tzinfo} '
          '(client lọc theo ngày địa phương)')

    session = SessionLocal()
    try:
        session.execute(text('SET TRANSACTION READ ONLY'))
        VESSEL_BY_SHIP_ID, VESSEL_BY_ID = load_vessel_map(session)
        api = Api(session)
        try:
            mismatches = live_phase(api)
        finally:
            api.close()
    finally:
        session.rollback()
        session.close()
        app.dependency_overrides.clear()

    mismatches += seeded_orders_phase()

    print('\n' + '=' * 78)
    if mismatches:
        print(f'Lệch: {mismatches} mục · ✗ KHÔNG ĐẠT')
        return 1
    print('Lệch: 0 mục · ✓ ĐẠT')
    return 0


if __name__ == '__main__':
    sys.exit(main())

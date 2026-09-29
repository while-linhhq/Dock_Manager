#!/usr/bin/env python3
"""A/B hai nhóm bộ lọc chạy ở SQL: trang bến (7 bộ lọc) và trang hoá đơn (8 bộ lọc).

Chạy trên **dữ liệu thật** của bảng `detections` và `invoices`:

* **A (client)** — port trung thực logic lọc của trình duyệt
  (`client/src/features/port/views/PortView.tsx:107-161`,
  `client/src/features/revenue/views/RevenueView.tsx:168-225`,
  `client/src/utils/table-filters.ts`, `client/src/utils/detection-display.ts`,
  `client/src/features/revenue/components/revenue-invoice-display.tsx`), chạy qua
  **toàn bộ tổ hợp** giá trị lọc trên đúng những row mà API trả cho trình duyệt
  (lấy hết bằng `limit=200` + `skip`). Với hoá đơn, "row mà API trả cho trình
  duyệt" là danh sách của từng cặp (tab nguồn tạo × sub-tab) — đúng những gì
  `revenueStore.fetchInvoices` gọi.
* **B (SQL)** — gọi chính endpoint `/api/v1/detections/` và `/api/v1/invoices/`
  (bộ lọc + sắp xếp mới chạy ở SQL), cũng đi hết các trang bằng `limit=200` + `skip`.

So **tập id** của hai bên cho từng tổ hợp. Khớp hết thì in
`Lệch: 0 tổ hợp · ✓ ĐẠT`; lệch thì in tổ hợp gây lệch kèm phần id chênh lệch và
thoát mã 1.

`--tz` (mặc định: timezone của máy) là timezone dùng để quy đổi "ngày trên lịch"
sang instant UTC: client lọc theo ngày địa phương của trình duyệt nên hai bên chỉ
so được với nhau khi cùng timezone.

Script chỉ **ĐỌC**: mọi truy vấn nằm trong một transaction `READ ONLY` và bị
rollback ở cuối; không ghi gì xuống DB.
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import warnings
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone, tzinfo
from itertools import product
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

with warnings.catch_warnings():
    # fastapi.testclient cảnh báo httpx2 ngay lúc import — không liên quan tới A/B.
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.vessel import Vessel

DETECTION_LIST_URL = '/api/v1/detections/'
INVOICE_LIST_URL = '/api/v1/invoices/'

# Đúng bằng `MAX_PAGE_SIZE` của server: đi hết dữ liệu bằng limit=200 + skip.
PAGE_SIZE = 200

# `client/src/utils/detection-display.ts:4`
UNKNOWN_SHIP_LABEL = 'KHÔNG XÁC ĐỊNH'
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Port logic client (giữ nguyên ngữ nghĩa, kể cả các nhánh `?? ''`)
# --------------------------------------------------------------------------- #


def epoch_ms(value: datetime) -> int:
    """Epoch ms như `Date.getTime()`: cắt bớt phần dưới mili-giây, không làm tròn."""
    delta = value.astimezone(timezone.utc) - EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1000 + delta.microseconds // 1000


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


def get_detection_ship_label(row: dict) -> str:
    """`detection-display.ts:6` — ship_id của tàu, rồi id OCR đầu tiên, rồi nhãn mặc định."""
    vessel = row.get('vessel') or {}
    from_vessel = (vessel.get('ship_id') or '').strip()
    if from_vessel:
        return from_vessel
    items = row.get('ocr_results')
    if isinstance(items, list) and items:
        first = items[0] or {}
        ocr_id = first.get('id') if isinstance(first, dict) else None
        if isinstance(ocr_id, str) and ocr_id.strip():
            return ocr_id.strip()
    return UNKNOWN_SHIP_LABEL


def _first_not_none(*values: Any) -> Any:
    """Toán tử `??` của JS: chỉ nhảy qua null/undefined, không nhảy qua chuỗi rỗng."""
    for value in values:
        if value is not None:
            return value
    return None


def get_detection_display_time_iso(row: dict) -> Optional[str]:
    """`detection-display.ts:22` — start_time, fallback created_at, null nếu không parse được."""
    raw = _first_not_none(row.get('start_time'), row.get('created_at'))
    if not raw:
        return None
    return raw if parse_api_date(raw) else None


def get_detection_sort_ts(row: dict) -> int:
    """`detection-display.ts:35` — berth_in_time → start_time → created_at (epoch ms)."""
    parsed = parse_api_date(
        _first_not_none(row.get('berth_in_time'), row.get('start_time'), row.get('created_at'))
    )
    return epoch_ms(parsed) if parsed else 0


def matches_any_field(needle: str, *haystacks: Any) -> bool:
    """`table-filters.ts:59` — needle rỗng thì khớp tất cả, ngược lại OR contains."""
    normalized = (needle or '').strip().lower()
    if not normalized:
        return True
    return any(normalized in ('' if item is None else str(item)).lower() for item in haystacks)


def _local_day_ms(day: str, tz: tzinfo, *, end_of_day: bool) -> Optional[int]:
    """`table-filters.ts:4/11` — biên ngày theo lịch địa phương (`T00:00:00` / `T23:59:59.999`)."""
    if not day:
        return None
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        return None  # JS: new Date(...) không hợp lệ → NaN → bỏ qua biên đó
    hms = (23, 59, 59, 999_000) if end_of_day else (0, 0, 0, 0)
    moment = datetime(parsed.year, parsed.month, parsed.day, *hms, tzinfo=tz)
    return epoch_ms(moment)


def iso_in_local_date_range(
    iso: Optional[str], date_from: str, date_to: str, tz: tzinfo
) -> bool:
    """`table-filters.ts:18` — không có biên thì qua; thiếu/không parse được iso thì loại."""
    if not date_from and not date_to:
        return True
    if not iso:
        return False
    parsed = parse_api_date(iso)
    if parsed is None:
        return False
    moment = epoch_ms(parsed)
    if date_from:
        start = _local_day_ms(date_from, tz, end_of_day=False)
        if start is not None and moment < start:
            return False
    if date_to:
        end = _local_day_ms(date_to, tz, end_of_day=True)
        if end is not None and moment > end:
            return False
    return True


def js_number(value: Any) -> Optional[float]:
    """`Number(x)` của JS cho giá trị API: None/không phải số → None (tức NaN)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def get_invoice_berth_minutes(row: dict) -> Optional[float]:
    """`revenue-invoice-display.ts:9` — seconds trước, fallback hours; null nếu không có."""
    total_seconds = js_number(row.get('berth_duration_seconds'))
    if total_seconds is None or total_seconds <= 0:
        hours = js_number(row.get('berth_duration_hours'))
        if hours is not None and hours > 0:
            total_seconds = float(math.floor(hours * 3600 + 0.5))  # Math.round
    if total_seconds is None or total_seconds <= 0:
        return None
    return total_seconds / 60


@dataclass(frozen=True)
class Filters:
    """Đúng 7 bộ lọc của `PortView` (giá trị đã ở dạng chuỗi như state React)."""

    q: str = ''
    accepted: str = 'all'  # 'all' | 'yes' | 'no'
    vessel_id: str = ''
    vessel_type_id: str = ''
    date_from: str = ''
    date_to: str = ''
    min_conf_pct: str = ''


@dataclass(frozen=True)
class InvoiceFilters:
    """Đúng 8 bộ lọc của `RevenueView` + trạng thái tab (nguồn tạo) và sub-tab.

    `list_kind`/`invoice_sub_tab` là state của trang (`revenueStore.fetchInvoices`):
    tab thường loại `AI`, tab AI chỉ lấy `AI`; sub-tab `pending` lấy
    `awaiting_payment`, `paid` lấy `payment_status=PAID`, `trash` lấy `deleted_only`.
    """

    list_kind: str = 'standard'  # 'standard' | 'ai'
    invoice_sub_tab: str = 'pending'  # 'pending' | 'paid' | 'trash'
    q: str = ''
    min_berth_minutes: str = ''
    ship_id: str = ''  # `invShipIdFilter` — thực chất là vessel_id
    vessel_type_id: str = ''
    date_from: str = ''
    date_to: str = ''
    min_total: str = ''
    max_total: str = ''


def _text(value: Any) -> str:
    """`String(x ?? '')` của client."""
    return '' if value is None else str(value)


def client_matches(
    row: dict,
    filters: Filters,
    *,
    vessels_by_id: dict[str, dict],
    tz: tzinfo,
) -> bool:
    """Port `PortView.tsx:107-161` — đúng thứ tự và đúng ngữ nghĩa từng bộ lọc."""
    vessel = row.get('vessel') or {}
    if not matches_any_field(
        filters.q,
        get_detection_ship_label(row),
        row.get('track_id'),
        _text(row.get('vessel_id')),
        vessel.get('ship_id'),
    ):
        return False

    if filters.accepted == 'yes' and row.get('is_accepted') is not True:
        return False
    if filters.accepted == 'no' and row.get('is_accepted') is True:
        return False

    # `filterVessels.find(v => String(v.id) === String(det.vessel_id ?? ''))`
    matched_vessel = vessels_by_id.get(_text(row.get('vessel_id')))
    if filters.vessel_id and _text(
        row.get('vessel_id') if row.get('vessel_id') is not None else (matched_vessel or {}).get('id')
    ) != filters.vessel_id:
        return False

    vessel_type = vessel.get('vessel_type_id')
    if vessel_type is None:
        vessel_type = (matched_vessel or {}).get('vessel_type_id')
    if filters.vessel_type_id and _text(vessel_type) != filters.vessel_type_id:
        return False

    display_iso = get_detection_display_time_iso(row)
    if not iso_in_local_date_range(
        _first_not_none(display_iso, row.get('created_at')),
        filters.date_from,
        filters.date_to,
        tz,
    ):
        return False

    if filters.min_conf_pct.strip():
        # Client: `const min = Number(detMinConfPct)`. Giá trị script dùng là số nguyên;
        # chuỗi không phải số (Number → NaN) làm client loại tất cả.
        try:
            minimum = float(filters.min_conf_pct)
        except ValueError:
            return False
        confidence = row.get('confidence')
        percent = (0.0 if confidence is None else float(confidence)) * 100
        if not math.isfinite(minimum) or percent < minimum:
            return False
    return True


def client_side_ids(
    rows: Iterable[dict],
    filters: Filters,
    *,
    vessels_by_id: dict[str, dict],
    tz: tzinfo,
) -> set[int]:
    """Tập id theo logic client (sắp xếp như `PortView` rồi lấy id — so theo tập)."""
    matched = [
        row
        for row in rows
        if client_matches(row, filters, vessels_by_id=vessels_by_id, tz=tz)
    ]
    matched.sort(key=get_detection_sort_ts, reverse=True)  # stable, giống Array.sort của JS
    return {int(row['id']) for row in matched}


def invoice_client_matches(
    row: dict,
    filters: InvoiceFilters,
    *,
    vessels_by_id: dict[str, dict],
    tz: tzinfo,
) -> bool:
    """Port `RevenueView.tsx:168-225` — đúng thứ tự và đúng ngữ nghĩa từng bộ lọc."""
    matched_vessel = vessels_by_id.get(_text(row.get('vessel_id')))
    if not matches_any_field(
        filters.q,
        row.get('invoice_number'),
        _text(row.get('order_id')),
        _first_not_none(row.get('vessel_ship_id'), (matched_vessel or {}).get('ship_id')),
        _text(row.get('vessel_id')),
        _text(row.get('detection_id')),
        _first_not_none(row.get('created_by_label'), ''),
    ):
        return False

    if filters.min_berth_minutes.strip():
        berth_minutes = get_invoice_berth_minutes(row)
        minimum = js_number(filters.min_berth_minutes)
        # Client: `Number(...)` không hữu hạn → `!Number.isFinite(min)` → loại tất cả.
        if minimum is None or berth_minutes is None or berth_minutes < minimum:
            return False

    if filters.ship_id and _text(
        row.get('vessel_id') if row.get('vessel_id') is not None else (matched_vessel or {}).get('id')
    ) != filters.ship_id:
        return False

    if filters.vessel_type_id and _text((matched_vessel or {}).get('vessel_type_id')) != filters.vessel_type_id:
        return False

    if not iso_in_local_date_range(
        row.get('created_at'), filters.date_from, filters.date_to, tz
    ):
        return False

    # Client: `const total = Number(inv.total_amount ?? 0)`; `total < NaN` là false nên
    # một ngưỡng không phải số chỉ là no-op (script chỉ sinh ngưỡng số).
    total = js_number(row.get('total_amount')) or 0.0
    if filters.min_total.strip():
        minimum_total = js_number(filters.min_total)
        if minimum_total is not None and total < minimum_total:
            return False
    if filters.max_total.strip():
        maximum_total = js_number(filters.max_total)
        if maximum_total is not None and total > maximum_total:
            return False
    return True


def invoice_client_side_ids(
    rows: Iterable[dict],
    filters: InvoiceFilters,
    *,
    vessels_by_id: dict[str, dict],
    tz: tzinfo,
) -> set[int]:
    """Tập id theo logic client (so theo tập nên không cần dựng lại thứ tự bảng)."""
    return {
        int(row['id'])
        for row in rows
        if invoice_client_matches(row, filters, vessels_by_id=vessels_by_id, tz=tz)
    }


# --------------------------------------------------------------------------- #
# Phía SQL: gọi endpoint mới, đi hết trang bằng limit=200 + skip
# --------------------------------------------------------------------------- #


def sql_side_params(filters: Filters, tz: tzinfo) -> dict[str, Any]:
    """Quy đổi state của trang bến sang query param của endpoint."""
    params: dict[str, Any] = {}
    if filters.q.strip():
        params['q'] = filters.q.strip()
    if filters.accepted == 'yes':
        params['is_accepted'] = 'true'
    elif filters.accepted == 'no':
        params['is_accepted'] = 'false'
    if filters.vessel_id:
        params['vessel_id'] = filters.vessel_id
    if filters.vessel_type_id:
        params['vessel_type_id'] = filters.vessel_type_id
    if filters.date_from:
        params['occurred_from'] = _local_instant(filters.date_from, tz, end_of_day=False).isoformat()
    if filters.date_to:
        params['occurred_to'] = _local_instant(filters.date_to, tz, end_of_day=True).isoformat()
    if filters.min_conf_pct.strip():
        # Client gửi phần trăm đã chia 100; endpoint nhận 0..1.
        params['min_confidence'] = float(filters.min_conf_pct) / 100
    return params


def invoice_tab_params(filters: InvoiceFilters) -> dict[str, Any]:
    """Param tab/sub-tab — đúng những gì `revenueStore.fetchInvoices` gửi."""
    params: dict[str, Any] = {}
    if filters.list_kind == 'ai':
        params['creation_source'] = 'AI'
    else:
        params['exclude_creation_source'] = 'AI'
    if filters.invoice_sub_tab == 'trash':
        params['deleted_only'] = 'true'
    elif filters.invoice_sub_tab == 'paid':
        params['payment_status'] = 'PAID'
    else:
        params['awaiting_payment'] = 'true'
    return params


def invoice_sql_params(filters: InvoiceFilters, tz: tzinfo) -> dict[str, Any]:
    """Quy đổi state của trang hoá đơn sang query param của endpoint."""
    params = invoice_tab_params(filters)
    if filters.q.strip():
        params['q'] = filters.q.strip()
    if filters.min_berth_minutes.strip():
        params['min_berth_minutes'] = filters.min_berth_minutes.strip()
    if filters.ship_id:
        params['vessel_id'] = filters.ship_id
    if filters.vessel_type_id:
        params['vessel_type_id'] = filters.vessel_type_id
    if filters.date_from:
        params['created_from'] = _local_instant(filters.date_from, tz, end_of_day=False).isoformat()
    if filters.date_to:
        params['created_to'] = _local_instant(filters.date_to, tz, end_of_day=True).isoformat()
    if filters.min_total.strip():
        params['min_total'] = filters.min_total.strip()
    if filters.max_total.strip():
        params['max_total'] = filters.max_total.strip()
    return params


def _local_instant(day: str, tz: tzinfo, *, end_of_day: bool) -> datetime:
    parsed = date.fromisoformat(day)
    hms = (23, 59, 59, 999_000) if end_of_day else (0, 0, 0, 0)
    return datetime(parsed.year, parsed.month, parsed.day, *hms, tzinfo=tz).astimezone(timezone.utc)


def fetch_all_pages(
    client: TestClient, url: str, params: dict[str, Any]
) -> tuple[list[dict], int]:
    """Đi hết các trang `limit=200` + `skip`; trả (rows theo thứ tự, X-Total-Count)."""
    rows: list[dict] = []
    total: Optional[int] = None
    skip = 0
    while True:
        response = client.get(url, params={**params, 'limit': PAGE_SIZE, 'skip': skip})
        if response.status_code != 200:
            raise RuntimeError(f'GET {url} {params} -> {response.status_code}: {response.text[:200]}')
        if total is None:
            raw_total = response.headers.get('X-Total-Count')
            if raw_total is None:
                raise RuntimeError('Thiếu header X-Total-Count')
            total = int(raw_total)
        batch = response.json()
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
        if len(rows) > total:  # chốt an toàn, tránh lặp vô hạn
            break
    ids = [int(item['id']) for item in rows]
    if len(ids) != total:
        raise RuntimeError(
            f'Đi hết trang được {len(ids)} id nhưng X-Total-Count = {total} ({params})'
        )
    if len(set(ids)) != len(ids):
        raise RuntimeError(f'Có id trùng giữa các trang — phân trang không tất định ({params})')
    return rows, total


# --------------------------------------------------------------------------- #
# Chọn giá trị lọc từ chính dữ liệu thật
# --------------------------------------------------------------------------- #


def pick_filter_values(
    rows: list[dict], vessels: list[dict], tz: tzinfo
) -> tuple[dict[str, list[str]], list[str]]:
    """Sinh danh sách giá trị cho từng bộ lọc (luôn có '' = không lọc)."""
    ship_ids = Counter(
        (row.get('vessel') or {}).get('ship_id')
        for row in rows
        if (row.get('vessel') or {}).get('ship_id')
    )
    q_values: list[str] = ['']
    if ship_ids:
        top_ship = ship_ids.most_common(1)[0][0]
        q_values.append(top_ship)
        if top_ship.lower() != top_ship:
            q_values.append(top_ship.lower())  # ILIKE phải không phân biệt hoa thường
    tracks = [row.get('track_id') for row in rows if row.get('track_id')]
    if tracks:
        q_values.append(str(sorted(tracks)[0]))  # khớp đúng 1 row
    # Row không gắn tàu: nhãn hiển thị rơi về id OCR (getDetectionShipLabel).
    for row in rows:
        if not (row.get('vessel') or {}).get('ship_id'):
            items = row.get('ocr_results') or []
            ocr_id = (items[0] or {}).get('id') if items and isinstance(items[0], dict) else None
            if isinstance(ocr_id, str) and ocr_id.strip():
                q_values.append(ocr_id.strip())
                break
    q_values += ['%', '_']  # wildcard của LIKE phải bị escape

    vessel_counts = Counter(_text(row.get('vessel_id')) for row in rows if row.get('vessel_id'))
    vessel_values = [''] + [vid for vid, _ in vessel_counts.most_common(1)]

    type_counts = Counter(
        _text(vessel.get('vessel_type_id')) for vessel in vessels if vessel.get('vessel_type_id')
    )
    type_values = [''] + [tid for tid, _ in type_counts.most_common(1)]

    local_days = sorted(
        {
            parse_api_date(get_detection_display_time_iso(row) or row.get('created_at'))
            .astimezone(tz)
            .date()
            .isoformat()
            for row in rows
            if parse_api_date(get_detection_display_time_iso(row) or row.get('created_at'))
        }
    )
    # Ngày nhỏ nhất / giữa / lớn nhất có dữ liệu: đủ để biên dưới, biên trên và
    # khoảng rỗng đều được chạy qua.
    day_from = [''] + ([local_days[0], local_days[len(local_days) // 2]] if local_days else [])
    day_to = [''] + ([local_days[len(local_days) // 2], local_days[-1]] if local_days else [])

    values = {
        'q': q_values,
        'accepted': ['all', 'yes', 'no'],
        'vessel_id': vessel_values,
        'vessel_type_id': type_values,
        'date_from': day_from,
        'date_to': day_to,
        'min_conf_pct': ['', '90'],
    }
    return values, local_days


def pick_invoice_filter_values(
    rows: list[dict], vessels_by_id: dict[str, dict], tz: tzinfo
) -> tuple[dict[str, list[str]], list[str]]:
    """Sinh danh sách giá trị cho 8 bộ lọc hoá đơn (luôn có '' = không lọc)."""
    q_values: list[str] = ['']
    numbers = sorted(str(row['invoice_number']) for row in rows if row.get('invoice_number'))
    if numbers:
        # Hậu tố của số hoá đơn: khớp đúng row đó mà không phụ thuộc tiền tố dùng chung.
        q_values.append(numbers[0][-6:])
    ship_ids = Counter(
        str(row['vessel_ship_id']) for row in rows if row.get('vessel_ship_id')
    )
    if ship_ids:
        # `vessel_ship_id` của payload (snapshot hoặc ship_id của tàu) nằm trong
        # danh sách trường `matchesAnyField` của client.
        q_values.append(ship_ids.most_common(1)[0][0])
    labels = sorted(
        {str(row['created_by_label']) for row in rows if row.get('created_by_label')}
    )
    if labels:
        q_values.append(labels[0])  # nhãn người tạo — 'AI' với hoá đơn tự động
    q_values.append('%')  # wildcard của LIKE phải bị escape

    vessel_counts = Counter(_text(row.get('vessel_id')) for row in rows if row.get('vessel_id'))
    vessel_values = [''] + [vid for vid, _ in vessel_counts.most_common(1)]

    # Loại tàu lấy từ chính các tàu mà hoá đơn đang tham chiếu (giống `filterVessels`
    # của trang), để giá trị chọn ra chắc chắn có row thật.
    type_counts = Counter(
        _text((vessels_by_id.get(_text(row.get('vessel_id'))) or {}).get('vessel_type_id'))
        for row in rows
        if row.get('vessel_id')
    )
    type_counts.pop('', None)
    type_values = [''] + [tid for tid, _ in type_counts.most_common(1)]

    local_days = sorted(
        {
            parsed.astimezone(tz).date().isoformat()
            for parsed in (parse_api_date(row.get('created_at')) for row in rows)
            if parsed is not None
        }
    )
    day_values = [''] + ([local_days[len(local_days) // 2]] if local_days else [])

    berth_minutes = [
        minutes for minutes in (get_invoice_berth_minutes(row) for row in rows) if minutes is not None
    ]
    totals = [js_number(row.get('total_amount')) or 0.0 for row in rows]

    return {
        'q': q_values,
        'min_berth_minutes': [''] + ([_split_value(berth_minutes)] if berth_minutes else []),
        'ship_id': vessel_values,
        'vessel_type_id': type_values,
        'date_from': day_values,
        'date_to': day_values,
        'min_total': [''] + ([_split_value(totals)] if totals else []),
        'max_total': [''] + ([_split_value(totals)] if totals else []),
    }, local_days


def _split_value(numbers: list[float]) -> str:
    """Giá trị chia tập dữ liệu thành hai phần: chọn từ các giá trị **khác nhau**.

    Lấy trung vị của danh sách gốc có thể ra 0.0 (rất nhiều hoá đơn tổng 0) và biến
    bộ lọc thành no-op; lấy trung vị của các giá trị khác nhau thì cả hai phía đều
    có row, nên tổ hợp kiểm tra được cả nhánh "lọt" lẫn nhánh "bị loại".
    """
    distinct = sorted(set(numbers))
    return str(distinct[len(distinct) // 2])


def build_combinations(values: dict[str, list[str]]) -> list[Filters]:
    keys = list(values)
    return [Filters(**dict(zip(keys, combo))) for combo in product(*(values[key] for key in keys))]


def build_invoice_combinations(values: dict[str, list[str]]) -> list[InvoiceFilters]:
    """Toàn bộ tổ hợp bộ lọc × 6 trạng thái tab (2 nguồn tạo × 3 sub-tab) của trang."""
    keys = list(values)
    combinations: list[InvoiceFilters] = []
    for list_kind in ('standard', 'ai'):
        for invoice_sub_tab in ('pending', 'paid', 'trash'):
            for combo in product(*(values[key] for key in keys)):
                combinations.append(
                    InvoiceFilters(
                        list_kind=list_kind,
                        invoice_sub_tab=invoice_sub_tab,
                        **dict(zip(keys, combo)),
                    )
                )
    return combinations


# --------------------------------------------------------------------------- #
# Chạy từng nhóm
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Mismatch:
    """Một tổ hợp lệch giữa hai phía."""

    group: str
    filters: str
    only_client: list[int]
    only_sql: list[int]


def run_detections(
    client: TestClient,
    vessels: list[dict],
    vessels_by_id: dict[str, dict],
    tz_name: str,
    tz: tzinfo,
    *,
    progress_every: int,
) -> tuple[int, list[Mismatch]]:
    """Nhóm 7 bộ lọc của trang bến."""
    rows, total = fetch_all_pages(client, DETECTION_LIST_URL, {})
    values, local_days = pick_filter_values(rows, vessels, tz)
    combinations = build_combinations(values)

    print('=== Nhóm bến: 7 bộ lọc của /detections/ ===')
    print(f'Dữ liệu thật: {len(rows)} detection (X-Total-Count={total}), {len(vessels)} vessel')
    print(f'Timezone lọc ngày: {tz_name} · ngày có dữ liệu: {local_days[:1]}…{local_days[-1:]}')
    for key, items in values.items():
        print(f'  {key}: {items}')
    print(f'Tổ hợp chạy: {len(combinations)}')

    mismatches: list[Mismatch] = []
    for index, filters in enumerate(combinations, start=1):
        expected = client_side_ids(rows, filters, vessels_by_id=vessels_by_id, tz=tz)
        sql_rows, _ = fetch_all_pages(client, DETECTION_LIST_URL, sql_side_params(filters, tz))
        actual = {int(item['id']) for item in sql_rows}
        if expected != actual:
            mismatches.append(
                Mismatch(
                    group='bến',
                    filters=_describe(filters),
                    only_client=sorted(expected - actual)[:20],
                    only_sql=sorted(actual - expected)[:20],
                )
            )
        if progress_every and index % progress_every == 0:
            print(f'  … {index}/{len(combinations)} tổ hợp, lệch {len(mismatches)}')
    print(f'Đã chạy: {len(combinations)} tổ hợp · lệch {len(mismatches)}\n')
    return len(combinations), mismatches


def run_invoices(
    client: TestClient,
    vessels_by_id: dict[str, dict],
    tz_name: str,
    tz: tzinfo,
    *,
    progress_every: int,
) -> tuple[int, list[Mismatch]]:
    """Nhóm 8 bộ lọc của trang hoá đơn (mỗi trạng thái tab là một tập row của client)."""
    print('=== Nhóm hoá đơn: 8 bộ lọc của /invoices/ ===')
    # `filterVessels` của trang: danh sách tàu cho dropdown, lọc theo id + loại tàu.
    baselines: dict[tuple[str, str], list[dict]] = {}
    for list_kind in ('standard', 'ai'):
        for invoice_sub_tab in ('pending', 'paid', 'trash'):
            state = InvoiceFilters(list_kind=list_kind, invoice_sub_tab=invoice_sub_tab)
            rows, total = fetch_all_pages(client, INVOICE_LIST_URL, invoice_tab_params(state))
            baselines[(list_kind, invoice_sub_tab)] = rows
            print(
                f'  tab {list_kind}/{invoice_sub_tab}: {len(rows)} invoice '
                f'(X-Total-Count={total})'
            )

    reference_rows = [row for rows in baselines.values() for row in rows]
    values, local_days = pick_invoice_filter_values(reference_rows, vessels_by_id, tz)
    filter_count = math.prod(len(items) for items in values.values())
    combinations = build_invoice_combinations(values)

    print(f'Timezone lọc ngày: {tz_name} · ngày có dữ liệu: {local_days[:1]}…{local_days[-1:]}')
    for key, items in values.items():
        print(f'  {key}: {items}')
    print(
        f'Tổ hợp chạy: {len(combinations)} '
        f'(6 trạng thái tab × {filter_count} tổ hợp bộ lọc)'
    )

    mismatches: list[Mismatch] = []
    for index, filters in enumerate(combinations, start=1):
        rows = baselines[(filters.list_kind, filters.invoice_sub_tab)]
        expected = invoice_client_side_ids(rows, filters, vessels_by_id=vessels_by_id, tz=tz)
        sql_rows, _ = fetch_all_pages(client, INVOICE_LIST_URL, invoice_sql_params(filters, tz))
        actual = {int(item['id']) for item in sql_rows}
        if expected != actual:
            mismatches.append(
                Mismatch(
                    group='hoá đơn',
                    filters=_describe(filters),
                    only_client=sorted(expected - actual)[:20],
                    only_sql=sorted(actual - expected)[:20],
                )
            )
        if progress_every and index % progress_every == 0:
            print(f'  … {index}/{len(combinations)} tổ hợp, lệch {len(mismatches)}')
    print(f'Đã chạy: {len(combinations)} tổ hợp · lệch {len(mismatches)}\n')
    return len(combinations), mismatches


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def machine_timezone() -> tuple[str, tzinfo]:
    """Timezone của máy: $TZ, rồi /etc/localtime; cuối cùng là offset hiện tại."""
    env_tz = os.environ.get('TZ')
    if env_tz:
        return env_tz, ZoneInfo(env_tz)
    try:
        name = str(Path('/etc/localtime').resolve()).split('zoneinfo/', 1)[1]
        return name, ZoneInfo(name)
    except Exception:
        current = datetime.now().astimezone().tzinfo or timezone.utc
        return str(current), current


def resolve_timezone(name: Optional[str]) -> tuple[str, tzinfo]:
    if not name:
        return machine_timezone()
    try:
        return name, ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001 - báo lỗi rõ ràng cho người chạy
        raise SystemExit(f'--tz không hợp lệ: {name} ({exc})') from exc


def _describe(filters: Any) -> str:
    return ' '.join(f'{key}={value!r}' for key, value in vars(filters).items())


def run(tz_name: str, tz: tzinfo, *, progress_every: int = 250) -> int:
    session = SessionLocal()
    combinations_run = 0
    mismatches: list[Mismatch] = []
    try:
        # Chốt cứng: mọi truy vấn trong script (kể cả của endpoint) là READ ONLY.
        session.execute(text('SET TRANSACTION READ ONLY'))
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, is_active=True)
        # không dùng context manager: bỏ qua lifespan (không bật pipeline/GPU)
        client = TestClient(app)
        try:
            # `filterVessels` của useFilterOptions: chỉ cần id + vessel_type_id. Đọc
            # thẳng từ DB để script không phụ thuộc Qdrant/MinIO như endpoint vessels.
            vessels = [
                {'id': vid, 'vessel_type_id': vtype}
                for vid, vtype in session.execute(
                    select(Vessel.id, Vessel.vessel_type_id)
                ).all()
            ]
            vessels_by_id = {str(vessel['id']): vessel for vessel in vessels}

            detection_combos, detection_mismatches = run_detections(
                client, vessels, vessels_by_id, tz_name, tz, progress_every=progress_every
            )
            invoice_combos, invoice_mismatches = run_invoices(
                client, vessels_by_id, tz_name, tz, progress_every=progress_every
            )
            combinations_run = detection_combos + invoice_combos
            mismatches = detection_mismatches + invoice_mismatches
        finally:
            client.close()
    finally:
        session.rollback()
        session.close()
        app.dependency_overrides.clear()

    if mismatches:
        print(f'\nLệch: {len(mismatches)} tổ hợp / {combinations_run}')
        for mismatch in mismatches[:10]:
            print(f'  ✗ [{mismatch.group}] {mismatch.filters}')
            print(f'      chỉ có ở client: {mismatch.only_client}')
            print(f'      chỉ có ở SQL   : {mismatch.only_sql}')
        if len(mismatches) > 10:
            print(f'  … còn {len(mismatches) - 10} tổ hợp lệch khác')
        print(f'Lệch: {len(mismatches)} tổ hợp · ✗ KHÔNG ĐẠT')
        return 1

    print(f'Đã chạy: {combinations_run} tổ hợp')
    print(f'Lệch: 0 tổ hợp · ✓ ĐẠT')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--tz',
        default=None,
        help='Timezone để quy đổi ngày địa phương (mặc định: timezone của máy)',
    )
    args = parser.parse_args()
    logging.disable(logging.INFO)  # tắt log access của app cho output sạch
    tz_name, tz = resolve_timezone(args.tz)
    return run(tz_name, tz)


if __name__ == '__main__':
    raise SystemExit(main())

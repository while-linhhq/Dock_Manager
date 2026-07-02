# IN/OUT Dedup — Deferred Write Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đảm bảo mỗi `GlobalIdentity` chỉ ghi tối đa 1 event IN + 1 event OUT bằng cách chuyển sang deferred write — ghi DB duy nhất tại `_finalize_identity_locked`.

**Architecture:** Bỏ gọi `record_boundary_crossing_event()` trong `report_boundary_crossing()`. Thêm cờ `events_written: bool` vào `GlobalIdentity` để chặn double-insert khi finalize chạy 2 lần (anchor release + flush expired). Thêm last-chance merge (C1) trước khi finalize để gom identity lẽ ra phải merge. `_finalize_identity_locked` là điểm ghi DB duy nhất.

**Tech Stack:** Python, SQLAlchemy, pytest, `cross_camera_reid.py`, `boundary_crossing_event_service.py`.

---

## Files

- Modify: `server/app/services/ai/cross_camera_reid.py` — bỏ ghi DB lúc crossing, thêm `events_written`, thêm last-chance merge, ghi event tại finalize.
- Test: `server/app/tests/test_inout_dedup.py` — tất cả test cases Phần 1.

---

### Task 1: Viết failing tests cho deferred write + events_written guard

**Files:**
- Create: `server/app/tests/test_inout_dedup.py`

- [ ] **Step 1: Tạo file test**

```python
"""Tests for IN/OUT dedup — deferred write via _finalize_identity_locked."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import numpy as np
import pytest

from app.services.ai.cross_camera_reid import CrossCameraReIdManager, GlobalIdentity


def _manager(camera_order: list[int] | None = None) -> CrossCameraReIdManager:
    recorded: list[tuple] = []

    def on_removed(track, history):
        recorded.append((track, history))

    mgr = CrossCameraReIdManager(
        camera_order=camera_order or [1, 2],
        visual_threshold=0.6,
        handoff_window_sec=5.0,
        on_global_track_removed=on_removed,
    )
    mgr._recorded = recorded
    return mgr


def _fake_track(track_id: str = 't1', camera_id: int = 1, ship_id: str | None = None):
    import numpy as np
    from app.services.ai.boat_tracker import TrackedBoat, TrackState
    return TrackedBoat(
        track_id=track_id,
        state=TrackState.CONFIRMED,
        box=np.array([10, 10, 50, 50], dtype=np.float32),
        conf=0.9,
        hits=3,
        misses=0,
        first_seen_ts=1.0,
        last_seen_ts=2.0,
        ship_id=ship_id,
        camera_id=camera_id,
        ever_confirmed=True,
    )


def test_two_cameras_merge_then_finalize_writes_one_in_one_out():
    """2 GlobalIdentity từ 2 cam → merge → finalize → đúng 1 IN + 1 OUT event."""
    mgr = _manager()
    track1 = _fake_track('t1', 1)
    track2 = _fake_track('t2', 2)

    mgr.report_track_update(1, track1, embedding=None, frame_shape=None)
    mgr.report_track_update(2, track2, embedding=None, frame_shape=None)

    # Ghi crossing trên cam 1 → IN
    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    # Ghi crossing trên cam 2 → IN lần nữa (nếu chưa merge = double IN bug cũ)
    mgr.report_boundary_crossing(2, 't2', 'in', 101.0)
    # OUT trên cam 2
    mgr.report_boundary_crossing(2, 't2', 'out', 200.0)

    # Merge 2 identity lại (simulate OCR match)
    gid1 = mgr.get_global_id(1, 't1')
    gid2 = mgr.get_global_id(2, 't2')
    if gid1 and gid2 and gid1 != gid2:
        with mgr._lock:
            id1 = mgr._identities.get(gid1)
            id2 = mgr._identities.get(gid2)
            if id1 and id2:
                mgr._merge_identities(id1, id2)

    mgr.flush_all()

    # Đếm IN/OUT từ on_global_track_removed callback
    in_count = sum(
        1 for (track, _) in mgr._recorded
        if getattr(track, 'berth_in_ts', None) is not None
    )
    out_count = sum(
        1 for (track, _) in mgr._recorded
        if getattr(track, 'berth_out_ts', None) is not None
    )
    assert in_count == 1, f'Expected 1 IN, got {in_count}'
    assert out_count == 1, f'Expected 1 OUT, got {out_count}'


def test_only_in_no_out_finalize_writes_in_only():
    """Tàu chỉ IN chưa OUT → finalize ghi IN, không OUT."""
    mgr = _manager()
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)
    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    mgr.flush_all()

    assert len(mgr._recorded) == 1
    track_out, _ = mgr._recorded[0]
    assert track_out.berth_in_ts == 100.0
    assert track_out.berth_out_ts is None


def test_events_written_guard_prevents_double_finalize():
    """Double finalize (anchor release + flush) → events_written chặn → không double row."""
    mgr = _manager()
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)
    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)

    gid = mgr.get_global_id(1, 't1')
    assert gid is not None

    # Finalize lần 1 (anchor release)
    with mgr._lock:
        identity = mgr._identities.get(gid)
        assert identity is not None
        mgr._finalize_identity_locked(identity)

    # Finalize lần 2 (flush expired) — phải bị chặn bởi events_written
    with mgr._lock:
        identity = mgr._identities.get(gid)
        if identity is not None:
            mgr._finalize_identity_locked(identity)

    assert len(mgr._recorded) == 1, f'Expected 1 callback, got {len(mgr._recorded)}'


def test_berth_out_before_in_sanity_still_writes():
    """berth_out_ts < berth_in_ts → log cảnh báo, vẫn ghi theo ts thực."""
    mgr = _manager()
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)
    mgr.report_boundary_crossing(1, 't1', 'in', 200.0)
    mgr.report_boundary_crossing(1, 't1', 'out', 100.0)  # out < in
    mgr.flush_all()

    assert len(mgr._recorded) == 1
    track_out, _ = mgr._recorded[0]
    assert track_out.berth_in_ts == 200.0
    assert track_out.berth_out_ts == 100.0  # ghi đúng ts, không normalize


def test_no_db_write_during_report_boundary_crossing():
    """report_boundary_crossing không ghi DB trực tiếp nữa — chỉ cập nhật state."""
    import unittest.mock as mock
    with mock.patch(
        'app.services.ai.cross_camera_reid.record_boundary_crossing_event'
    ) as mock_record:
        mgr = _manager()
        track = _fake_track('t1', 1)
        mgr.report_track_update(1, track, embedding=None, frame_shape=None)
        mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
        mgr.report_boundary_crossing(1, 't1', 'out', 200.0)
        mock_record.assert_not_called()
```

- [ ] **Step 2: Chạy RED**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
pytest server/app/tests/test_inout_dedup.py -v 2>&1 | head -40
```

Expected: ImportError hoặc `assert len(mgr._recorded) == 1` fail vì hiện tại `report_boundary_crossing` vẫn ghi DB ngay.

- [ ] **Step 3: Commit test**

```bash
git add server/app/tests/test_inout_dedup.py
git commit -m "test(reid): add failing IN/OUT dedup tests"
```

---

### Task 2: Thêm `events_written` vào `GlobalIdentity` và bỏ ghi DB lúc crossing

**Files:**
- Modify: `server/app/services/ai/cross_camera_reid.py:29-46` (GlobalIdentity dataclass)
- Modify: `server/app/services/ai/cross_camera_reid.py:311-347` (report_boundary_crossing)

- [ ] **Step 1: Thêm field `events_written` vào `GlobalIdentity`**

Tìm dataclass `GlobalIdentity` (dòng ~29), thêm field cuối:

```python
@dataclass
class GlobalIdentity:
    global_id: str
    ship_id: str | None
    camera_tracks: dict[int, str]
    embeddings: list[np.ndarray] = field(default_factory=list)
    ocr_history: list[tuple[str, float]] = field(default_factory=list)
    ocr_confirmed_tracks: set[TrackKey] = field(default_factory=set)
    first_seen_ts: float = 0.0
    last_seen_ts: float = 0.0
    primary_camera_id: int | None = None
    active_tracks: set[TrackKey] = field(default_factory=set)
    removed_tracks: set[TrackKey] = field(default_factory=set)
    last_track: TrackedBoat | None = None
    finalized: bool = False
    anchored: bool = False
    berth_in_ts: float | None = None
    berth_out_ts: float | None = None
    events_written: bool = False          # ← thêm dòng này
```

- [ ] **Step 2: Bỏ ghi DB trong `report_boundary_crossing`**

Tìm method `report_boundary_crossing` (~dòng 311). Xóa toàn bộ block `if not should_record: return` và `record_boundary_crossing_event(...)`. Kết quả sau khi sửa:

```python
def report_boundary_crossing(
    self, camera_id: int, track_id: str, direction: str, ts: float
) -> None:
    with self._lock:
        key = (int(camera_id), str(track_id))
        identity = self._identity_for_track(key)
        if identity is None:
            identity = self._create_empty_identity(int(camera_id), str(track_id))
            self._track_to_global[key] = identity.global_id
        if direction == 'in':
            if identity.berth_in_ts is None:
                identity.berth_in_ts = ts
            elif ts < identity.berth_in_ts:
                identity.berth_in_ts = ts
        elif direction == 'out':
            if identity.berth_in_ts is not None and identity.berth_out_ts is None:
                identity.berth_out_ts = ts
            elif (
                identity.berth_in_ts is not None
                and identity.berth_out_ts is not None
                and ts > identity.berth_out_ts
            ):
                identity.berth_out_ts = ts
```

- [ ] **Step 3: Chạy test**

```bash
pytest server/app/tests/test_inout_dedup.py::test_no_db_write_during_report_boundary_crossing -v
```

Expected: PASS.

---

### Task 3: Ghi event tại `_finalize_identity_locked` với `events_written` guard

**Files:**
- Modify: `server/app/services/ai/cross_camera_reid.py:688-701` (_finalize_identity_locked)

- [ ] **Step 1: Sửa `_finalize_identity_locked` để ghi event IN/OUT tại đây**

```python
def _finalize_identity_locked(self, identity: GlobalIdentity) -> None:
    if identity.finalized:
        return
    identity.finalized = True

    # Last-chance merge (C1): trước khi ghi, gom identity khác có cùng ship_id
    # chưa finalize — tránh ghi 2 lần cho cùng 1 tàu
    if identity.ship_id:
        for other in list(self._identities.values()):
            if other is identity or other.finalized:
                continue
            if other.ship_id == identity.ship_id and not other.active_tracks:
                identity = self._merge_identities(identity, other)

    # Ghi event IN/OUT một lần duy nhất
    if not identity.events_written:
        identity.events_written = True
        self._write_boundary_events_locked(identity)

    if self._on_global_track_removed is None or identity.last_track is None:
        return
    track = identity.last_track.copy_public()
    track.track_id = identity.global_id
    track.ship_id = identity.ship_id or track.ship_id or 'UNKNOWN'
    track.last_known_ship_id = track.ship_id
    track.berth_in_ts = identity.berth_in_ts
    track.berth_out_ts = identity.berth_out_ts
    history = list(identity.ocr_history)
    self._on_global_track_removed(track, history)
```

- [ ] **Step 2: Thêm helper `_write_boundary_events_locked`**

Thêm method mới ngay sau `_finalize_identity_locked`:

```python
def _write_boundary_events_locked(self, identity: GlobalIdentity) -> None:
    """Ghi event IN và/hoặc OUT vào DB — chỉ gọi 1 lần từ _finalize_identity_locked."""
    from app.services.boundary_crossing_event_service import record_boundary_crossing_event

    if identity.berth_in_ts is not None and identity.berth_out_ts is not None:
        if identity.berth_out_ts < identity.berth_in_ts:
            _log.warning(
                'reid: identity %s berth_out_ts %.1f < berth_in_ts %.1f — writing as-is',
                identity.global_id,
                identity.berth_out_ts,
                identity.berth_in_ts,
            )

    camera_id = identity.primary_camera_id or next(iter(identity.camera_tracks), 0)
    track_id = identity.global_id

    if identity.berth_in_ts is not None:
        record_boundary_crossing_event(
            camera_id=int(camera_id),
            track_id=str(track_id),
            direction='in',
            crossed_at_ts=float(identity.berth_in_ts),
            ship_id=identity.ship_id,
        )
    if identity.berth_out_ts is not None:
        record_boundary_crossing_event(
            camera_id=int(camera_id),
            track_id=str(track_id),
            direction='out',
            crossed_at_ts=float(identity.berth_out_ts),
            ship_id=identity.ship_id,
        )
```

- [ ] **Step 3: Chạy full test suite**

```bash
pytest server/app/tests/test_inout_dedup.py -v
```

Expected: tất cả 5 test PASS.

- [ ] **Step 4: Commit**

```bash
git add server/app/services/ai/cross_camera_reid.py
git commit -m "feat(reid): deferred IN/OUT write — single event per GlobalIdentity at finalize"
```

---

### Task 4: Integration test — không double-insert khi merge sau crossing

**Files:**
- Modify: `server/app/tests/test_inout_dedup.py`

- [ ] **Step 1: Thêm test C1 last-chance merge**

Append vào `test_inout_dedup.py`:

```python
def test_last_chance_merge_before_finalize_prevents_double_in():
    """C1: 2 identity cùng ship_id inactive → last-chance merge → 1 IN duy nhất."""
    recorded = []
    mgr = CrossCameraReIdManager(
        camera_order=[1, 2],
        visual_threshold=0.6,
        handoff_window_sec=5.0,
        on_global_track_removed=lambda t, h: recorded.append((t, h)),
    )
    track1 = _fake_track('t1', 1, ship_id='BD-0001')
    track2 = _fake_track('t2', 2, ship_id='BD-0001')
    mgr.report_track_update(1, track1, embedding=None, frame_shape=None)
    mgr.report_track_update(2, track2, embedding=None, frame_shape=None)

    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    mgr.report_boundary_crossing(2, 't2', 'in', 101.0)

    # Cả 2 track removed (tàu đi hết)
    mgr.report_track_removed(1, track1, [])
    mgr.report_track_removed(2, track2, [])

    mgr.flush_all()

    # last-chance merge gom 2 identity cùng ship_id → 1 finalize → 1 IN
    in_events = [t for t, _ in recorded if t.berth_in_ts is not None]
    assert len(in_events) == 1, f'Expected 1 IN event, got {len(in_events)}'
```

- [ ] **Step 2: Chạy**

```bash
pytest server/app/tests/test_inout_dedup.py -v
```

Expected: 6/6 PASS. (Last-chance merge test có thể cần điều chỉnh tùy logic `_may_merge_identities` — nếu fail do mock không đủ, xem ghi chú bên dưới.)

> **Ghi chú:** Test `test_last_chance_merge_before_finalize_prevents_double_in` dựa vào `_finalize_identity_locked` gom identity cùng `ship_id`. Nếu identity vẫn còn `active_tracks` lúc `flush_all`, last-chance merge không xảy ra. Test dùng `report_track_removed` để clear `active_tracks` trước.

- [ ] **Step 3: Commit**

```bash
git add server/app/tests/test_inout_dedup.py
git commit -m "test(reid): add last-chance merge C1 test for IN/OUT dedup"
```

---

### Task 5: Chạy full regression suite

- [ ] **Step 1: Chạy tất cả test liên quan**

```bash
pytest server/app/tests/test_inout_dedup.py server/app/tests/test_ship_id_lock.py server/app/tests/test_ship_id_evidence.py server/app/tests/test_zone_gated_vote.py -v
```

Expected: tất cả pass.

- [ ] **Step 2: Commit cuối**

```bash
git add -p
git commit -m "feat(reid): complete IN/OUT dedup — deferred write, events_written guard, C1 last-chance merge"
```

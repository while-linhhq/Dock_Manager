"""Tests for IN/OUT dedup — deferred write via _finalize_identity_locked."""
from __future__ import annotations

import sys
import types
import unittest.mock as mock
import numpy as np
import pytest

# boundary_crossing_event_service imports sqlalchemy at module level, which is not
# available in the test environment.  Stub the whole module in sys.modules before
# anything else imports it, so mock.patch can resolve the target without crashing.
_stub_mod = types.ModuleType('app.services.boundary_crossing_event_service')
_stub_mod.record_boundary_crossing_event = mock.MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault('app.services.boundary_crossing_event_service', _stub_mod)

from app.services.ai.cross_camera_reid import CrossCameraReIdManager, GlobalIdentity  # noqa: E402


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
    """2 GlobalIdentity từ 2 cam → merge → finalize → đúng 1 IN + 1 OUT event.

    RED reason: currently report_boundary_crossing calls record_boundary_crossing_event
    immediately (2 direct writes for 2 identities).  After the fix, writes happen only
    at _finalize_identity_locked on the merged identity → exactly 1 call total.
    """
    _stub_mod.record_boundary_crossing_event.reset_mock()  # type: ignore[attr-defined]
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

    # No DB writes should happen during crossing — only state updates
    _stub_mod.record_boundary_crossing_event.assert_not_called()  # type: ignore[attr-defined]

    # Merge 2 identity lại (simulate OCR match)
    gid1 = mgr.get_global_id(1, 't1')
    gid2 = mgr.get_global_id(2, 't2')
    assert gid1 is not None, 'track1 not registered with manager'
    assert gid2 is not None, 'track2 not registered with manager'
    if gid1 != gid2:
        with mgr._lock:
            id1 = mgr._identities.get(gid1)
            id2 = mgr._identities.get(gid2)
            if id1 and id2:
                mgr._merge_identities(id1, id2)

    mgr.flush_all()

    # _finalize_identity_locked copies identity.berth_in_ts / berth_out_ts onto
    # the track object it passes to on_global_track_removed (lines 698-699 of
    # cross_camera_reid.py), so checking track.berth_in_ts here is correct.
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
    """Tàu chỉ IN chưa OUT → finalize ghi IN, không OUT.

    RED reason: currently report_boundary_crossing writes to DB immediately.
    After the fix, no DB write happens during crossing — only at finalize.
    """
    _stub_mod.record_boundary_crossing_event.reset_mock()  # type: ignore[attr-defined]
    mgr = _manager()
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)
    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    # Must NOT write DB during crossing
    _stub_mod.record_boundary_crossing_event.assert_not_called()  # type: ignore[attr-defined]
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

    # Grab a reference before finalize — finalize may remove the identity from
    # _identities, so a second dict lookup would return None and silently skip the guard.
    with mgr._lock:
        identity = mgr._identities.get(gid)
    assert identity is not None

    # Finalize lần 1 (anchor release)
    with mgr._lock:
        mgr._finalize_identity_locked(identity)

    # Finalize lần 2 (flush expired) — same object reference, must be blocked by events_written
    with mgr._lock:
        mgr._finalize_identity_locked(identity)

    # events_written must exist and be True — AttributeError here until field is added
    assert identity.events_written is True  # type: ignore[attr-defined]
    assert len(mgr._recorded) == 1, f'Expected 1 callback, got {len(mgr._recorded)}'


def test_berth_out_before_in_sanity_still_writes():
    """berth_out_ts < berth_in_ts → log warning, still writes actual ts at finalize."""
    _stub_mod.record_boundary_crossing_event.reset_mock()  # type: ignore[attr-defined]
    mgr = _manager()
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)
    mgr.report_boundary_crossing(1, 't1', 'in', 200.0)
    mgr.report_boundary_crossing(1, 't1', 'out', 100.0)  # out < in
    # Should NOT write DB during crossing (deferred write is the goal)
    _stub_mod.record_boundary_crossing_event.assert_not_called()  # type: ignore[attr-defined]
    mgr.flush_all()

    assert len(mgr._recorded) == 1
    track_out, _ = mgr._recorded[0]
    assert track_out.berth_in_ts == 200.0
    assert track_out.berth_out_ts == 100.0  # writes actual ts, no normalization


def test_no_db_write_during_report_boundary_crossing():
    """report_boundary_crossing không ghi DB trực tiếp nữa — chỉ cập nhật state."""
    _stub_mod.record_boundary_crossing_event.reset_mock()  # type: ignore[attr-defined]
    mgr = _manager()
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)
    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    mgr.report_boundary_crossing(1, 't1', 'out', 200.0)
    _stub_mod.record_boundary_crossing_event.assert_not_called()  # type: ignore[attr-defined]

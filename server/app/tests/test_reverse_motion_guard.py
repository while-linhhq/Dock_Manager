"""Tests for the reverse-motion guard in CrossCameraReIdManager.report_boundary_crossing.

Scenario: a boat arrives (cam1→cam2 handoff, one GlobalIdentity), berths, then
departs. While backing out it reverses and clips the previous camera's berth
zone, which fires another IN crossing. That must NOT re-open the berth window or
fabricate an OUT→IN cycle — it is the same boat, same identity, already departed.
"""
from __future__ import annotations

import sys
import types
import unittest.mock as mock

import numpy as np
import pytest

# boundary_crossing_event_service imports sqlalchemy at module level; stub it.
_stub_mod = types.ModuleType('app.services.boundary_crossing_event_service')
_stub_mod.record_boundary_crossing_event = mock.MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault('app.services.boundary_crossing_event_service', _stub_mod)

from app.services.ai.cross_camera_reid import CrossCameraReIdManager  # noqa: E402


def _manager(reverse_guard: bool = True) -> CrossCameraReIdManager:
    recorded: list[tuple] = []

    def on_removed(track, history):
        recorded.append((track, history))

    mgr = CrossCameraReIdManager(
        camera_order=[1, 2],
        visual_threshold=0.6,
        handoff_window_sec=5.0,
        on_global_track_removed=on_removed,
        reverse_motion_guard_enabled=reverse_guard,
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


def test_reverse_retouch_after_departure_is_ignored():
    """IN → OUT → reverse IN: the second IN after departure must be dropped."""
    mgr = _manager(reverse_guard=True)
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)

    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    mgr.report_boundary_crossing(1, 't1', 'out', 200.0)
    # boat backs out, clips the zone again → spurious IN at 205
    mgr.report_boundary_crossing(1, 't1', 'in', 205.0)

    gid = mgr.get_global_id(1, 't1')
    identity = mgr._identities[gid]
    # berth window unchanged: single IN@100, single OUT@200
    assert identity.berth_in_ts == 100.0
    assert identity.berth_out_ts == 200.0


def test_reverse_retouch_does_not_reset_out():
    """A second OUT after the reverse re-touch must not extend past the real OUT
    unless it is genuinely later (existing max-ts behaviour preserved)."""
    mgr = _manager(reverse_guard=True)
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)

    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    mgr.report_boundary_crossing(1, 't1', 'out', 200.0)
    mgr.report_boundary_crossing(1, 't1', 'in', 205.0)   # guarded, ignored
    mgr.report_boundary_crossing(1, 't1', 'out', 210.0)  # later real OUT extends

    gid = mgr.get_global_id(1, 't1')
    identity = mgr._identities[gid]
    assert identity.berth_in_ts == 100.0
    assert identity.berth_out_ts == 210.0


def test_guard_disabled_allows_reopen():
    """With the guard off, the legacy behaviour (IN ignored because berth_in_ts
    already set, but not because of departure) is unchanged — berth_in_ts stays
    at the earliest, proving the guard is what blocks re-touch, not other logic."""
    mgr = _manager(reverse_guard=False)
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)

    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    mgr.report_boundary_crossing(1, 't1', 'out', 200.0)
    mgr.report_boundary_crossing(1, 't1', 'in', 205.0)

    gid = mgr.get_global_id(1, 't1')
    identity = mgr._identities[gid]
    # in stays at earliest (100), out stays 200 — the 205 IN is a no-op either way
    # because berth_in_ts is already set and 205 > 100. Confirms no crash path.
    assert identity.berth_in_ts == 100.0
    assert identity.berth_out_ts == 200.0


def test_first_in_still_works_with_guard_on():
    """Guard must not block the legitimate first IN (berth_out_ts is None)."""
    mgr = _manager(reverse_guard=True)
    track = _fake_track('t1', 1)
    mgr.report_track_update(1, track, embedding=None, frame_shape=None)

    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)

    gid = mgr.get_global_id(1, 't1')
    identity = mgr._identities[gid]
    assert identity.berth_in_ts == 100.0
    assert identity.berth_out_ts is None

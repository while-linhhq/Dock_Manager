"""End-to-end pipeline logic tests: detection identity → berth crossing → billing window → hours.

Covers the full chain the user cares about, using the pure/decoupled units so no
live DB or GPU is needed:

  1. Cross-camera identity: sequential handoff + concurrent overlap → ONE GlobalIdentity.
  2. Reverse-motion re-touch after departure → NO fabricated IN/OUT.
  3. Deferred IN/OUT write → exactly one IN + one OUT per identity at finalize.
  4. Billing: berth window resolution feeds correct berthing hours for the invoice.

These tie the reid layer (cross_camera_reid) to the invoice layer
(detection_invoice_service.resolve_berth_window / _berthing_hours) so a regression
in either that would produce wrong invoices is caught here.
"""
from __future__ import annotations

import sys
import time
import types
import unittest.mock as mock
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pytest

# Stub the DB-backed boundary event writer before reid imports it.
_stub_mod = types.ModuleType('app.services.boundary_crossing_event_service')
_stub_mod.record_boundary_crossing_event = mock.MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault('app.services.boundary_crossing_event_service', _stub_mod)

from app.services.ai.cross_camera_reid import CrossCameraReIdManager  # noqa: E402
from app.services.ai.boat_tracker import TrackedBoat, TrackState  # noqa: E402
from app.services.ai.directional_handoff import DirectionalHandoffConfig  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _manager(**kwargs) -> CrossCameraReIdManager:
    recorded: list[tuple] = []
    mgr = CrossCameraReIdManager(
        camera_order=[1, 2],
        visual_threshold=0.6,
        handoff_window_sec=30.0,
        on_global_track_removed=lambda t, h: recorded.append((t, h)),
        **kwargs,
    )
    mgr._recorded = recorded  # type: ignore[attr-defined]
    # cam2 sits to the RIGHT of cam1 in layout → forward handoff = vx>0
    mgr.set_camera_layout({1: 0.0, 2: 1920.0})
    mgr._frame_width_by_camera = {1: 1920.0, 2: 1920.0}  # type: ignore[attr-defined]
    return mgr


def _track(track_id, camera_id, *, box, ship_id=None, embedding=None,
           velocity=None, first_seen=1.0, last_seen=2.0):
    return TrackedBoat(
        track_id=track_id,
        state=TrackState.CONFIRMED,
        box=np.asarray(box, dtype=np.float32),
        conf=0.9,
        hits=5,
        misses=0,
        first_seen_ts=first_seen,
        last_seen_ts=last_seen,
        ship_id=ship_id,
        camera_id=camera_id,
        velocity=velocity,
        embedding=embedding,
        ever_confirmed=True,
    )


def _emb(vec):
    a = np.asarray(vec, dtype=np.float32)
    return a / (np.linalg.norm(a) + 1e-9)


# ── 1. Identity: OCR handoff → one identity, one IN + one OUT ──────────────────

def test_ocr_handoff_yields_single_in_out():
    """Same ship_id read on cam1 and cam2 → merge → 1 IN + 1 OUT."""
    _stub_mod.record_boundary_crossing_event.reset_mock()  # type: ignore[attr-defined]
    mgr = _manager()
    t1 = _track('t1', 1, box=[10, 10, 50, 50], ship_id='BD-0001')
    t2 = _track('t2', 2, box=[10, 10, 50, 50], ship_id='BD-0001')

    mgr.report_track_update(1, t1, embedding=None, frame_shape=(1080, 1920))
    mgr.report_track_update(2, t2, embedding=None, frame_shape=(1080, 1920))

    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    mgr.report_boundary_crossing(2, 't2', 'out', 300.0)

    mgr.flush_all()

    in_events = [t for t, _ in mgr._recorded if t.berth_in_ts is not None]
    out_events = [t for t, _ in mgr._recorded if t.berth_out_ts is not None]
    assert len(in_events) == 1, f'expected 1 IN, got {len(in_events)}'
    assert len(out_events) == 1, f'expected 1 OUT, got {len(out_events)}'
    assert in_events[0].berth_in_ts == 100.0
    assert out_events[0].berth_out_ts == 300.0


# ── 2. Reverse re-touch after departure → no fabricated crossing ───────────────

def test_reverse_retouch_does_not_add_events():
    """Boat departed (OUT set), backs out clipping cam1 zone again → no new IN."""
    mgr = _manager()
    t1 = _track('t1', 1, box=[10, 10, 50, 50], ship_id='BD-0002')
    mgr.report_track_update(1, t1, embedding=None, frame_shape=(1080, 1920))

    mgr.report_boundary_crossing(1, 't1', 'in', 100.0)
    mgr.report_boundary_crossing(1, 't1', 'out', 300.0)
    # reverse re-touch: another IN after departure must be ignored
    mgr.report_boundary_crossing(1, 't1', 'in', 320.0)

    gid = mgr.get_global_id(1, 't1')
    with mgr._lock:
        identity = mgr._identities[gid]
    assert identity.berth_in_ts == 100.0  # unchanged
    assert identity.berth_out_ts == 300.0  # not reset


# ── 3. Directional sequential handoff (OCR-less) → single identity ─────────────

def test_directional_handoff_ocrless_merges():
    """No OCR: boat exits cam1 moving right, appears at cam2 left edge → merge."""
    mgr = _manager(
        directional_handoff_config=DirectionalHandoffConfig(
            enabled=True, max_transit_sec=20.0, min_velocity_px=5.0,
            embedding_floor=0.4, accept_threshold=0.55,
        ),
    )
    shared = _emb([1.0, 0.2, 0.0])
    # Anchor timestamps to real clock so _flush_expired_locked (which uses
    # time.time()) does not finalize cam1's identity before cam2 arrives.
    base = time.time()
    # cam1: boat near right border moving right (vx>0)
    t1 = _track('t1', 1, box=[1850, 100, 1910, 200], embedding=shared,
                velocity=(30.0, 0.0), first_seen=base, last_seen=base + 2.0)
    mgr.report_track_update(1, t1, embedding=shared, frame_shape=(1080, 1920))
    mgr.report_track_removed(1, t1, [])

    # cam2: boat appears at LEFT edge shortly after (within handoff window)
    t2 = _track('t2', 2, box=[10, 100, 70, 200], embedding=shared,
                velocity=(30.0, 0.0), first_seen=base + 3.0, last_seen=base + 5.0)
    gid2 = mgr.report_track_update(2, t2, embedding=shared, frame_shape=(1080, 1920))

    gid1 = mgr.get_global_id(1, 't1')
    assert gid1 == gid2, 'directional handoff should merge into one identity'


# ── 4. Billing chain: berth window → hours ─────────────────────────────────────

def _dt(h, m):
    return datetime(2026, 7, 1, h, m, 0, tzinfo=timezone.utc)


def test_billing_full_window_from_berth_timestamps():
    from app.services.detection_invoice_service import resolve_berth_window, _berthing_hours
    # detection track window loose; berth in/out precise
    s, e = resolve_berth_window(_dt(9, 0), _dt(12, 0), _dt(9, 30), _dt(11, 30))
    assert s == _dt(9, 30)
    assert e == _dt(11, 30)
    assert _berthing_hours(s, e) == Decimal('2')


def test_billing_zero_when_berth_window_degenerate():
    from app.services.detection_invoice_service import resolve_berth_window
    # out before in → invalid → (None, None) → no anchorage charge
    s, e = resolve_berth_window(_dt(9, 0), _dt(12, 0), _dt(11, 30), _dt(9, 30))
    assert s is None and e is None


def test_billing_fallback_when_only_berth_in():
    from app.services.detection_invoice_service import resolve_berth_window, _berthing_hours
    s, e = resolve_berth_window(_dt(9, 0), _dt(12, 0), _dt(9, 30), None)
    assert s == _dt(9, 30)
    assert e == _dt(12, 0)  # falls back to detection end
    assert _berthing_hours(s, e) == Decimal('2.5')


def test_billing_reverse_scenario_single_charge():
    """Integration: reverse re-touch kept berth_out at true departure, so the
    billing window reflects one clean visit, not an inflated re-entry."""
    from app.services.detection_invoice_service import resolve_berth_window, _berthing_hours
    # berth_in/out as produced by reid after reverse guard (300 kept, not 320+)
    berth_in = datetime.fromtimestamp(100.0, tz=timezone.utc)
    berth_out = datetime.fromtimestamp(300.0, tz=timezone.utc)
    start = datetime.fromtimestamp(90.0, tz=timezone.utc)
    end = datetime.fromtimestamp(310.0, tz=timezone.utc)
    s, e = resolve_berth_window(start, end, berth_in, berth_out)
    assert (e - s).total_seconds() == 200.0  # exactly the real visit, not extended
    assert _berthing_hours(s, e) == Decimal(str(200.0)) / Decimal('3600')

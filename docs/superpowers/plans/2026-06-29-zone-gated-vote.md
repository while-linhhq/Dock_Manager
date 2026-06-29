# Zone-Gated Identity Vote — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate OCR/embedding votes from entering the ship_id pool unless the track's `berth_zone_overlap >= berth_zone_threshold`; OCR/embedding workers still run and update overlay cache regardless.

**Architecture:** Add `get_track(track_id)` to `BoatTracker`, add `_is_in_recognition_zone(track)` helper to `PerCameraPipeline`, insert zone gate in both `_on_ocr_result` and `_on_visual_result` callbacks right before `report_ocr_result`. No change to workers, pool, or lock logic.

**Tech Stack:** Python, threading, pytest, unittest.mock

---

## File Map

| File | Change |
|---|---|
| `server/app/services/ai/boat_tracker.py` | Add `get_track(track_id) -> TrackedBoat \| None` after line 479 |
| `server/app/services/ai/per_camera_pipeline.py` | Add `_is_in_recognition_zone`; gate in `_on_ocr_result` (line 546) and `_on_visual_result` (line 564) |
| `server/app/tests/test_zone_gated_vote.py` | New — 4 test cases |

---

### Task 1: Add `get_track` to `BoatTracker`

**Files:**
- Modify: `server/app/services/ai/boat_tracker.py:479`

- [ ] **Step 1: Insert method after `get_track_state`**

In `boat_tracker.py`, find `get_track_state` (line 476). Insert immediately after its closing line:

```python
def get_track(self, track_id: str) -> TrackedBoat | None:
    with self._lock:
        return self._tracks.get(track_id)
```

- [ ] **Step 2: Verify no import changes needed**

`TrackedBoat` is already imported at module level — no new imports.

- [ ] **Step 3: Commit**

```bash
git add server/app/services/ai/boat_tracker.py
git commit -m "feat(tracker): add get_track accessor method"
```

---

### Task 2: Add `_is_in_recognition_zone` and gate `_on_ocr_result`

**Files:**
- Modify: `server/app/services/ai/per_camera_pipeline.py:546`

- [ ] **Step 1: Insert `_is_in_recognition_zone` before `_on_ocr_result`**

In `per_camera_pipeline.py`, find the line `def _on_ocr_result(self, track_id: str` (line 546). Insert immediately before it:

```python
def _is_in_recognition_zone(self, track: TrackedBoat) -> bool:
    overlap = getattr(track, 'berth_zone_overlap', None)
    threshold = getattr(track, 'berth_zone_threshold', None)
    if overlap is None or threshold is None:
        return True  # no zone configured — don't gate
    return overlap >= threshold

```

- [ ] **Step 2: Gate vote in `_on_ocr_result`**

Current `_on_ocr_result` (line 546):

```python
def _on_ocr_result(self, track_id: str, ship_id: str, confidence: float) -> None:
    if self._tracker.is_track_identity_locked(str(track_id)):
        return
    if not self._should_accept_ship_id(ship_id, source='ocr', confidence=confidence):
        return
    self._reid_manager.report_ocr_result(
```

Add gate block between `_should_accept_ship_id` check and `report_ocr_result`:

```python
def _on_ocr_result(self, track_id: str, ship_id: str, confidence: float) -> None:
    if self._tracker.is_track_identity_locked(str(track_id)):
        return
    if not self._should_accept_ship_id(ship_id, source='ocr', confidence=confidence):
        return
    track = self._tracker.get_track(str(track_id))
    if track is not None and not self._is_in_recognition_zone(track):
        return
    self._reid_manager.report_ocr_result(
        int(self.config.camera_id),
        str(track_id),
        ship_id,
        confidence,
    )
    global_ship_id = self._reid_manager.get_global_ship_id(
        int(self.config.camera_id),
        str(track_id),
    )
    if global_ship_id:
        self._tracker.update_track_metadata(str(track_id), ship_id=global_ship_id)
```

- [ ] **Step 3: Commit**

```bash
git add server/app/services/ai/per_camera_pipeline.py
git commit -m "feat(pipeline): add _is_in_recognition_zone; gate OCR vote"
```

---

### Task 3: Gate `_on_visual_result`

**Files:**
- Modify: `server/app/services/ai/per_camera_pipeline.py:564`

- [ ] **Step 1: Locate gate insertion point in `_on_visual_result`**

The `ocr_cache` update block (lines 580-599) must stay — it feeds the overlay. Gate goes after the identity lock check (currently line 605):

```python
        if not ship_id or not self._should_accept_ship_id(
            ship_id, source=source, confidence=confidence
        ):
            return
        if self._tracker.is_track_identity_locked(str(track_id)):
            return
        # ← insert gate here
        self._reid_manager.report_ocr_result(
```

- [ ] **Step 2: Insert gate**

```python
        if not ship_id or not self._should_accept_ship_id(
            ship_id, source=source, confidence=confidence
        ):
            return
        if self._tracker.is_track_identity_locked(str(track_id)):
            return
        track = self._tracker.get_track(str(track_id))
        if track is not None and not self._is_in_recognition_zone(track):
            return
        self._reid_manager.report_ocr_result(
            int(self.config.camera_id),
            str(track_id),
            ship_id,
            float(confidence),
        )
        global_ship_id = self._reid_manager.get_global_ship_id(
            int(self.config.camera_id),
            str(track_id),
        )
        if global_ship_id:
            self._tracker.update_track_metadata(str(track_id), ship_id=global_ship_id)
        else:
            self._tracker.update_track_metadata(str(track_id), ship_id=ship_id)
```

- [ ] **Step 3: Commit**

```bash
git add server/app/services/ai/per_camera_pipeline.py
git commit -m "feat(pipeline): gate visual/embedding vote on berth zone overlap"
```

---

### Task 4: Tests

**Files:**
- Create: `server/app/tests/test_zone_gated_vote.py`

- [ ] **Step 1: Write test file**

```python
"""Tests for zone-gated identity vote (per_camera_pipeline._is_in_recognition_zone)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.ai.per_camera_pipeline import PerCameraPipeline


def _make_pipeline() -> PerCameraPipeline:
    """Construct pipeline without running __init__, inject required attrs."""
    p = object.__new__(PerCameraPipeline)
    p._tracker = MagicMock()
    p._reid_manager = MagicMock()
    p._ocr_cache = {}
    p._ocr_lock = MagicMock()
    p._ship_id_catalog = None
    cfg = MagicMock()
    cfg.camera_id = 1
    p.config = cfg
    return p


def _make_track(overlap, threshold):
    t = MagicMock()
    t.berth_zone_overlap = overlap
    t.berth_zone_threshold = threshold
    return t


# ── _is_in_recognition_zone unit tests ──────────────────────────────────────

def test_below_threshold_returns_false():
    p = _make_pipeline()
    track = _make_track(overlap=0.1, threshold=0.3)
    assert p._is_in_recognition_zone(track) is False


def test_above_threshold_returns_true():
    p = _make_pipeline()
    track = _make_track(overlap=0.5, threshold=0.3)
    assert p._is_in_recognition_zone(track) is True


def test_no_zone_configured_returns_true():
    p = _make_pipeline()
    track = _make_track(overlap=None, threshold=None)
    assert p._is_in_recognition_zone(track) is True


def test_no_threshold_returns_true():
    p = _make_pipeline()
    track = _make_track(overlap=0.1, threshold=None)
    assert p._is_in_recognition_zone(track) is True


# ── _on_ocr_result gate tests ────────────────────────────────────────────────

def test_ocr_vote_blocked_when_outside_zone():
    p = _make_pipeline()
    track = _make_track(overlap=0.05, threshold=0.3)
    p._tracker.is_track_identity_locked.return_value = False
    p._tracker.get_track.return_value = track

    with patch.object(p, '_should_accept_ship_id', return_value=True):
        p._on_ocr_result('trk_abc', 'TS-123', 0.9)

    p._reid_manager.report_ocr_result.assert_not_called()


def test_ocr_vote_passes_when_inside_zone():
    p = _make_pipeline()
    track = _make_track(overlap=0.5, threshold=0.3)
    p._tracker.is_track_identity_locked.return_value = False
    p._tracker.get_track.return_value = track
    p._reid_manager.get_global_ship_id.return_value = None

    with patch.object(p, '_should_accept_ship_id', return_value=True):
        p._on_ocr_result('trk_abc', 'TS-123', 0.9)

    p._reid_manager.report_ocr_result.assert_called_once()


def test_ocr_vote_passes_when_track_gone():
    """Track removed before callback fires — gate must NOT block vote (spec edge case)."""
    p = _make_pipeline()
    p._tracker.is_track_identity_locked.return_value = False
    p._tracker.get_track.return_value = None  # track already removed
    p._reid_manager.get_global_ship_id.return_value = None

    with patch.object(p, '_should_accept_ship_id', return_value=True):
        p._on_ocr_result('trk_abc', 'TS-123', 0.9)

    p._reid_manager.report_ocr_result.assert_called_once()


# ── pool persistence test (integration-style) ────────────────────────────────

def test_pool_kept_after_leaving_zone():
    """Leaving zone stops new votes but does not clear accumulated pool."""
    from app.services.ai.boat_tracker import BoatTracker

    tracker = BoatTracker(camera_id=1)
    # Manually add a vote as if track was in zone
    tracker._ocr_history['trk_x'] = [('TS-456', 0.95)]

    # Simulate leaving zone: no new call to add_ocr_vote
    # Pool must remain untouched
    assert tracker._ocr_history.get('trk_x') == [('TS-456', 0.95)]
```

- [ ] **Step 2: Run tests**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
python -m pytest app/tests/test_zone_gated_vote.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add server/app/tests/test_zone_gated_vote.py
git commit -m "test(pipeline): zone-gated vote — 9 unit tests"
```

# Plan: Post-Hoc Detection Merge

**Date:** 2026-07-01
**Goal:** After the pipeline creates a detection record, absorb any older detections of the same vessel whose berth window is fully contained within the new detection's berth window. The detection with the longest berth window always wins.

---

## Architecture

```
pipeline_service.py
  └─ _persist_track_removed()
       ├─ detection_repo.create()          ← existing
       ├─ absorb_contained(db, det.id)     ← NEW (inserted at line 1219)
       │    ├─ detection_repo.get_overlapping_by_vessel()   ← NEW repo method
       │    ├─ detection_repo.soft_delete()                 ← NEW repo method
       │    └─ invoice soft-delete (inline)
       └─ media attachment + invoice creation (existing, using winner id)
```

Key invariant: `det` and `det_id_for_invoice` are always updated to the winner before any media or invoice work begins. The winner is the detection with the longest `berth_out_time - berth_in_time`.

## Tech Stack

- Python 3.11+, FastAPI, SQLAlchemy (sync sessions), PostgreSQL 16
- pytest for tests (existing suite in `server/app/tests/`)
- No new dependencies

---

> **Note for agentic workers:** This plan is designed for the `superpowers:subagent-driven-development` skill. Tasks 1–3 are sequential (each builds on the previous). Run tests at each RED/GREEN checkpoint before proceeding to the next task. Do not skip the commit steps — they act as save points.

---

## Task 1 — Repository methods

### 1.1 Write failing tests first

File: `server/app/tests/test_detection_merge.py`

Add this import block and the six test functions. The full file (tests only, no service yet):

```python
"""Tests for post-hoc detection merge."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.repositories.detection_repository import DetectionRepository
from app.models.detection import Detection
from app.models.invoice import Invoice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(hour: int, minute: int) -> datetime:
    """UTC datetime on a fixed date."""
    return datetime(2026, 7, 1, hour, minute, 0, tzinfo=timezone.utc)


def _make_detection(
    id: int,
    vessel_id: int,
    berth_in: datetime | None,
    berth_out: datetime | None,
    is_accepted: bool | None = None,
    deleted_at: datetime | None = None,
) -> Detection:
    d = Detection()
    d.id = id
    d.vessel_id = vessel_id
    d.track_id = f"track_{id}"
    d.berth_in_time = berth_in
    d.berth_out_time = berth_out
    d.is_accepted = is_accepted
    d.deleted_at = deleted_at
    d.invoices = []
    return d


def _make_invoice(
    id: int,
    detection_id: int,
    payment_status: str = "UNPAID",
    deleted_at: datetime | None = None,
) -> Invoice:
    inv = Invoice()
    inv.id = id
    inv.detection_id = detection_id
    inv.payment_status = payment_status
    inv.deleted_at = deleted_at
    inv.invoice_number = f"INV-{id:04d}"
    inv.total_amount = 100
    return inv


# ---------------------------------------------------------------------------
# Test 1 — new detection is the winner, absorbs the old one
# ---------------------------------------------------------------------------

def test_new_detection_is_winner_absorbs_old():
    """New detection (21:40–22:00) contains old one (21:50–21:55) → old absorbed."""
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(21, 40), berth_out=_dt(22, 0))
    old_det = _make_detection(1, vessel_id=1, berth_in=_dt(21, 50), berth_out=_dt(21, 55))

    repo = DetectionRepository()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda db, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        winner_id = absorb_contained(MagicMock(), 2)

    assert winner_id == 2
    mock_soft_delete.assert_called_once()
    call_args = mock_soft_delete.call_args[0]
    assert call_args[1] == 1  # absorbed detection id


# ---------------------------------------------------------------------------
# Test 2 — old detection is the winner, new one is absorbed
# ---------------------------------------------------------------------------

def test_old_detection_is_winner_new_is_absorbed():
    """Old detection (21:40–22:05) contains new one (21:50–22:00) → new absorbed, returns old.id."""
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(21, 50), berth_out=_dt(22, 0))
    old_det = _make_detection(1, vessel_id=1, berth_in=_dt(21, 40), berth_out=_dt(22, 5))

    repo = DetectionRepository()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda db, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        winner_id = absorb_contained(MagicMock(), 2)

    assert winner_id == 1
    mock_soft_delete.assert_called_once()
    call_args = mock_soft_delete.call_args[0]
    assert call_args[1] == 2  # new detection was absorbed


# ---------------------------------------------------------------------------
# Test 3 — skip merge when berth times are missing
# ---------------------------------------------------------------------------

def test_no_merge_when_berth_times_missing():
    """New detection has no berth_in_time → returns same id, no merge."""
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(5, vessel_id=1, berth_in=None, berth_out=None)

    repo = DetectionRepository()

    with (
        patch.object(repo.__class__, 'get', return_value=new_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel') as mock_query,
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        winner_id = absorb_contained(MagicMock(), 5)

    assert winner_id == 5
    mock_query.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — accepted candidate is not absorbed
# ---------------------------------------------------------------------------

def test_no_merge_when_accepted():
    """Candidate has is_accepted=True → not absorbed, new detection remains winner."""
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(21, 40), berth_out=_dt(22, 0))
    # is_accepted=True candidates are excluded at the query level;
    # get_overlapping_by_vessel returns an empty list here.
    repo = DetectionRepository()

    with (
        patch.object(repo.__class__, 'get', return_value=new_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        winner_id = absorb_contained(MagicMock(), 2)

    assert winner_id == 2
    mock_soft_delete.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5 — UNPAID invoice on absorbed detection is soft-deleted
# ---------------------------------------------------------------------------

def test_invoice_soft_deleted_for_absorbed():
    """Absorbed detection has UNPAID invoice → invoice gets deleted_at set."""
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(21, 40), berth_out=_dt(22, 0))
    old_det = _make_detection(1, vessel_id=1, berth_in=_dt(21, 50), berth_out=_dt(21, 55))
    unpaid_inv = _make_invoice(10, detection_id=1, payment_status='UNPAID')
    old_det.invoices = [unpaid_inv]

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete'),
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        absorb_contained(db, 2)

    assert unpaid_inv.deleted_at is not None
    db.commit.assert_called()


# ---------------------------------------------------------------------------
# Test 6 — PAID invoice on absorbed detection is NOT soft-deleted
# ---------------------------------------------------------------------------

def test_paid_invoice_not_deleted():
    """Absorbed detection has PAID invoice → invoice kept (deleted_at stays None)."""
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(21, 40), berth_out=_dt(22, 0))
    old_det = _make_detection(1, vessel_id=1, berth_in=_dt(21, 50), berth_out=_dt(21, 55))
    paid_inv = _make_invoice(11, detection_id=1, payment_status='PAID')
    old_det.invoices = [paid_inv]

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete'),
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        absorb_contained(db, 2)

    assert paid_inv.deleted_at is None
```

### 1.2 Confirm RED

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_detection_merge.py -v 2>&1 | head -40
```

Expected output: all 6 tests fail with `ImportError: cannot import name 'absorb_contained' from 'app.services.detection_merge_service'` (module does not exist yet).

### 1.3 Add repository methods

File: `server/app/repositories/detection_repository.py`

Add these two methods to the `DetectionRepository` class, before the closing of the class body (after `delete`):

```python
    def get_overlapping_by_vessel(
        self,
        db: Session,
        vessel_id: int,
        berth_in: datetime,
        berth_out: datetime,
        exclude_id: int,
        window_hours: int = 2,
    ) -> List[Detection]:
        """Return non-deleted, non-accepted detections of the same vessel whose
        berth window overlaps the given window by ±window_hours hours.

        Filtering for strict containment is done in Python by the service layer
        after loading candidates.
        """
        from datetime import timedelta
        from sqlalchemy import and_

        earliest = berth_in - timedelta(hours=window_hours)
        latest = berth_out + timedelta(hours=window_hours)
        return (
            db.query(Detection)
            .filter(
                Detection.vessel_id == vessel_id,
                Detection.id != exclude_id,
                Detection.deleted_at.is_(None),
                Detection.is_accepted.isnot(True),
                Detection.berth_in_time.isnot(None),
                Detection.berth_out_time.isnot(None),
                Detection.berth_in_time >= earliest,
                Detection.berth_out_time <= latest,
            )
            .all()
        )

    def soft_delete(self, db: Session, detection_id: int) -> None:
        """Set deleted_at on a detection (soft delete)."""
        from datetime import timezone as _tz

        db_obj = self.get(db, detection_id)
        if db_obj is None:
            return
        db_obj.deleted_at = datetime.now(_tz.utc)
        db.commit()
```

Also add `datetime` to the existing imports at the top of the file (it is only imported indirectly via `date` and `datetime` from `datetime` already — verify the import line reads):

```python
from datetime import date, datetime, time, timezone
```

No change needed if it is already there.

### 1.4 Create the merge service

File: `server/app/services/detection_merge_service.py` (new file)

```python
"""Post-hoc detection merge service.

After the pipeline creates a detection, call absorb_contained() to find any
older detections of the same vessel whose berth window is fully contained
within the new one, absorb them (soft-delete their UNPAID invoices and
themselves), and return the winner's id.

The winner is always the detection with the longest berth window duration.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.detection_repository import detection_repo

_log = logging.getLogger(__name__)


def absorb_contained(db: Session, detection_id: int) -> int:
    """Absorb detections of the same vessel whose berth window is fully
    contained within the new detection's berth window.

    Returns:
        The winner's detection id (may differ from detection_id if an older
        detection turns out to have a longer berth window).
    """
    new_det = detection_repo.get(db, detection_id)
    if new_det is None:
        _log.warning('detection_merge: detection %s not found, skipping', detection_id)
        return detection_id

    # Guard: both berth timestamps must be present to compare windows
    if new_det.berth_in_time is None or new_det.berth_out_time is None:
        return detection_id

    candidates = detection_repo.get_overlapping_by_vessel(
        db,
        vessel_id=new_det.vessel_id,
        berth_in=new_det.berth_in_time,
        berth_out=new_det.berth_out_time,
        exclude_id=new_det.id,
    )

    # Build the pool: new detection + all candidates that actually have berth times
    pool = [new_det] + [c for c in candidates if c.berth_in_time and c.berth_out_time]

    # Winner = detection with the longest berth window
    def _duration(d):  # type: ignore[return]
        return (d.berth_out_time - d.berth_in_time).total_seconds()

    winner = max(pool, key=_duration)

    now = datetime.now(timezone.utc)

    for det in pool:
        if det.id == winner.id:
            continue

        # Soft-delete UNPAID invoices only; leave PAID invoices intact
        for inv in list(det.invoices):
            if inv.payment_status == 'UNPAID' and inv.deleted_at is None:
                inv.deleted_at = now

        db.commit()

        # Soft-delete the detection itself
        detection_repo.soft_delete(db, det.id)

        _log.info(
            'detection_merge: absorbed detection %s into winner %s',
            det.id,
            winner.id,
        )

    return winner.id
```

### 1.5 Confirm GREEN

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_detection_merge.py -v
```

Expected output:

```
PASSED app/tests/test_detection_merge.py::test_new_detection_is_winner_absorbs_old
PASSED app/tests/test_detection_merge.py::test_old_detection_is_winner_new_is_absorbed
PASSED app/tests/test_detection_merge.py::test_no_merge_when_berth_times_missing
PASSED app/tests/test_detection_merge.py::test_no_merge_when_accepted
PASSED app/tests/test_detection_merge.py::test_invoice_soft_deleted_for_absorbed
PASSED app/tests/test_detection_merge.py::test_paid_invoice_not_deleted

6 passed in ...s
```

### 1.6 Commit

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/repositories/detection_repository.py \
        server/app/services/detection_merge_service.py \
        server/app/tests/test_detection_merge.py
git commit -m "feat(detection): add post-hoc detection merge service and repo methods

- DetectionRepository.get_overlapping_by_vessel(): candidate query
- DetectionRepository.soft_delete(): set deleted_at
- detection_merge_service.absorb_contained(): winner selection, invoice
  soft-delete, detection soft-delete
- 6 passing unit tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2 — Pipeline integration

### 2.1 Modify pipeline_service.py

File: `server/app/services/pipeline_service.py`

Locate the block at line 1219 (immediately after the `except IntegrityError` block):

```python
            det_id_for_invoice = det.id

            video_uri: str | None = None
```

Replace it with:

```python
            det_id_for_invoice = det.id

            # Post-hoc merge: absorb contained detections of the same vessel.
            # Must run before media attachment and invoice creation so that all
            # downstream work goes to the winner's record.
            if det.berth_in_time is not None and det.berth_out_time is not None:
                from app.services.detection_merge_service import absorb_contained
                try:
                    winner_id = absorb_contained(db, det.id)
                    if winner_id != det.id:
                        det = detection_repo.get(db, winner_id)
                        det_id_for_invoice = winner_id
                except Exception:
                    _log.exception(
                        'detection_merge: failed for detection_id=%s', det.id
                    )

            video_uri: str | None = None
```

The `except Exception` swallows merge failures so the pipeline never loses a detection due to a merge bug. The exception is logged via `_log.exception` which captures the full traceback.

### 2.2 Verify no import errors

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "from app.services.pipeline_service import PipelineService; print('OK')"
```

Expected output: `OK`

### 2.3 Run full test suite

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all previously passing tests still pass; the 6 new merge tests pass.

### 2.4 Commit

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/pipeline_service.py
git commit -m "feat(pipeline): call absorb_contained after detection create

Insert post-hoc merge call at _persist_track_removed() line 1219.
Winner detection id flows through to media attachment and invoice
creation. Merge failures are caught and logged so pipeline is not
interrupted.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Type consistency checklist

| Symbol | Type | Used in |
|--------|------|---------|
| `detection_id` parameter | `int` | `absorb_contained`, `soft_delete`, `get_overlapping_by_vessel` (as `exclude_id`) |
| `winner_id` in pipeline | `int` | returned by `absorb_contained`, passed to `detection_repo.get()` |
| `det` in pipeline | `Detection` | re-assigned from `detection_repo.get(db, winner_id)` on absorption |
| `det_id_for_invoice` | `int \| None` | set to `winner_id` (int) on absorption; existing `None` path unchanged |
| `deleted_at` on Invoice/Detection | `datetime` (UTC-aware) | `datetime.now(timezone.utc)` |
| `berth_in_time`, `berth_out_time` | `datetime` (UTC-aware) | guard checks `is not None` before arithmetic |

---

## Edge cases

**Tie (equal duration):** `max()` returns the first maximum encountered. The pool is built as `[new_det] + candidates`, so among equals the new detection wins. This is intentional — prefer the freshest record.

**IntegrityError path:** When `detection_repo.create()` raises `IntegrityError`, `det` is loaded via `get_by_track_id`. It may already have been merged by a concurrent call. `absorb_contained` will find no new candidates in that case and return `det.id` unchanged — safe.

**No berth window on new detection:** The guard at the top of `absorb_contained` (both times None check) returns early. The pipeline-side guard (`if det.berth_in_time is not None and det.berth_out_time is not None`) prevents the import and call entirely for the common case of detections that never entered a berth zone.

**Accepted detections:** `get_overlapping_by_vessel` filters `is_accepted IS NOT TRUE`, so accepted detections are never candidates — they cannot be absorbed regardless of window size.

**PAID invoices:** Only `payment_status == 'UNPAID'` invoices have `deleted_at` set. PAID invoices survive the merge intact (test 6 verifies this).

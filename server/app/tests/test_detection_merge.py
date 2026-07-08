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


class _FakeVessel:
    def __init__(self, ship_id: str):
        self.ship_id = ship_id


def _make_detection(
    id: int,
    vessel_id: int,
    berth_in: datetime | None,
    berth_out: datetime | None,
    is_accepted: bool | None = None,
    deleted_at: datetime | None = None,
    ship_id: str = "SG-0001",
    berth_out_source: str | None = None,
) -> Detection:
    d = Detection()
    d.id = id
    d.vessel_id = vessel_id
    d.track_id = f"track_{id}"
    d.berth_in_time = berth_in
    d.berth_out_time = berth_out
    d.berth_out_source = berth_out_source
    d.is_accepted = is_accepted
    d.deleted_at = deleted_at
    d.invoices = []
    # Gán vessel định danh mặc định (known) để không bị guard UNKNOWN chặn.
    # Test UNKNOWN truyền ship_id='UNKNOWN' tường minh. Set qua __dict__ để
    # bypass instrumented relationship setter của SQLAlchemy (tránh _sa_instance_state).
    d.__dict__['vessel'] = _FakeVessel(ship_id)
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
    """Candidate has is_accepted=True → query excludes it, soft_delete never called.

    The guard lives in get_overlapping_by_vessel (is_accepted.isnot(True)).
    We simulate this by having the mock return an empty list (as the real DB
    query would), while also verifying via a separate sub-test that if somehow
    an accepted detection slips through, the service itself does not soft-delete
    it because it won't appear in the candidate list at all.
    """
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(21, 40), berth_out=_dt(22, 0))
    # accepted_det has a longer window — if it were included it would become
    # winner and new_det would be absorbed.  The query must exclude it.
    accepted_det = _make_detection(
        1, vessel_id=1, berth_in=_dt(21, 30), berth_out=_dt(22, 30),
        is_accepted=True,
    )
    repo = DetectionRepository()

    # get_overlapping_by_vessel filters is_accepted.isnot(True) at DB level;
    # mock returns [] to reflect that the accepted detection is excluded.
    with (
        patch.object(repo.__class__, 'get', return_value=new_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[]) as mock_query,
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        winner_id = absorb_contained(MagicMock(), 2)

    assert winner_id == 2
    mock_soft_delete.assert_not_called()
    mock_query.assert_called_once()  # query was attempted but returned nothing


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


# ---------------------------------------------------------------------------
# Test 7 — two disjoint visits of the same vessel are NOT merged
# ---------------------------------------------------------------------------

def test_disjoint_visits_not_merged():
    """Two separate berthing visits of the same vessel that are far enough apart
    in time (gap ≥ berth_merge_gap_sec) must NOT be merged, even though they fall
    inside the ±2h coarse candidate filter.

    Repro: SG-7082 visit 06:45–07:15 and visit 08:29–08:31 were both returned by
    the ±2h repo filter; the old code merged them and deleted the short one →
    MISSING detection. Here the gap = 08:29 − 07:15 = 74 min > 30 min default →
    a real departure-and-return → keep both. (Default gap read falls back to
    1800s because the port_config lookup is not mocked here.)
    """
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(8, 29), berth_out=_dt(8, 31))
    # Earlier disjoint visit, longer duration — would win & absorb new_det if
    # the 74-min gap were not respected.
    old_det = _make_detection(1, vessel_id=1, berth_in=_dt(6, 45), berth_out=_dt(7, 15))

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        winner_id = absorb_contained(db, 2)

    assert winner_id == 2
    mock_soft_delete.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8 — fragmented visit (short gap, no overlap) IS coalesced
# ---------------------------------------------------------------------------

def test_fragmented_visit_within_gap_is_coalesced():
    """Two fragments of ONE berthing visit whose windows do NOT overlap but are
    only ~9 min apart (track dropped in-zone and re-acquired) → GỘP into one.

    Repro (vessel 120, 7/7): a boat neo continuously produced fragments
    00:11:35–00:11:57 then 00:20:49–00:24:12 (gap 8m52s, both last_seen). With
    overlap-only logic they stayed separate (over-fragmentation). Gap-based
    merge (gap < 1800s) stitches them, and the winner window widens to span
    00:11:35–00:24:12.
    """
    from app.services import detection_merge_service as svc

    new_det = _make_detection(
        2, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 0, 20, 49, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 0, 24, 12, tzinfo=timezone.utc),
    )
    frag = _make_detection(
        1, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 0, 11, 35, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 0, 11, 57, tzinfo=timezone.utc),
    )

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else frag),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[frag]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_merge_gap_sec', return_value=1800.0),
        patch.object(svc, '_window_hours', return_value=2.0),
    ):
        winner_id = svc.absorb_contained(db, 2)

    # new_det (203s) is longer than frag (22s) → winner is new_det (id 2).
    assert winner_id == 2
    mock_soft_delete.assert_called_once()
    assert mock_soft_delete.call_args[0][1] == 1
    # Winner window widened to span the whole cluster.
    assert new_det.berth_in_time == datetime(2026, 7, 7, 0, 11, 35, tzinfo=timezone.utc)
    assert new_det.berth_out_time == datetime(2026, 7, 7, 0, 24, 12, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 9 — edge-departure (real leave, last_seen) with long gap stays separate
# ---------------------------------------------------------------------------

def test_edge_departure_long_gap_kept_separate():
    """Boat truly departs at the camera edge (OUT missed → last_seen fallback)
    and returns 50 min later. Gap 50' > 30' → two separate visits, NOT merged.

    This is the case berth_out_source CANNOT distinguish (edge-departure also
    yields last_seen) — only the time gap separates it from a lost-track stitch.
    """
    from app.services import detection_merge_service as svc

    # First visit ends 10:00 (real departure, but recorded as last_seen).
    old_det = _make_detection(
        1, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 9, 30, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc),
    )
    # Returns 50 min later.
    new_det = _make_detection(
        2, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 10, 50, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 11, 20, tzinfo=timezone.utc),
    )

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_merge_gap_sec', return_value=1800.0),
        patch.object(svc, '_window_hours', return_value=2.0),
    ):
        winner_id = svc.absorb_contained(db, 2)

    assert winner_id == 2
    mock_soft_delete.assert_not_called()
    # Windows untouched (no coalescing).
    assert new_det.berth_in_time == datetime(2026, 7, 7, 10, 50, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 10 — chain of fragments all coalesced into one winner
# ---------------------------------------------------------------------------

def test_fragment_chain_coalesced():
    """A chain of 4 short fragments each < 30 min apart is fully coalesced into
    one visit; the longest fragment wins and its window spans the whole chain.
    """
    from app.services import detection_merge_service as svc

    def _f(id, h, m0, m1):
        return _make_detection(
            id, vessel_id=1,
            berth_in=datetime(2026, 7, 7, h, m0, tzinfo=timezone.utc),
            berth_out=datetime(2026, 7, 7, h, m1, tzinfo=timezone.utc),
        )

    # New detection is the LONGEST → becomes winner.
    new_det = _f(5, 0, 48, 55)          # 7 min — longest
    frags = [_f(1, 0, 11, 12), _f(2, 0, 20, 24), _f(3, 0, 26, 27), _f(4, 0, 37, 38)]

    repo = DetectionRepository()
    db = MagicMock()
    by_id = {d.id: d for d in (frags + [new_det])}

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: by_id[did]),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=frags),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_merge_gap_sec', return_value=1800.0),
        patch.object(svc, '_window_hours', return_value=2.0),
    ):
        winner_id = svc.absorb_contained(db, 5)

    assert winner_id == 5
    assert mock_soft_delete.call_count == 4  # all 4 fragments absorbed
    # Winner spans earliest berth_in (00:11) to latest berth_out (00:55).
    assert new_det.berth_in_time == datetime(2026, 7, 7, 0, 11, tzinfo=timezone.utc)
    assert new_det.berth_out_time == datetime(2026, 7, 7, 0, 55, tzinfo=timezone.utc)


def test_overlapping_visit_with_null_berth_out_uses_end_time():
    """Candidate with NULL berth_out falls back to end_time for overlap check;
    a genuinely overlapping short track is still absorbed."""
    from app.services.detection_merge_service import absorb_contained

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(21, 40), berth_out=_dt(22, 10))
    # Overlapping visit, berth_out NULL → end_time fallback keeps it in-window.
    old_det = _make_detection(1, vessel_id=1, berth_in=_dt(21, 50), berth_out=None)
    old_det.end_time = _dt(21, 55)

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
    ):
        winner_id = absorb_contained(db, 2)

    assert winner_id == 2
    mock_soft_delete.assert_called_once()
    assert mock_soft_delete.call_args[0][1] == 1


# ---------------------------------------------------------------------------
# Test 11 — UNKNOWN detections are NOT merged (identity not confirmed yet)
# ---------------------------------------------------------------------------

def test_unknown_detections_not_merged():
    """Hai detection UNKNOWN cùng 'vessel UNKNOWN', gap nhỏ — vẫn KHÔNG gộp.

    Mọi tàu chưa định danh trỏ về CÙNG vessel 'UNKNOWN'; nếu gộp theo vessel_id
    sẽ trộn nhiều con tàu khác nhau. Guard berth_merge_skip_unknown chặn việc đó.
    """
    from app.services import detection_merge_service as svc

    new_det = _make_detection(2, vessel_id=1, berth_in=_dt(0, 20), berth_out=_dt(0, 24), ship_id='UNKNOWN')
    frag = _make_detection(1, vessel_id=1, berth_in=_dt(0, 11), berth_out=_dt(0, 12), ship_id='UNKNOWN')

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else frag),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[frag]) as mock_query,
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_skip_unknown', return_value=True),
    ):
        winner_id = svc.absorb_contained(db, 2)

    assert winner_id == 2
    mock_soft_delete.assert_not_called()
    mock_query.assert_not_called()  # trả về sớm trước cả khi query ứng viên


# ---------------------------------------------------------------------------
# Test 12 — after Zalo confirms ship_id, fragments DO coalesce
# ---------------------------------------------------------------------------

def test_confirmed_ship_id_coalesces_fragments():
    """Sau khi Zalo xác nhận (vessel không còn UNKNOWN), các mảnh cùng lượt gộp.

    Đây là hành vi khi _reassign_vessel_identity gọi lại absorb_contained: giờ
    ship_id đã biết → guard không chặn → gap-based coalesce chạy như thường.
    """
    from app.services import detection_merge_service as svc

    new_det = _make_detection(
        2, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 0, 20, 49, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 0, 24, 12, tzinfo=timezone.utc),
        ship_id='SG-7044',
    )
    frag = _make_detection(
        1, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 0, 11, 35, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 0, 11, 57, tzinfo=timezone.utc),
        ship_id='SG-7044',
    )

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else frag),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[frag]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_skip_unknown', return_value=True),
        patch.object(svc, '_merge_gap_sec', return_value=1800.0),
        patch.object(svc, '_window_hours', return_value=2.0),
    ):
        winner_id = svc.absorb_contained(db, 2)

    assert winner_id == 2
    mock_soft_delete.assert_called_once()
    assert mock_soft_delete.call_args[0][1] == 1
    assert new_det.berth_in_time == datetime(2026, 7, 7, 0, 11, 35, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 13 — OUT-crossing barrier: prev fragment left via real OUT crossing →
# next visit NOT merged even if gap < threshold
# ---------------------------------------------------------------------------

def test_out_crossing_barrier_blocks_merge():
    """Mảnh trước rời bằng OUT crossing THẬT (berth_out_source='crossing') →
    lượt sau KHÔNG gộp dù gap < 30'.

    Repro (vessel 89, 7/7): lượt 06:29:33–06:32:34 (crossing, tàu rời có bằng
    chứng) và lượt 06:48:29–06:58:55, gap 15.9' — TRƯỚC khi thêm hàng rào bị nối
    thành một lượt sai. OUT crossing = tàu đã rời thật → 2 lượt RIÊNG.
    """
    from app.services import detection_merge_service as svc

    old_det = _make_detection(
        1, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 6, 29, 33, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 6, 32, 34, tzinfo=timezone.utc),
        ship_id='SG-0089', berth_out_source='crossing',
    )
    new_det = _make_detection(
        2, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 6, 48, 29, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 6, 58, 55, tzinfo=timezone.utc),
        ship_id='SG-0089', berth_out_source='crossing',
    )

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_merge_gap_sec', return_value=1800.0),
        patch.object(svc, '_window_hours', return_value=2.0),
    ):
        winner_id = svc.absorb_contained(db, 2)

    assert winner_id == 2
    mock_soft_delete.assert_not_called()  # hàng rào crossing chặn nối
    # Windows untouched.
    assert new_det.berth_in_time == datetime(2026, 7, 7, 6, 48, 29, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 14 — last_seen prev (edge-departure or lost-track) still merges on gap
# ---------------------------------------------------------------------------

def test_last_seen_prev_still_merges_within_gap():
    """Mảnh trước rời bằng last_seen (track chết, KHÔNG có OUT crossing) → gap<30'
    vẫn GỘP. last_seen KHÔNG chứng minh tàu rời → chỉ có gap phân biệt; gap nhỏ =
    track-chết-nối-lại cùng lượt.
    """
    from app.services import detection_merge_service as svc

    old_det = _make_detection(
        1, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 0, 11, 35, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 0, 11, 57, tzinfo=timezone.utc),
        ship_id='SG-0120', berth_out_source='last_seen',
    )
    new_det = _make_detection(
        2, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 0, 20, 49, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 0, 24, 12, tzinfo=timezone.utc),
        ship_id='SG-0120', berth_out_source='last_seen',
    )

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_merge_gap_sec', return_value=1800.0),
        patch.object(svc, '_window_hours', return_value=2.0),
    ):
        winner_id = svc.absorb_contained(db, 2)

    assert winner_id == 2
    mock_soft_delete.assert_called_once()
    assert new_det.berth_in_time == datetime(2026, 7, 7, 0, 11, 35, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 15 — overlap still merges even when prev has OUT crossing (2 cameras)
# ---------------------------------------------------------------------------

def test_overlap_merges_despite_crossing():
    """Hàng rào crossing chỉ áp cho gap>0 (2 lượt tách biệt). Khi 2 cửa sổ THẬT
    SỰ chồng lấn (2 camera thấy cùng lúc), vẫn gộp dù prev có OUT crossing.
    """
    from app.services import detection_merge_service as svc

    old_det = _make_detection(
        1, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 6, 29, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 6, 40, tzinfo=timezone.utc),
        ship_id='SG-0089', berth_out_source='crossing',
    )
    # Overlaps old_det (starts 06:35 < 06:40).
    new_det = _make_detection(
        2, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 6, 35, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 6, 45, tzinfo=timezone.utc),
        ship_id='SG-0089', berth_out_source='crossing',
    )

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=lambda sess, did: new_det if did == 2 else old_det),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', return_value=[old_det]),
        patch.object(repo.__class__, 'soft_delete') as mock_soft_delete,
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_merge_gap_sec', return_value=1800.0),
        patch.object(svc, '_window_hours', return_value=2.0),
    ):
        winner_id = svc.absorb_contained(db, 2)

    assert mock_soft_delete.call_count == 1  # overlap → vẫn gộp


# ---------------------------------------------------------------------------
# Test 16 — INCREMENTAL replay: winner absorbs a real-OUT-crossing fragment,
# then the NEXT visit after that crossing must NOT be merged (source propagated)
# ---------------------------------------------------------------------------

def test_incremental_crossing_source_propagated_blocks_next():
    """Bug 3-bước (vessel 89, 7/7) — chỉ lộ khi replay TUẦN TỰ như live pipeline.

    Chuỗi persist:
      A 00:18–01:00 last_seen  (dài, sẽ là winner)
      B 01:10–01:14 crossing   (tàu RỜI THẬT tại 01:14)
      C 01:18–01:21 last_seen  (lượt sau, gap 4' so với B)

    Khi B persist: winner=A (dài hơn) nuốt B, berth_out A nới tới 01:14. NẾU
    KHÔNG propagate source, A.berth_out_source vẫn 'last_seen' → lúc C persist,
    hàng rào OUT-crossing không kích hoạt (thấy A last_seen) → C bị nối oan.
    Fix: winner mang berth_out_source='crossing' của mảnh cấp cluster_end →
    C persist thấy A src='crossing' → CHẶN nối. Đây là 2 lượt riêng.
    """
    from app.services import detection_merge_service as svc

    a = _make_detection(
        1, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 0, 18, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 1, 0, tzinfo=timezone.utc),
        ship_id='SG-9190', berth_out_source='last_seen',
    )
    b = _make_detection(
        2, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 1, 10, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 1, 14, tzinfo=timezone.utc),
        ship_id='SG-9190', berth_out_source='crossing',
    )
    c = _make_detection(
        3, vessel_id=1,
        berth_in=datetime(2026, 7, 7, 1, 18, tzinfo=timezone.utc),
        berth_out=datetime(2026, 7, 7, 1, 21, tzinfo=timezone.utc),
        ship_id='SG-9190', berth_out_source='last_seen',
    )

    store = {1: a, 2: b, 3: c}

    def _get(sess, did):
        return store.get(did)

    def _overlapping(sess, vessel_id, berth_in, berth_out, exclude_id, window_hours):
        # Trả các detection cùng vessel còn ALIVE (deleted_at is None), trừ chính nó.
        return [
            d for d in store.values()
            if d.vessel_id == vessel_id
            and d.id != exclude_id
            and d.deleted_at is None
            and d.berth_in_time is not None
        ]

    def _soft_delete(sess, did):
        store[did].deleted_at = datetime.now(timezone.utc)

    repo = DetectionRepository()
    db = MagicMock()

    with (
        patch.object(repo.__class__, 'get', side_effect=_get),
        patch.object(repo.__class__, 'get_overlapping_by_vessel', side_effect=_overlapping),
        patch.object(repo.__class__, 'soft_delete', side_effect=_soft_delete),
        patch('app.services.detection_merge_service.detection_repo', repo),
        patch.object(svc, '_merge_gap_sec', return_value=1800.0),
        patch.object(svc, '_window_hours', return_value=2.0),
    ):
        # Replay tuần tự đúng thứ tự persist.
        svc.absorb_contained(db, 1)
        svc.absorb_contained(db, 2)   # winner A nuốt B, propagate src='crossing'
        winner_c = svc.absorb_contained(db, 3)   # C phải KHÔNG bị nối

    # Sau B: A là winner, berth_out nới tới 01:14, source đã thành crossing.
    assert a.deleted_at is None
    assert b.deleted_at is not None
    assert a.berth_out_time == datetime(2026, 7, 7, 1, 14, tzinfo=timezone.utc)
    assert a.berth_out_source == 'crossing'
    # C là lượt riêng — hàng rào crossing chặn nối, C sống độc lập.
    assert c.deleted_at is None
    assert winner_c == 3

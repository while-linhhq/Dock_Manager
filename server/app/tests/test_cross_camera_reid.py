"""Cross-camera re-id: plate must not leak to a second concurrent boat via visual match."""

import time

import numpy as np

from app.services.ai.boat_tracker import TrackState, TrackedBoat
from app.services.ai.cross_camera_reid import CrossCameraReIdManager


def _track(
    track_id: str,
    *,
    camera_id: int = 1,
    box: tuple[float, float, float, float] = (10.0, 10.0, 100.0, 100.0),
) -> TrackedBoat:
    now = time.time()
    return TrackedBoat(
        track_id=track_id,
        state=TrackState.CONFIRMED,
        box=np.array(box, dtype=np.float32),
        conf=0.9,
        hits=5,
        misses=0,
        first_seen_ts=now,
        last_seen_ts=now,
        camera_id=camera_id,
    )


def _unit_embedding(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(128).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-6)


def test_visual_match_does_not_propagate_plate_without_ocr() -> None:
    mgr = CrossCameraReIdManager([1, 2, 3], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(7)

    boat_a = _track('trk_a', camera_id=2)
    mgr.report_track_update(2, boat_a, embedding=emb)
    mgr.report_ocr_result(2, 'trk_a', 'SG-6375', 0.95)

    boat_b = _track('trk_b', camera_id=3, box=(200.0, 200.0, 320.0, 320.0))
    similar_emb = emb * 0.98 + _unit_embedding(99) * 0.02
    mgr.report_track_update(3, boat_b, embedding=similar_emb)

    assert mgr.get_global_ship_id(3, 'trk_b') is None
    assert boat_b.ship_id is None


def test_ocr_on_second_track_shows_plate_only_after_read() -> None:
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(3)

    mgr.report_track_update(1, _track('trk_1', camera_id=1), embedding=emb)
    mgr.report_ocr_result(1, 'trk_1', 'SG-7082', 0.9)

    mgr.report_track_update(2, _track('trk_2', camera_id=2), embedding=emb)
    assert mgr.get_global_ship_id(2, 'trk_2') is None

    mgr.report_ocr_result(2, 'trk_2', 'SG-7082', 0.85)
    assert mgr.get_global_ship_id(2, 'trk_2') == 'SG-7082'


def test_repeated_track_updates_do_not_ballot_stuff_ship_id() -> None:
    """Per-frame report_track_update must NOT inject synthetic conf=1.0 votes.

    Regression for the self-reinforcing phantom identity: a track seeded with a
    wrong provisional ship_id (from a noisy embedding) used to append
    (ship_id, 1.0) into identity.ocr_history on EVERY frame via _attach_track.
    After N frames that ID accumulated N synthetic 1.0 votes and buried the real
    fractional OCR reads in _best_ship_id — e.g. SG-8853 winning 196x1.0 over the
    correct SG-9190. Real OCR reads must decide the winner regardless of how many
    frames the wrong provisional guess was carried.
    """
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(21)

    boat = _track('trk_x', camera_id=1)
    # First frame: track carries a wrong provisional guess (no real OCR yet).
    boat.ship_id = 'SG-8853'
    mgr.report_track_update(1, boat, embedding=emb)

    # A real OCR read votes the CORRECT plate once, at true fractional confidence.
    mgr.report_ocr_result(1, 'trk_x', 'SG-9190', 0.87)

    # Now the wrong provisional guess rides along for 200 more frames (identity
    # propagates ship_id back onto the track, which _attach_track would re-vote).
    for _ in range(200):
        boat.ship_id = 'SG-8853'
        mgr.report_track_update(1, boat, embedding=emb)

    gid = mgr.get_global_id(1, 'trk_x')
    assert gid is not None
    identity = mgr._identities[gid]
    # Only the single genuine OCR read should be in the vote pool.
    assert identity.ocr_history == [('SG-9190', 0.87)]
    assert mgr.get_global_ship_id(1, 'trk_x') == 'SG-9190'


def test_seed_ship_id_when_no_ocr_evidence() -> None:
    """When identity has no OCR evidence at all, a track's provisional ship_id
    still seeds identity.ship_id so the overlay shows something — but it is NOT
    written into ocr_history, so a later real OCR read overrides it cleanly."""
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(33)

    boat = _track('trk_seed', camera_id=1)
    boat.ship_id = 'SG-1000'
    mgr.report_track_update(1, boat, embedding=emb)

    gid = mgr.get_global_id(1, 'trk_seed')
    assert gid is not None
    identity = mgr._identities[gid]
    assert identity.ship_id == 'SG-1000'
    assert identity.ocr_history == []  # seeded, not voted

    # A real OCR read of a different plate must win — no synthetic votes to fight.
    mgr.report_ocr_result(1, 'trk_seed', 'SG-2000', 0.80)
    assert identity.ocr_history == [('SG-2000', 0.80)]
    assert mgr.get_global_ship_id(1, 'trk_seed') == 'SG-2000'


def test_handoff_inherits_plate_after_source_track_removed() -> None:
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(11)

    boat_a = _track('trk_cam1', camera_id=1)
    mgr.report_track_update(1, boat_a, embedding=emb)
    mgr.report_ocr_result(1, 'trk_cam1', 'SG-1111', 0.92)
    mgr.report_track_removed(1, boat_a, ocr_history=[('SG-1111', 0.92)])

    boat_b = _track('trk_cam2', camera_id=2)
    mgr.report_track_update(2, boat_b, embedding=emb)

    assert mgr.get_global_ship_id(2, 'trk_cam2') == 'SG-1111'


def test_adjacent_same_plate_merges_when_both_cameras_active() -> None:
    mgr = CrossCameraReIdManager([5, 6], visual_threshold=0.9, handoff_window_sec=60.0)

    mgr.report_track_update(5, _track('trk_x', camera_id=5))
    mgr.report_ocr_result(5, 'trk_x', 'SG-6375', 0.9)

    mgr.report_track_update(6, _track('trk_y', camera_id=6))
    mgr.report_ocr_result(6, 'trk_y', 'SG-6375', 0.88)

    gid_x = mgr._track_to_global[(5, 'trk_x')]
    gid_y = mgr._track_to_global[(6, 'trk_y')]
    assert gid_x == gid_y


def test_same_plate_not_merged_on_non_adjacent_cameras() -> None:
    mgr = CrossCameraReIdManager([1, 2, 3], visual_threshold=0.9, handoff_window_sec=60.0)

    mgr.report_track_update(1, _track('trk_a', camera_id=1))
    mgr.report_ocr_result(1, 'trk_a', 'SG-6375', 0.9)

    mgr.report_track_update(3, _track('trk_c', camera_id=3))
    mgr.report_ocr_result(3, 'trk_c', 'SG-6375', 0.88)

    gid_a = mgr._track_to_global[(1, 'trk_a')]
    gid_c = mgr._track_to_global[(3, 'trk_c')]
    assert gid_a != gid_c


def test_same_plate_not_merged_on_same_camera_concurrent_tracks() -> None:
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.9, handoff_window_sec=60.0)

    mgr.report_track_update(1, _track('trk_one', camera_id=1, box=(10.0, 10.0, 80.0, 80.0)))
    mgr.report_ocr_result(1, 'trk_one', 'SG-6375', 0.9)

    mgr.report_track_update(1, _track('trk_two', camera_id=1, box=(200.0, 200.0, 280.0, 280.0)))
    mgr.report_ocr_result(1, 'trk_two', 'SG-6375', 0.88)

    gid_one = mgr._track_to_global[(1, 'trk_one')]
    gid_two = mgr._track_to_global[(1, 'trk_two')]
    assert gid_one != gid_two


def test_embedding_match_not_merged_on_same_camera_concurrent_tracks() -> None:
    """Reproduces SG-8271 / SG-10447 (2026-07-07 07:58:39).

    Two look-alike boats on the SAME camera, seen concurrently. The second boat
    has not been OCR-read yet, so the ship-id conflict guard cannot fire. Its
    embedding cosine to the first identity clears the visual threshold. Without
    the same-camera concurrency guard the two collapse into one global id and
    one detection (SG-10447) is lost. Two live bboxes on one camera are always
    two boats, so they must keep separate identities.
    """
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(7)

    # Boat A on cam1, OCR-confirmed SG-8271.
    boat_a = _track('trk_8271', camera_id=1, box=(10.0, 10.0, 100.0, 100.0))
    mgr.report_track_update(1, boat_a, embedding=emb)
    mgr.report_ocr_result(1, 'trk_8271', 'SG-8271', 0.95)

    # Boat B appears on the SAME cam1 concurrently, near-identical hull, NO OCR yet.
    boat_b = _track('trk_10447', camera_id=1, box=(300.0, 300.0, 400.0, 400.0))
    similar_emb = emb * 0.98 + _unit_embedding(99) * 0.02
    mgr.report_track_update(1, boat_b, embedding=similar_emb)

    gid_a = mgr._track_to_global[(1, 'trk_8271')]
    gid_b = mgr._track_to_global[(1, 'trk_10447')]
    assert gid_a != gid_b
    # B must not inherit A's plate.
    assert mgr.get_global_ship_id(1, 'trk_10447') is None
    assert boat_b.ship_id is None

    # After B is OCR-read as its own plate, the two identities stay distinct.
    mgr.report_ocr_result(1, 'trk_10447', 'SG-10447', 0.9)
    assert mgr._identities[gid_a].ship_id == 'SG-8271'
    assert mgr._identities[gid_b].ship_id == 'SG-10447'


def test_same_camera_reattach_after_removed_still_works() -> None:
    """Guard must not block legit same-camera re-id: when the first track is
    REMOVED (IoU tracker dropped it), it leaves active_tracks, so a reappearing
    track with a matching embedding on the same camera can rebind. Only *live*
    concurrent tracks are two boats.
    """
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(11)

    boat_a = _track('trk_first', camera_id=1)
    mgr.report_track_update(1, boat_a, embedding=emb)
    mgr.report_ocr_result(1, 'trk_first', 'SG-1111', 0.92)
    gid_first = mgr._track_to_global[(1, 'trk_first')]

    # Tracker drops the track (no active track left on cam1).
    mgr.report_track_removed(1, boat_a, ocr_history=[('SG-1111', 0.92)])

    # Same boat reappears on the SAME camera with a matching embedding, no OCR.
    boat_b = _track('trk_reappear', camera_id=1)
    mgr.report_track_update(1, boat_b, embedding=emb)

    gid_reappear = mgr._track_to_global[(1, 'trk_reappear')]
    assert gid_reappear == gid_first
    assert mgr.get_global_ship_id(1, 'trk_reappear') == 'SG-1111'


def test_finalize_once_after_adjacent_seam_merge() -> None:
    finalized: list[str] = []

    def on_removed(track, _hist):
        finalized.append(str(track.track_id))

    mgr = CrossCameraReIdManager(
        [5, 6],
        visual_threshold=0.9,
        handoff_window_sec=60.0,
        on_global_track_removed=on_removed,
    )

    boat_x = _track('trk_x', camera_id=5)
    boat_y = _track('trk_y', camera_id=6)
    mgr.report_track_update(5, boat_x)
    mgr.report_ocr_result(5, 'trk_x', 'SG-1234', 0.9)
    mgr.report_track_update(6, boat_y)
    mgr.report_ocr_result(6, 'trk_y', 'SG-1234', 0.88)

    gid = mgr._track_to_global[(5, 'trk_x')]
    assert mgr._track_to_global[(6, 'trk_y')] == gid

    identity = mgr._identities[gid]
    identity.berth_in_ts = time.time() - 60
    identity.berth_out_ts = time.time()

    mgr.report_track_removed(5, boat_x, ocr_history=[('SG-1234', 0.9)])
    mgr.report_track_removed(6, boat_y, ocr_history=[('SG-1234', 0.88)])

    assert len(finalized) == 1
    assert finalized[0].startswith('gid_')


def test_embedding_match_rejected_when_ship_ids_conflict() -> None:
    """Over-merge guard: a track with a valid plate must not merge into an
    identity holding a *different* valid plate, even at high cosine score.

    Reproduces BD-0422/SG-6047: distinct boats reach cosine ~0.88 which clears
    the 0.6 threshold. Without the ship-id conflict guard they collapse into one
    global id and one detection is lost.
    """
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(7)

    # Identity A on cam1, OCR-confirmed as SG-6047.
    boat_a = _track('trk_a', camera_id=1)
    mgr.report_track_update(1, boat_a, embedding=emb)
    mgr.report_ocr_result(1, 'trk_a', 'SG-6047', 0.95)

    # Track B on adjacent cam2 with a near-identical embedding but a DIFFERENT
    # confirmed plate. It must get its own identity, not merge into A.
    boat_b = _track('trk_b', camera_id=2, box=(200.0, 200.0, 320.0, 320.0))
    similar_emb = emb * 0.98 + _unit_embedding(99) * 0.02
    boat_b.ship_id = 'BD-0422'
    mgr.report_track_update(2, boat_b, embedding=similar_emb)
    mgr.report_ocr_result(2, 'trk_b', 'BD-0422', 0.93)

    gid_a = mgr._track_to_global[(1, 'trk_a')]
    gid_b = mgr._track_to_global[(2, 'trk_b')]
    assert gid_a != gid_b
    assert mgr._identities[gid_a].ship_id == 'SG-6047'
    assert mgr._identities[gid_b].ship_id == 'BD-0422'


def test_embedding_match_still_works_when_incoming_plate_unknown() -> None:
    """Guard must not block legit handoff: an incoming track with no/unknown
    plate can still bind to an existing identity via embedding.
    """
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    emb = _unit_embedding(11)

    boat_a = _track('trk_src', camera_id=1)
    mgr.report_track_update(1, boat_a, embedding=emb)
    mgr.report_ocr_result(1, 'trk_src', 'SG-1111', 0.92)
    mgr.report_track_removed(1, boat_a, ocr_history=[('SG-1111', 0.92)])

    # No OCR on the reappearing track — pure embedding handoff must succeed.
    boat_b = _track('trk_dst', camera_id=2)
    mgr.report_track_update(2, boat_b, embedding=emb)

    assert mgr.get_global_ship_id(2, 'trk_dst') == 'SG-1111'


def test_directional_fallback_rejected_when_ship_ids_conflict() -> None:
    """Fallback-path over-merge guard: the directional/overlap matchers score on
    motion/time/embedding only and have NO ship_id check. A track carrying a
    valid plate B must not be handed off into an identity confirmed as plate A,
    even when direction + timing + embedding would otherwise accept the merge.

    This is the leak left after the embedding-branch guard: when that guard
    rejects a conflicting plate it falls through to these fallbacks, which
    previously re-merged the two distinct boats into one gid.
    """
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.99, handoff_window_sec=60.0)
    mgr.set_camera_layout({1: 0.0, 2: 1000.0})
    emb = _unit_embedding(7)

    # Identity A on cam1, OCR-confirmed SG-6047, moving RIGHT toward the cam2 seam.
    boat_a = _track('trk_a', camera_id=1, box=(900.0, 100.0, 980.0, 200.0))
    boat_a.velocity = (30.0, 0.0)
    mgr.report_track_update(1, boat_a, embedding=emb, frame_shape=(360, 1000))
    mgr.report_ocr_result(1, 'trk_a', 'SG-6047', 0.95)

    # Track B appears at cam2's left edge shortly after, near-identical embedding
    # (would clear the directional floor) but a DIFFERENT confirmed plate.
    boat_b = _track('trk_b', camera_id=2, box=(10.0, 100.0, 70.0, 200.0))
    boat_b.velocity = (30.0, 0.0)
    boat_b.ship_id = 'BD-0422'
    similar_emb = emb * 0.99 + _unit_embedding(99) * 0.01
    mgr.report_track_update(2, boat_b, embedding=similar_emb, frame_shape=(360, 1000))
    mgr.report_ocr_result(2, 'trk_b', 'BD-0422', 0.93)

    gid_a = mgr._track_to_global[(1, 'trk_a')]
    gid_b = mgr._track_to_global[(2, 'trk_b')]
    assert gid_a != gid_b
    assert mgr._identities[gid_a].ship_id == 'SG-6047'
    assert mgr._identities[gid_b].ship_id == 'BD-0422'


def test_identity_ship_id_conflicts_helper() -> None:
    """Unit: the fallback pre-filter predicate only rejects a *different* valid plate."""
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    identity = mgr._create_empty_identity(1, 'trk')

    identity.ship_id = 'SG-6047'
    assert mgr._identity_ship_id_conflicts(identity, 'BD-0422') is True
    assert mgr._identity_ship_id_conflicts(identity, 'SG-6047') is False
    # Incoming unknown/empty → never a conflict (must allow OCR-less handoff).
    assert mgr._identity_ship_id_conflicts(identity, '') is False
    assert mgr._identity_ship_id_conflicts(identity, 'UNKNOWN') is False
    # Identity has no valid plate → never a conflict.
    identity.ship_id = None
    assert mgr._identity_ship_id_conflicts(identity, 'BD-0422') is False


def test_get_global_id_returns_gid_after_track_report() -> None:
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    boat = _track('trk_gid', camera_id=1)
    mgr.report_track_update(1, boat, embedding=_unit_embedding(42))

    global_id = mgr.get_global_id(1, 'trk_gid')
    assert global_id is not None
    assert global_id.startswith('gid_')


def test_finalized_identities_are_purged_after_retention() -> None:
    """RAM leak guard: finalized identities + track maps must be evicted."""
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=1.0)
    # Shrink retention so the test does not wait minutes.
    mgr._finalized_retention_sec = 0.0

    boat = _track('trk_purge', camera_id=1)
    mgr.report_track_update(1, boat, embedding=_unit_embedding(11))
    assert len(mgr._identities) == 1
    assert len(mgr._track_to_global) == 1

    # Remove the track and let it finalize (no active tracks, not anchored).
    mgr.report_track_removed(1, boat)
    # Force the expiry sweep well past the handoff window.
    mgr._flush_expired_locked(time.time() + 10.0)

    assert len(mgr._identities) == 0
    assert len(mgr._track_to_global) == 0


def test_ocr_history_is_capped() -> None:
    """RAM leak guard: ocr_history must not grow without bound."""
    from app.services.ai.cross_camera_reid import _MAX_OCR_HISTORY

    mgr = CrossCameraReIdManager([1], visual_threshold=0.5, handoff_window_sec=60.0)
    mgr.report_track_update(1, _track('trk_hist', camera_id=1), embedding=_unit_embedding(5))
    for _ in range(_MAX_OCR_HISTORY + 50):
        mgr.report_ocr_result(1, 'trk_hist', 'SG-6375', 0.9)

    identity = mgr._identity_for_track((1, 'trk_hist'))
    assert identity is not None
    assert len(identity.ocr_history) <= _MAX_OCR_HISTORY


def test_track_local_berth_in_propagates_to_identity() -> None:
    """Seed-inside path: a track sets berth_in_ts WITHOUT emitting an 'in'
    crossing (boat appeared already inside the zone). _attach_track must lift
    that timestamp onto the identity, otherwise berth_in stays None → the track
    is dropped at persist (min_berth gate) or the IN time is stamped late."""
    mgr = CrossCameraReIdManager([1], visual_threshold=0.5, handoff_window_sec=60.0)
    boat = _track('trk_seed', camera_id=1)
    # No report_boundary_crossing('in') is ever called — mimic seed-inside.
    boat.berth_in_ts = boat.first_seen_ts
    mgr.report_track_update(1, boat, embedding=_unit_embedding(21))

    identity = mgr._identity_for_track((1, 'trk_seed'))
    assert identity is not None
    assert identity.berth_in_ts == boat.first_seen_ts
    assert identity.berth_in_camera_id == 1


def test_track_local_berth_in_keeps_earliest() -> None:
    """When both a track-local berth_in and a later crossing exist, the identity
    keeps the EARLIEST — the true arrival, not the late line-cross."""
    mgr = CrossCameraReIdManager([1], visual_threshold=0.5, handoff_window_sec=60.0)
    boat = _track('trk_early', camera_id=1)
    early = boat.first_seen_ts
    late = early + 300.0

    # A late 'in' crossing lands first (the buggy real-world order).
    mgr.report_boundary_crossing(1, 'trk_early', 'in', late)
    # Then the per-frame update carries the true (earlier) arrival.
    boat.berth_in_ts = early
    mgr.report_track_update(1, boat, embedding=_unit_embedding(22))

    identity = mgr._identity_for_track((1, 'trk_early'))
    assert identity is not None
    assert identity.berth_in_ts == early


def test_track_local_berth_in_not_reopened_after_departure() -> None:
    """Reverse-motion guard: once berth_out_ts is set (boat departed), a
    seed-inside re-touch on another camera must NOT resurrect berth_in."""
    mgr = CrossCameraReIdManager([1], visual_threshold=0.5, handoff_window_sec=60.0)
    boat = _track('trk_rev', camera_id=1)
    t0 = boat.first_seen_ts
    mgr.report_boundary_crossing(1, 'trk_rev', 'in', t0)
    mgr.report_boundary_crossing(1, 'trk_rev', 'out', t0 + 100.0)

    identity = mgr._identity_for_track((1, 'trk_rev'))
    assert identity is not None
    berth_in_before = identity.berth_in_ts

    # Boat backs out and clips the zone again → seed-inside sets a new berth_in_ts.
    boat.berth_in_ts = t0 + 200.0
    mgr.report_track_update(1, boat, embedding=_unit_embedding(23))

    assert identity.berth_in_ts == berth_in_before


def test_visual_diag_rejects_track_on_far_edge_of_last_camera() -> None:
    """Overlay leak repro: the `REID vis` diagnostic line compared the incoming
    track's embedding against ANY adjacent-camera identity regardless of where
    the track sat in the frame. A boat parked at the far-right edge of the last
    camera (which can never overlap a boat on the first camera — the seam is on
    its LEFT edge) showed `REID vis x/y ->#gid/<plate>` naming that first-camera
    boat. The visual branch must apply the SAME seam-zone gate the real overlap
    matcher uses, so it stays in sync and never names an impossible target.
    """
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    mgr.set_camera_layout({1: 0.0, 2: 1000.0})
    emb = _unit_embedding(7)

    # Identity A lives on cam1 (the "first" camera), OCR-confirmed.
    boat_a = _track('trk_a', camera_id=1, box=(900.0, 100.0, 980.0, 200.0))
    mgr.report_track_update(1, boat_a, embedding=emb, frame_shape=(360, 1000))
    mgr.report_ocr_result(1, 'trk_a', 'SG-6047', 0.95)

    # Track B on cam2 (the "last" camera) at its FAR-RIGHT edge — the opposite
    # side from the cam1 seam (which is cam2's left edge). Near-identical
    # embedding, so only geometry can reject it. Report it first (as the real
    # pipeline does every frame) so cam2's frame width is known to the seam gate.
    boat_b = _track('trk_b', camera_id=2, box=(930.0, 100.0, 990.0, 200.0))
    similar_emb = emb * 0.99 + _unit_embedding(99) * 0.01
    norm_emb = similar_emb / np.linalg.norm(similar_emb)
    mgr.report_track_update(2, boat_b, embedding=norm_emb, frame_shape=(360, 1000))
    diag = mgr.diagnose_track(2, boat_b, norm_emb, time.time())

    # Seam-zone gate must drop A → no visual target, no leaked plate on overlay.
    assert diag['visual']['target_gid'] is None
    assert diag['visual']['target_ship_id'] is None


def test_visual_diag_accepts_track_on_seam_edge() -> None:
    """Complement to the far-edge repro: a track sitting in the seam-facing edge
    zone (cam2's LEFT edge, bordering cam1) SHOULD surface the adjacent identity
    as the visual target — the gate rejects only impossible geometry, not valid
    seam comparisons.
    """
    mgr = CrossCameraReIdManager([1, 2], visual_threshold=0.5, handoff_window_sec=60.0)
    mgr.set_camera_layout({1: 0.0, 2: 1000.0})
    emb = _unit_embedding(7)

    boat_a = _track('trk_a', camera_id=1, box=(900.0, 100.0, 980.0, 200.0))
    mgr.report_track_update(1, boat_a, embedding=emb, frame_shape=(360, 1000))
    mgr.report_ocr_result(1, 'trk_a', 'SG-6047', 0.95)

    # Track B at cam2's LEFT edge = the seam bordering cam1.
    boat_b = _track('trk_b', camera_id=2, box=(10.0, 100.0, 70.0, 200.0))
    similar_emb = emb * 0.99 + _unit_embedding(99) * 0.01
    diag = mgr.diagnose_track(
        2, boat_b, similar_emb / np.linalg.norm(similar_emb), time.time()
    )

    gid_a = mgr._track_to_global[(1, 'trk_a')]
    assert diag['visual']['target_gid'] == gid_a
    assert diag['visual']['target_ship_id'] == 'SG-6047'

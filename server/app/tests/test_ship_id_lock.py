import time

import numpy as np

from app.services.ai.boat_tracker import BoatTracker, TrackState, TrackedBoat
from app.services.ai.ship_id_lock import (
    effective_ship_id,
    is_track_identity_locked,
    tracks_open_for_recognition,
    update_ship_id_stability,
    update_tracks_ship_id_stability,
)


def _track(ship_id: str | None = 'BD-0001', *, state: TrackState = TrackState.CONFIRMED) -> TrackedBoat:
    return TrackedBoat(
        track_id='t1',
        state=state,
        box=np.array([10, 10, 50, 50], dtype=np.float32),
        conf=0.9,
        hits=3,
        misses=0,
        first_seen_ts=1.0,
        last_seen_ts=2.0,
        ship_id=ship_id,
    )


def test_id_change_resets_stability_timer():
    track = _track('BD-0001')
    track.ship_id_stable_candidate = 'BD-0001'
    track.ship_id_stable_since_ts = 100.0

    update_ship_id_stability(track, lock_sec=60.0, now=120.0)
    assert track.ship_id_locked is False
    assert track.ship_id_stable_since_ts == 100.0

    track.ship_id = 'BD-0002'
    update_ship_id_stability(track, lock_sec=60.0, now=130.0)
    assert track.ship_id_locked is False
    assert track.ship_id_stable_candidate == 'BD-0002'
    assert track.ship_id_stable_since_ts == 130.0


def test_stable_id_for_lock_sec_triggers_lock():
    track = _track('BD-0042')
    update_ship_id_stability(track, lock_sec=60.0, now=0.0)
    update_ship_id_stability(track, lock_sec=60.0, now=59.9)
    assert track.ship_id_locked is False

    update_ship_id_stability(track, lock_sec=60.0, now=60.0)
    assert track.ship_id_locked is True
    assert track.ship_id_locked_value == 'BD-0042'
    assert track.ship_id == 'BD-0042'


def test_lock_sec_zero_disables_locking():
    track = _track('BD-0001')
    update_ship_id_stability(track, lock_sec=0.0, now=10_000.0)
    assert track.ship_id_locked is False


def test_unknown_ship_id_does_not_lock():
    track = _track('UNKNOWN')
    update_ship_id_stability(track, lock_sec=60.0, now=120.0)
    assert track.ship_id_locked is False
    assert track.ship_id_stable_candidate is None


def test_effective_ship_id_prefers_locked_value():
    track = _track('BD-OLD')
    track.ship_id_locked = True
    track.ship_id_locked_value = 'BD-LOCKED'
    track.ship_id = 'BD-OLD'
    assert effective_ship_id(track) == 'BD-LOCKED'


def test_tracks_open_for_recognition_excludes_locked():
    open_track = _track('BD-0001')
    locked_track = _track('BD-0002')
    locked_track.ship_id_locked = True
    locked_track.ship_id_locked_value = 'BD-0002'

    open_list = tracks_open_for_recognition([open_track, locked_track])
    assert open_list == [open_track]
    assert is_track_identity_locked(locked_track) is True


def test_update_tracks_skips_tentative():
    tentative = _track('BD-0001', state=TrackState.TENTATIVE)
    update_tracks_ship_id_stability([tentative], lock_sec=60.0, now=0.0)
    assert tentative.ship_id_stable_candidate is None


def test_add_ocr_vote_ignored_when_locked():
    tracker = BoatTracker(min_hits=1, max_tentative_misses=1, max_lost_frames=1)
    track = _track('BD-LOCKED')
    track.ship_id_locked = True
    track.ship_id_locked_value = 'BD-LOCKED'
    tracker._tracks['t1'] = track

    tracker.add_ocr_vote('t1', 'BD-OTHER', 0.99)
    assert track.ship_id == 'BD-LOCKED'
    assert tracker.get_ocr_history('t1') == []


def test_tracker_update_ship_id_stability_persists_lock():
    tracker = BoatTracker(min_hits=1, max_tentative_misses=1, max_lost_frames=1)
    tracks = tracker.update([np.array([10, 10, 50, 50], dtype=np.float32)], [0.9], ts=0.0)
    tracker.add_ocr_vote(tracks[0].track_id, 'BD-0001', 1.0)
    tracker.add_ocr_vote(tracks[0].track_id, 'BD-0001', 1.0)

    tracker.update([np.array([10, 10, 50, 50], dtype=np.float32)], [0.9], ts=1.0)
    tracker.update_ship_id_stability(lock_sec=1.0, now=1.0)
    tracker.update_ship_id_stability(lock_sec=1.0, now=2.0)

    live_track = tracker.get_track(tracks[0].track_id)
    assert live_track is not None
    assert live_track.ship_id_locked is True
    assert live_track.ship_id_locked_value == 'BD-0001'

    next_tracks = tracker.update([np.array([10, 10, 50, 50], dtype=np.float32)], [0.9], ts=3.0)
    assert next_tracks[0].ship_id_locked is True
    assert next_tracks[0].ship_id_locked_value == 'BD-0001'


def test_embedding_wrong_pool_does_not_override_repeated_ocr():
    tracker = BoatTracker(min_hits=1, max_tentative_misses=1, max_lost_frames=1)
    tracks = tracker.update([np.array([10, 10, 50, 50], dtype=np.float32)], [0.9], ts=0.0)
    track_id = tracks[0].track_id

    tracker.add_ocr_vote(track_id, 'BD-0001', 0.70)
    tracker.add_ocr_vote(track_id, 'BD-0001', 0.70)
    tracker.add_embedding_vote(track_id, 'BD-9999', 0.80)
    tracker.add_embedding_vote(track_id, 'BD-9999', 0.82)
    tracker.add_embedding_vote(track_id, 'BD-9999', 0.81)
    tracker.update([np.array([10, 10, 50, 50], dtype=np.float32)], [0.9], ts=1.0)

    tracker.update_ship_id_stability(lock_sec=1.0, now=1.0)
    tracker.update_ship_id_stability(lock_sec=1.0, now=2.0)

    live_track = tracker.get_track(track_id)
    assert live_track is not None
    assert live_track.ship_id_locked is True
    assert live_track.ship_id_locked_value == 'BD-0001'


def test_single_wrong_ocr_does_not_block_strong_embedding_lock():
    tracker = BoatTracker(min_hits=1, max_tentative_misses=1, max_lost_frames=1)
    tracks = tracker.update([np.array([10, 10, 50, 50], dtype=np.float32)], [0.9], ts=0.0)
    track_id = tracks[0].track_id

    tracker.add_ocr_vote(track_id, 'BD-WRONG', 0.90)
    tracker.add_embedding_vote(track_id, 'BD-0002', 0.80)
    tracker.add_embedding_vote(track_id, 'BD-0002', 0.82)
    tracker.add_embedding_vote(track_id, 'BD-0002', 0.81)
    tracker.update([np.array([10, 10, 50, 50], dtype=np.float32)], [0.9], ts=1.0)

    tracker.update_ship_id_stability(lock_sec=1.0, now=1.0)
    tracker.update_ship_id_stability(lock_sec=1.0, now=2.0)

    live_track = tracker.get_track(track_id)
    assert live_track is not None
    assert live_track.ship_id_locked is True
    assert live_track.ship_id_locked_value == 'BD-0002'


def test_locked_track_ignores_embedding_vote():
    tracker = BoatTracker(min_hits=1, max_tentative_misses=1, max_lost_frames=1)
    track = _track('BD-LOCKED')
    track.ship_id_locked = True
    track.ship_id_locked_value = 'BD-LOCKED'
    tracker._tracks['t1'] = track

    tracker.add_embedding_vote('t1', 'BD-OTHER', 0.99)
    assert track.ship_id == 'BD-LOCKED'


def test_global_ship_id_cannot_override_local_final_evidence():
    tracker = BoatTracker(min_hits=1, max_tentative_misses=1, max_lost_frames=1)
    tracks = tracker.update([np.array([10, 10, 50, 50], dtype=np.float32)], [0.9], ts=0.0)
    track_id = tracks[0].track_id

    tracker.add_ocr_vote(track_id, 'SG-7044', 0.90)
    tracker.update_track_metadata(track_id, ship_id='VF-20053')

    live_track = tracker.get_track(track_id)
    assert live_track is not None
    assert live_track.ship_id == 'SG-7044'
    assert live_track.last_known_ship_id == 'SG-7044'
    assert live_track.ship_id_decision_source == 'ocr'

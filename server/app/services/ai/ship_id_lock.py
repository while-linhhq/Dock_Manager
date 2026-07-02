"""Per-track ship ID stability lock — stop OCR/visual after ID is stable."""
from __future__ import annotations

from collections.abc import Callable, Sequence

from app.services.ai.boat_tracker import TrackedBoat, TrackState
from app.services.ship_id_utils import is_unknown_ship_id


def effective_ship_id(track: TrackedBoat) -> str | None:
    if track.ship_id_locked and track.ship_id_locked_value:
        return track.ship_id_locked_value
    return track.ship_id


def is_track_identity_locked(track: TrackedBoat) -> bool:
    return bool(track.ship_id_locked)


def _normalize_ship_id(ship_id: str | None) -> str | None:
    if not ship_id:
        return None
    normalized = str(ship_id).strip().upper()
    return normalized or None


def is_lockable_ship_id(
    ship_id: str | None,
    *,
    catalog_is_known: Callable[[str], bool] | None = None,
) -> bool:
    normalized = _normalize_ship_id(ship_id)
    if not normalized or is_unknown_ship_id(normalized):
        return False
    if catalog_is_known is not None and not catalog_is_known(normalized):
        return False
    return True


def _reset_stability(track: TrackedBoat) -> None:
    track.ship_id_stable_candidate = None
    track.ship_id_stable_since_ts = None


def _apply_locked_ship_id(track: TrackedBoat) -> None:
    locked_value = _normalize_ship_id(track.ship_id_locked_value)
    if not locked_value:
        return
    track.ship_id = locked_value
    track.last_known_ship_id = locked_value


def update_ship_id_stability(
    track: TrackedBoat,
    *,
    lock_sec: float,
    now: float,
    catalog_is_known: Callable[[str], bool] | None = None,
) -> None:
    if track.ship_id_locked:
        _apply_locked_ship_id(track)
        return
    if lock_sec <= 0:
        return

    decision_state = getattr(track, 'ship_id_decision_state', None)
    if decision_state in {'conflict', 'none'}:
        _reset_stability(track)
        return
    if decision_state == 'provisional':
        _reset_stability(track)
        return

    current_id = _normalize_ship_id(track.ship_id)
    if not is_lockable_ship_id(current_id, catalog_is_known=catalog_is_known):
        _reset_stability(track)
        return

    if current_id != track.ship_id_stable_candidate:
        track.ship_id_stable_candidate = current_id
        track.ship_id_stable_since_ts = now
        return

    stable_since = track.ship_id_stable_since_ts
    if stable_since is None:
        track.ship_id_stable_since_ts = now
        return

    if now - stable_since >= lock_sec:
        track.ship_id_locked = True
        track.ship_id_locked_value = current_id
        _apply_locked_ship_id(track)


def tracks_open_for_recognition(tracks: Sequence[TrackedBoat]) -> list[TrackedBoat]:
    return [track for track in tracks if not is_track_identity_locked(track)]


def update_tracks_ship_id_stability(
    tracks: Sequence[TrackedBoat],
    *,
    lock_sec: float,
    now: float,
    catalog_is_known: Callable[[str], bool] | None = None,
) -> None:
    for track in tracks:
        if track.ship_id_locked:
            update_ship_id_stability(
                track,
                lock_sec=lock_sec,
                now=now,
                catalog_is_known=catalog_is_known,
            )
            continue
        if track.state != TrackState.CONFIRMED:
            continue
        update_ship_id_stability(
            track,
            lock_sec=lock_sec,
            now=now,
            catalog_is_known=catalog_is_known,
        )

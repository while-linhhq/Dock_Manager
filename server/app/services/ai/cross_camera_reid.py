from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import numpy as np

from app.services.ai.boat_tracker import TrackedBoat
from app.services.ai.embedding_extractor import cosine_similarity, normalize_embedding
from app.services.ai.handoff_matcher import OverlapMergeConfig, OverlapMergeMatcher
from app.services.ai.directional_handoff import (
    DirectionalHandoffConfig,
    DirectionalHandoffMatcher,
)
from app.services.ship_id_utils import is_unknown_ship_id, normalize_ship_id

if TYPE_CHECKING:
    from app.services.ai.seam_anchor_verifier import SeamAnchorVerifier
    from app.services.ai.ship_id_catalog import ShipIdCatalog


_log = logging.getLogger(__name__)

# Bound per-identity OCR vote history. Only the aggregate score matters for
# _best_ship_id, so unbounded growth is pure RAM waste on long-lived anchors.
_MAX_OCR_HISTORY = 200

TrackKey = tuple[int, str]


def _append_ocr_history(
    history: list[tuple[str, float]],
    entry: tuple[str, float],
) -> None:
    history.append(entry)
    if len(history) > _MAX_OCR_HISTORY:
        del history[: len(history) - _MAX_OCR_HISTORY]


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
    finalized_ts: float = 0.0
    anchored: bool = False
    berth_in_ts: float | None = None
    berth_out_ts: float | None = None
    berth_in_camera_id: int | None = None
    berth_out_camera_id: int | None = None
    events_written: bool = False
    dominant_hsv_history: list[tuple[int, int, int]] = field(default_factory=list)
    vx_history: list[float] = field(default_factory=list)


class CrossCameraReIdManager:
    """
    Merge per-camera tracks into one global vessel identity.

    Matching is intentionally constrained by `camera_order`: visual matching only
    happens between the same camera or adjacent cameras. OCR ship IDs can merge
    identities retroactively because they are stronger semantic evidence.
    """

    def __init__(
        self,
        camera_order: list[int],
        *,
        visual_threshold: float = 0.6,
        handoff_window_sec: float = 30.0,
        primary_zone_ratio: float = 0.8,
        edge_zone_ratio: float = 0.1,
        on_global_track_removed=None,
        seam_anchor_verifier: 'SeamAnchorVerifier | None' = None,
        ship_id_catalog: 'ShipIdCatalog | None' = None,
        is_track_identity_locked: Callable[[int, str], bool] | None = None,
        overlap_merge_config: 'OverlapMergeConfig | None' = None,
        directional_handoff_config: 'DirectionalHandoffConfig | None' = None,
        reverse_motion_guard_enabled: bool = True,
        embedding_diversity_max_cos: float = 0.98,
    ) -> None:
        self._camera_order = [int(camera_id) for camera_id in camera_order]
        self._camera_index = {
            camera_id: index for index, camera_id in enumerate(self._camera_order)
        }
        self._visual_threshold = float(visual_threshold)
        self._handoff_window_sec = float(handoff_window_sec)
        self._primary_zone_ratio = float(np.clip(primary_zone_ratio, 0.2, 1.0))
        self._edge_zone_ratio = float(np.clip(edge_zone_ratio, 0.01, 0.45))
        self._on_global_track_removed = on_global_track_removed
        self._seam_anchor_verifier = seam_anchor_verifier
        self._ship_id_catalog = ship_id_catalog
        self._is_track_identity_locked = is_track_identity_locked
        self._identities: dict[str, GlobalIdentity] = {}
        self._track_to_global: dict[TrackKey, str] = {}
        self._lock = threading.RLock()
        # Retain finalized identities briefly for late merges, then purge to bound RAM.
        self._finalized_retention_sec = max(
            float(self._handoff_window_sec) * 2.0, 120.0
        )
        # Hard backstop: never let the identity table grow unbounded (RAM leak guard).
        self._max_identities = 2000
        self._frame_width_by_camera: dict[int, float] = {}
        self._layout_x_by_camera: dict[int, float] = {}
        self._reverse_motion_guard_enabled = bool(reverse_motion_guard_enabled)
        # Diversity gate for the per-identity embedding buffer. Embeddings are
        # extracted every frame, so 20 raw appends = the last ~1-2s of near-
        # identical poses — a "1 vs 20" match that is really "1 vs 1" repeated.
        # Skip an incoming embedding when it is >= this cosine to the most recent
        # kept one, so the 20 slots hold genuinely distinct poses spread over the
        # track's life (better cross-camera recall). 1.0 disables the gate.
        self._embedding_diversity_max_cos = float(
            np.clip(embedding_diversity_max_cos, 0.5, 1.0)
        )
        self._overlap_matcher = OverlapMergeMatcher(
            overlap_merge_config or OverlapMergeConfig(),
            is_adjacent=self._cameras_are_adjacent_pair,
            frame_width_for=lambda cam: self._frame_width_by_camera.get(int(cam), 0.0),
            layout_x_for=lambda cam: self._layout_x_by_camera.get(int(cam)),
        )
        self._directional_matcher = DirectionalHandoffMatcher(
            directional_handoff_config or DirectionalHandoffConfig(),
            is_adjacent=self._cameras_are_adjacent_pair,
            frame_width_for=lambda cam: self._frame_width_by_camera.get(int(cam), 0.0),
            layout_x_for=lambda cam: self._layout_x_by_camera.get(int(cam)),
        )

    def set_camera_layout(self, layout_x_by_camera: dict[int, float]) -> None:
        """Record per-camera horizontal layout position (from camera-group members).

        Used by the directional handoff matcher to know which camera sits to the
        left/right of which, so a valid sequential handoff requires the source
        track's velocity to point toward the shared border.
        """
        with self._lock:
            self._layout_x_by_camera = {
                int(cam): float(x) for cam, x in (layout_x_by_camera or {}).items()
            }

    def set_is_track_identity_locked(
        self,
        checker: Callable[[int, str], bool] | None,
    ) -> None:
        self._is_track_identity_locked = checker

    def set_seam_anchor_verifier(self, verifier: 'SeamAnchorVerifier | None') -> None:
        self._seam_anchor_verifier = verifier

    def sync_restored_anchors(self, states: list[Any]) -> None:
        """Mark identities restored from DB as anchored so they are not finalized early."""
        with self._lock:
            for state in states:
                global_id = str(state.global_id)
                identity = self._identities.get(global_id)
                if identity is None:
                    identity = GlobalIdentity(
                        global_id=global_id,
                        ship_id=state.ship_id,
                        camera_tracks={int(state.cam_a_id): str(state.track_id)},
                        first_seen_ts=float(state.first_seen_ts),
                        last_seen_ts=float(state.last_seen_ts),
                        primary_camera_id=int(state.cam_a_id),
                        anchored=True,
                        last_track=state.last_track,
                    )
                    if state.embedding is not None:
                        identity.embeddings.append(state.embedding)
                    if state.ocr_history:
                        identity.ocr_history = list(state.ocr_history)
                    if state.berth_in_ts is not None:
                        identity.berth_in_ts = state.berth_in_ts
                    if state.berth_out_ts is not None:
                        identity.berth_out_ts = state.berth_out_ts
                    self._identities[global_id] = identity
                else:
                    identity.anchored = True
                    identity.last_seen_ts = max(
                        identity.last_seen_ts, float(state.last_seen_ts)
                    )
                    if state.last_track is not None:
                        identity.last_track = state.last_track
                    if state.berth_in_ts is not None:
                        identity.berth_in_ts = state.berth_in_ts if identity.berth_in_ts is None else min(identity.berth_in_ts, state.berth_in_ts)
                    if state.berth_out_ts is not None:
                        identity.berth_out_ts = state.berth_out_ts if identity.berth_out_ts is None else max(identity.berth_out_ts, state.berth_out_ts)

    def handle_anchor_release(self, global_id: str, last_seen_ts: float) -> None:
        """SeamAnchorVerifier callback: anchor departed, finalize identity now."""
        with self._lock:
            identity = self._identities.get(str(global_id))
            if identity is None:
                return
            identity.anchored = False
            ts = float(last_seen_ts)
            identity.last_seen_ts = max(identity.last_seen_ts, ts)
            if identity.last_track is not None:
                identity.last_track.last_seen_ts = max(
                    identity.last_track.last_seen_ts, ts
                )
            if not identity.finalized:
                self._finalize_identity_locked(identity)

    def adjacent_camera_ids(self, camera_id: int) -> list[int]:
        camera_key = int(camera_id)
        index = self._camera_index.get(camera_key)
        if index is None:
            return []
        adjacent: list[int] = []
        if index > 0:
            adjacent.append(self._camera_order[index - 1])
        if index + 1 < len(self._camera_order):
            adjacent.append(self._camera_order[index + 1])
        return adjacent

    def report_track_update(
        self,
        camera_id: int,
        track: TrackedBoat,
        embedding: np.ndarray | None = None,
        frame_shape: tuple[int, int] | None = None,
    ) -> str:
        with self._lock:
            now = time.time()
            self._flush_expired_locked(now)
            camera_key = int(camera_id)
            if frame_shape is not None and len(frame_shape) >= 2:
                self._frame_width_by_camera[camera_key] = float(frame_shape[1])
            track_key = (camera_key, str(track.track_id))
            global_id = self._track_to_global.get(track_key)
            identity = self._identities.get(global_id) if global_id else None

            if identity is None and self._seam_anchor_verifier is not None:
                resurrected_id = self._seam_anchor_verifier.try_resurrect(
                    camera_key,
                    track.box,
                    embedding,
                    dominant_hsv=getattr(track, 'dominant_color_hsv', None),
                    ship_id=track.ship_id or track.last_known_ship_id,
                )
                if resurrected_id is not None:
                    identity = self._identities.get(resurrected_id)
                    if identity is not None:
                        identity.anchored = False
                        _log.info(
                            'reid: track reattached via seam anchor global_id=%s '
                            'camera_id=%s track_id=%s',
                            resurrected_id,
                            camera_key,
                            track.track_id,
                        )

            if identity is None:
                identity = self._match_existing_identity(
                    camera_key,
                    track,
                    embedding,
                    now,
                )
                if identity is None:
                    identity = self._create_identity(camera_key, track)
                    _log.info(
                        'reid NEW identity gid=%s cam=%s track=%s ship_id=%s',
                        identity.global_id,
                        camera_key,
                        track.track_id,
                        identity.ship_id or '-',
                    )
                else:
                    score = (
                        self._identity_similarity(identity, embedding)
                        if embedding is not None
                        else 0.0
                    )
                    _log.info(
                        'reid MATCH gid=%s cam=%s track=%s ship_id=%s cosine=%.2f/%.2f',
                        identity.global_id,
                        camera_key,
                        track.track_id,
                        identity.ship_id or '-',
                        score,
                        self._visual_threshold,
                    )

            self._attach_track(identity, camera_key, track, embedding)
            self._track_to_global[track_key] = identity.global_id
            self._update_primary_camera(identity, camera_key, track, frame_shape)
            if (
                not track.ship_id_locked
                and self._should_propagate_ship_id_to_track(identity, track_key, track)
            ):
                track.ship_id = identity.ship_id
                track.last_known_ship_id = identity.ship_id
            return identity.global_id

    def report_ocr_result(
        self,
        camera_id: int,
        track_id: str,
        ship_id: str,
        confidence: float,
    ) -> str:
        if self._is_track_identity_locked is not None and self._is_track_identity_locked(
            int(camera_id),
            str(track_id),
        ):
            track_key = (int(camera_id), str(track_id))
            with self._lock:
                identity = self._identity_for_track(track_key)
                return identity.global_id if identity is not None else ''
        normalized_ship_id = normalize_ship_id(ship_id)
        if not normalized_ship_id or is_unknown_ship_id(normalized_ship_id):
            track_key = (int(camera_id), str(track_id))
            with self._lock:
                identity = self._identity_for_track(track_key)
                return identity.global_id if identity is not None else ''
        if self._ship_id_catalog is not None and not self._ship_id_catalog.is_known(normalized_ship_id):
            track_key = (int(camera_id), str(track_id))
            with self._lock:
                identity = self._identity_for_track(track_key)
                return identity.global_id if identity is not None else ''
        with self._lock:
            camera_key = int(camera_id)
            track_key = (camera_key, str(track_id))
            identity = self._identity_for_track(track_key)
            if identity is None:
                identity = self._create_empty_identity(camera_key, str(track_id))
                self._track_to_global[track_key] = identity.global_id

            prev_ship_id = identity.ship_id
            _append_ocr_history(identity.ocr_history, (normalized_ship_id, float(confidence)))
            identity.ship_id = self._best_ship_id(identity)
            identity.ocr_confirmed_tracks.add(track_key)
            if identity.ship_id != prev_ship_id:
                _log.info(
                    'reid OCR cam=%s track=%s -> ship_id=%s conf=%.2f gid=%s',
                    camera_key,
                    track_id,
                    identity.ship_id,
                    float(confidence),
                    identity.global_id,
                )

            for other in list(self._identities.values()):
                if other.global_id == identity.global_id or other.ship_id != normalized_ship_id:
                    continue
                if not self._may_merge_identities(identity, other):
                    continue
                merged_from = other.global_id
                identity = self._merge_identities(identity, other)
                _log.info(
                    'reid MERGE ship_id=%s kept=%s absorbed=%s',
                    normalized_ship_id,
                    identity.global_id,
                    merged_from,
                )

            return identity.global_id

    def report_track_removed(
        self,
        camera_id: int,
        track: TrackedBoat,
        ocr_history: list[tuple[str, float]] | None = None,
    ) -> str:
        with self._lock:
            camera_key = int(camera_id)
            identity = self._identity_for_track((camera_key, str(track.track_id)))
            if identity is None:
                identity = self._create_identity(camera_key, track)
            self._attach_track(identity, camera_key, track, track.embedding)
            track_key = (camera_key, str(track.track_id))
            if ocr_history:
                for ship_id, confidence in ocr_history:
                    _append_ocr_history(
                        identity.ocr_history,
                        (str(ship_id).strip().upper(), float(confidence)),
                    )
                identity.ship_id = self._best_ship_id(identity)
                identity.ocr_confirmed_tracks.add(track_key)
            identity.active_tracks.discard(track_key)
            identity.removed_tracks.add(track_key)
            identity.last_seen_ts = max(identity.last_seen_ts, float(track.last_seen_ts))
            identity.last_track = track.copy_public()
            should_finalize_now = identity.berth_out_ts is not None

            if (
                not identity.active_tracks
                and not identity.anchored
                and self._seam_anchor_verifier is not None
                and not should_finalize_now
            ):
                last_embedding = (
                    identity.embeddings[-1] if identity.embeddings else track.embedding
                )
                anchored_ok = self._seam_anchor_verifier.try_anchor(
                    global_id=identity.global_id,
                    ship_id=identity.ship_id,
                    track_id=str(track.track_id),
                    camera_id=camera_key,
                    bbox=track.box,
                    embedding=last_embedding,
                    motion_state=track.motion_state,
                    first_seen_ts=identity.first_seen_ts,
                    last_seen_ts=identity.last_seen_ts,
                    ocr_history=identity.ocr_history,
                    last_track=identity.last_track,
                    dominant_color_hsv=getattr(track, 'dominant_color_hsv', None),
                    berth_in_ts=identity.berth_in_ts,
                    berth_out_ts=identity.berth_out_ts,
                )
                if anchored_ok:
                    identity.anchored = True

            if not identity.active_tracks and not identity.anchored and should_finalize_now:
                self._finalize_identity_locked(identity)
                return identity.global_id

            self._flush_expired_locked(time.time())
            return identity.global_id

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
                # Reverse-motion guard: the boat already departed this identity
                # (berth_out_ts set) and is now backing out, clipping a previous
                # camera's zone. This is NOT a new arrival — do not re-open the
                # berth window or fabricate an OUT→IN cycle. Same boat, same
                # identity, no new crossing event.
                if (
                    self._reverse_motion_guard_enabled
                    and identity.berth_out_ts is not None
                ):
                    _log.info(
                        'reid: skip IN crossing for %s on cam=%s — reverse re-touch '
                        'after departure (berth_out_ts already set)',
                        identity.global_id,
                        camera_id,
                    )
                    return
                if identity.berth_in_ts is None:
                    identity.berth_in_ts = ts
                    identity.berth_in_camera_id = int(camera_id)
                elif ts < identity.berth_in_ts:
                    identity.berth_in_ts = ts
                    identity.berth_in_camera_id = int(camera_id)
            elif direction == 'out':
                if identity.berth_in_ts is not None and identity.berth_out_ts is None:
                    identity.berth_out_ts = ts
                    identity.berth_out_camera_id = int(camera_id)
                elif (
                    identity.berth_in_ts is not None
                    and identity.berth_out_ts is not None
                    and ts > identity.berth_out_ts
                ):
                    identity.berth_out_ts = ts
                    identity.berth_out_camera_id = int(camera_id)

    def get_global_ship_id(self, camera_id: int, track_id: str) -> str | None:
        with self._lock:
            track_key = (int(camera_id), str(track_id))
            identity = self._identity_for_track(track_key)
            if identity is None or not identity.ship_id:
                return None
            if not self._track_may_display_ship_id(identity, track_key):
                return None
            return identity.ship_id

    def get_global_id(self, camera_id: int, track_id: str) -> str | None:
        """Return the gid_* identifier for this (camera_id, track_id) pair, or None."""
        with self._lock:
            return self._track_to_global.get((int(camera_id), str(track_id)))

    def diagnose_track(
        self,
        camera_id: int,
        track: TrackedBoat,
        embedding: np.ndarray | None,
        now: float,
    ) -> dict:
        """Debug overlay: live ReID comparison values vs configured thresholds.

        Returns per-signal dicts of the *current* computed score against the
        configured accept threshold, so the operator can tune config while
        watching the preview. Diagnostic only — never mutates identity state.
        """
        with self._lock:
            track_key = (int(camera_id), str(track.track_id))
            own = self._identity_for_track(track_key)
            own_gid = own.global_id if own is not None else None

            visual_best = 0.0
            visual_target: GlobalIdentity | None = None
            if embedding is not None:
                for identity in self._identities.values():
                    if identity.global_id == own_gid:
                        continue
                    if identity.finalized:
                        continue
                    # Match the staleness guard from _match_existing_identity: a
                    # non-anchored identity older than the handoff window can never
                    # be chosen by the real matcher, so it must not appear on the
                    # debug overlay either — otherwise the operator sees a live
                    # "B ~ A 78%" comparison against a boat that departed long ago
                    # and fears an over-merge the matcher would never make.
                    if (
                        not identity.anchored
                        and now - identity.last_seen_ts > self._handoff_window_sec
                    ):
                        continue
                    if not self._is_camera_candidate(int(camera_id), identity):
                        continue
                    # Seam-zone gate — SAME test the real overlap matcher uses.
                    # Without it the visual overlay compared the incoming track's
                    # embedding against ANY adjacent-camera identity regardless of
                    # where the track sits in the frame, so a boat at the far edge
                    # of the last camera showed "REID vis x/y ->#gid/<plate>"
                    # naming a boat from the first camera it can never overlap.
                    # Delegating to the matcher's own gate keeps overlay and match
                    # logic from drifting apart (the recurring root cause).
                    if not self._overlap_matcher._track_in_seam_zone(identity, track):
                        continue
                    score = self._identity_similarity(identity, embedding)
                    if score > visual_best:
                        visual_best = score
                        visual_target = identity

            others = [
                idn for idn in self._identities.values() if idn.global_id != own_gid
            ]
            try:
                overlap = self._overlap_matcher.diagnose(others, track, now)
            except Exception:
                overlap = None
            try:
                directional = self._directional_matcher.diagnose(others, track, now)
            except Exception:
                directional = None

            seam = None
            if self._seam_anchor_verifier is not None and own_gid is not None:
                try:
                    seam = self._seam_anchor_verifier.diagnose(own_gid)
                except Exception:
                    seam = None

            return {
                'own_gid': own_gid,
                'visual': {
                    'score': float(visual_best),
                    'threshold': float(self._visual_threshold),
                    'target_gid': visual_target.global_id if visual_target else None,
                    'target_ship_id': (
                        visual_target.ship_id if visual_target else None
                    ),
                },
                'overlap': overlap,
                'directional': directional,
                'seam': seam,
            }

    def resolve_lookup_track_ids(self, track_id: str) -> list[str]:
        """
        IDs usable for TrackMediaCollector / video registry lookup.
        Persist uses global_id (gid_*); recorder/collector use per-camera trk_*.
        """
        needle = str(track_id)
        with self._lock:
            if needle in self._identities:
                identity = self._identities[needle]
            else:
                identity = None
                for ident in self._identities.values():
                    if needle in ident.camera_tracks.values():
                        identity = ident
                        break
            if identity is None:
                return [needle]
            out: list[str] = []
            for candidate in (identity.global_id, *identity.camera_tracks.values()):
                c = str(candidate)
                if c and c not in out:
                    out.append(c)
            return out

    def flush_all(self) -> None:
        with self._lock:
            for identity in list(self._identities.values()):
                if not identity.finalized:
                    self._finalize_identity_locked(identity)

    def _identity_for_track(self, track_key: TrackKey) -> GlobalIdentity | None:
        global_id = self._track_to_global.get(track_key)
        return self._identities.get(global_id) if global_id else None

    def _create_empty_identity(self, camera_id: int, track_id: str) -> GlobalIdentity:
        now = time.time()
        identity = GlobalIdentity(
            global_id=f'gid_{uuid4().hex}',
            ship_id=None,
            camera_tracks={int(camera_id): str(track_id)},
            first_seen_ts=now,
            last_seen_ts=now,
            primary_camera_id=int(camera_id),
        )
        identity.active_tracks.add((int(camera_id), str(track_id)))
        self._identities[identity.global_id] = identity
        return identity

    def _create_identity(self, camera_id: int, track: TrackedBoat) -> GlobalIdentity:
        identity = GlobalIdentity(
            global_id=f'gid_{uuid4().hex}',
            ship_id=track.ship_id or track.last_known_ship_id,
            camera_tracks={int(camera_id): str(track.track_id)},
            first_seen_ts=float(track.first_seen_ts),
            last_seen_ts=float(track.last_seen_ts),
            primary_camera_id=int(camera_id),
            last_track=track.copy_public(),
        )
        if track.embedding is not None:
            identity.embeddings.append(normalize_embedding(track.embedding))
        identity.active_tracks.add((int(camera_id), str(track.track_id)))
        self._identities[identity.global_id] = identity
        return identity

    def _append_diverse_embedding(
        self,
        identity: GlobalIdentity,
        embedding: np.ndarray,
    ) -> None:
        """Append to the identity buffer only when the pose is distinct enough.

        Embeddings arrive every frame, so a naive append+trim keeps 20 near-
        identical vectors from the last ~1-2s. Drop an incoming vector whose
        cosine to the most recent kept one is >= the diversity ceiling, so the
        20 slots span genuinely different poses over the track's life — which is
        what makes the cross-camera "1 vs many" max-cosine match actually work.
        """
        cap = self._embedding_diversity_max_cos
        if cap < 1.0 and identity.embeddings:
            if cosine_similarity(identity.embeddings[-1], embedding) >= cap:
                # Refresh the latest slot so a static boat still tracks slow
                # drift, but don't grow the buffer with a redundant pose.
                identity.embeddings[-1] = embedding
                return
        identity.embeddings.append(embedding)
        identity.embeddings = identity.embeddings[-20:]

    def _attach_track(
        self,
        identity: GlobalIdentity,
        camera_id: int,
        track: TrackedBoat,
        embedding: np.ndarray | None,
    ) -> None:
        camera_key = int(camera_id)
        track_key = (camera_key, str(track.track_id))
        identity.camera_tracks[camera_key] = str(track.track_id)
        identity.active_tracks.add(track_key)
        identity.removed_tracks.discard(track_key)
        identity.first_seen_ts = min(identity.first_seen_ts or track.first_seen_ts, track.first_seen_ts)
        identity.last_seen_ts = max(identity.last_seen_ts, track.last_seen_ts)
        identity.last_track = track.copy_public()
        # Propagate track-local berth_in vào identity. Một track có thể xác lập
        # berth_in mà KHÔNG phát 'in' crossing — điển hình là track xuất hiện đã
        # nằm trong berth_zone (seed-inside ở BoundaryCrossingTracker), và máy
        # trạng thái CỐ TÌNH nén sự kiện 'in' để tránh berth_in giả trên camera
        # handoff chỉ chứng kiến cảnh RA. Nếu không đồng bộ ở đây, identity.
        # berth_in_ts kẹt None tới khi một 'in' crossing (có thể muộn hơn nhiều
        # phút) mới nổ → hoặc lệch giờ IN, hoặc MẤT detection (berth_in None →
        # chặn suy diễn berth_out → rớt ngưỡng min_berth). Lấy mốc SỚM NHẤT,
        # đúng như first_seen. KHÔNG mở lại sau khi đã RA (reverse-motion guard):
        # berth_out_ts đã set nghĩa là tàu đã đi, seed-inside lúc này là tàu lùi
        # chạm lại vùng camera khác, không phải arrival mới.
        track_berth_in = getattr(track, 'berth_in_ts', None)
        if track_berth_in is not None and identity.berth_out_ts is None:
            if identity.berth_in_ts is None or track_berth_in < identity.berth_in_ts:
                identity.berth_in_ts = float(track_berth_in)
                identity.berth_in_camera_id = camera_key
        if embedding is not None:
            self._append_diverse_embedding(identity, normalize_embedding(embedding))
        hsv = getattr(track, 'dominant_color_hsv', None)
        if hsv is not None:
            identity.dominant_hsv_history.append(tuple(int(v) for v in hsv))
            identity.dominant_hsv_history = identity.dominant_hsv_history[-20:]
        vel = getattr(track, 'velocity', None)
        if vel is not None:
            identity.vx_history.append(float(vel[0]))
            identity.vx_history = identity.vx_history[-10:]
        # Seed identity.ship_id from the track ONLY when the identity has no
        # evidence of its own yet. Do NOT push this into ocr_history: track.ship_id
        # is frequently just a reflection of identity.ship_id (propagated back at
        # report_track_update:306 / update_track_metadata), so appending it as a
        # conf=1.0 "vote" every frame stuffs the ballot — a single provisional guess
        # accumulates hundreds of synthetic 1.0 votes and buries the real fractional
        # OCR reads in _best_ship_id (self-reinforcing phantom identity; e.g. SG-8853
        # winning 196×1.0 over the correct SG-9190). Genuine votes enter with their
        # true confidence via report_ocr_result / report_track_removed.
        track_ship_id = (track.ship_id or track.last_known_ship_id or '').strip().upper()
        if track_ship_id and identity.ship_id is None and not identity.ocr_history:
            identity.ship_id = track_ship_id

    def _match_existing_identity(
        self,
        camera_id: int,
        track: TrackedBoat,
        embedding: np.ndarray | None,
        now: float,
    ) -> GlobalIdentity | None:
        ship_id = (track.ship_id or track.last_known_ship_id or '').strip().upper()
        if ship_id:
            for identity in self._identities.values():
                if identity.ship_id != ship_id:
                    continue
                if not self._allows_ship_id_attach(identity, camera_id):
                    continue
                return identity

        if embedding is None:
            return None

        # Ship-id conflict guard for the embedding-only path: a track carrying a
        # valid OCR ship_id must never be merged into an identity that already
        # holds a *different* valid ship_id, no matter how high the cosine score.
        # Without this, embedding noise (distinct boats reach ~0.86+) merges two
        # different vessels into one global id and one detection is lost.
        incoming_sid = normalize_ship_id(ship_id) if ship_id else ''
        incoming_known = bool(incoming_sid) and not is_unknown_ship_id(incoming_sid)

        best_identity: GlobalIdentity | None = None
        best_score = 0.0
        for identity in self._identities.values():
            if identity.finalized:
                continue
            if self._has_concurrent_active_on_non_adjacent_camera(identity, camera_id):
                continue
            # Same-camera concurrency guard: one camera showing two separate
            # bboxes at the same time is physically two different boats — never
            # one. If this identity already holds a *live* track on the very
            # camera we're matching on, a high embedding cosine (near-identical
            # hulls reach ~0.86+) would wrongly merge them into one global id and
            # drop one detection. The ship_id path already blocks this via
            # _allows_ship_id_attach; the embedding path must too.
            if self._has_active_track_on_camera(identity, camera_id):
                continue
            if not identity.anchored and now - identity.last_seen_ts > self._handoff_window_sec:
                continue
            if not self._is_camera_candidate(camera_id, identity):
                continue
            if incoming_known:
                identity_sid = normalize_ship_id(identity.ship_id or '')
                if (
                    identity_sid
                    and not is_unknown_ship_id(identity_sid)
                    and identity_sid != incoming_sid
                ):
                    continue
            score = self._identity_similarity(identity, embedding)
            if score > best_score:
                best_score = score
                best_identity = identity

        if best_identity is not None and best_score >= self._visual_threshold:
            return best_identity

        # Ship-id conflict guard also applies to the directional/overlap fallback
        # matchers below. Those matchers score on motion/time/embedding only and
        # have NO ship_id check, so without pre-filtering, a track carrying a
        # valid plate B could still be merged into a plate-A identity — the exact
        # "2 tàu OCR ra 2 mã khác nhau nhưng bị gộp 1 gid" over-merge. Drop any
        # identity holding a different valid plate from the candidate list handed
        # to both fallbacks.
        # Same-camera concurrency guard (see _has_active_track_on_camera): the
        # directional / overlap fallbacks score on motion/time only and have no
        # camera-occupancy check, so an identity already live on this camera
        # must be dropped here too — otherwise the guard above is bypassed.
        fallback_candidates = [
            identity
            for identity in self._identities.values()
            if not self._has_active_track_on_camera(identity, camera_id)
        ]
        if incoming_known:
            fallback_candidates = [
                identity
                for identity in fallback_candidates
                if not self._identity_ship_id_conflicts(identity, incoming_sid)
            ]

        # Step 3.5: directional sequential handoff — boat left an adjacent camera
        # heading toward the shared border and reappears here after a plausible
        # transit gap. Covers OCR-less handoff that overlap merge (concurrent-only)
        # cannot. Reverse re-touch (boat backing out) is rejected by the direction
        # gate because its velocity points away from the border.
        try:
            directional_gid = self._directional_matcher.best_match(
                fallback_candidates,
                track,
                now,
            )
        except Exception:
            _log.exception('reid: directional handoff matcher failed')
            directional_gid = None
        if directional_gid is not None:
            return self._identities.get(directional_gid)

        # Step 4: overlap merge (weak fusion signal) — boat seen concurrently on
        # an adjacent overlapping-FOV camera, no strong embedding / OCR.
        try:
            overlap_gid = self._overlap_matcher.best_match(
                fallback_candidates,
                track,
                now,
            )
        except Exception:
            _log.exception('reid: overlap merge matcher failed')
            overlap_gid = None
        if overlap_gid is not None:
            return self._identities.get(overlap_gid)

        return None

    def _identity_ship_id_conflicts(
        self,
        identity: GlobalIdentity,
        incoming_sid: str,
    ) -> bool:
        """True when the identity holds a *different* valid plate than incoming.

        Used to keep the directional / overlap fallback matchers from merging a
        track carrying plate B into an identity already confirmed as plate A.
        """
        if not incoming_sid or is_unknown_ship_id(incoming_sid):
            return False
        identity_sid = normalize_ship_id(identity.ship_id or '')
        if not identity_sid or is_unknown_ship_id(identity_sid):
            return False
        return identity_sid != incoming_sid

    def _is_camera_candidate(self, camera_id: int, identity: GlobalIdentity) -> bool:
        candidate_cameras = {int(camera_id), *self.adjacent_camera_ids(camera_id)}
        return any(cam in candidate_cameras for cam in identity.camera_tracks)

    def _identity_similarity(self, identity: GlobalIdentity, embedding: np.ndarray) -> float:
        if not identity.embeddings:
            return 0.0
        return max(cosine_similarity(existing, embedding) for existing in identity.embeddings)

    def _merge_identities(
        self,
        keep: GlobalIdentity,
        other: GlobalIdentity,
    ) -> GlobalIdentity:
        keep.camera_tracks.update(other.camera_tracks)
        keep.embeddings.extend(other.embeddings)
        keep.embeddings = keep.embeddings[-20:]
        keep.ocr_history.extend(other.ocr_history)
        if len(keep.ocr_history) > _MAX_OCR_HISTORY:
            del keep.ocr_history[: len(keep.ocr_history) - _MAX_OCR_HISTORY]
        keep.ocr_confirmed_tracks |= other.ocr_confirmed_tracks
        keep.ship_id = self._best_ship_id(keep)
        keep.first_seen_ts = min(keep.first_seen_ts, other.first_seen_ts)
        keep.last_seen_ts = max(keep.last_seen_ts, other.last_seen_ts)
        keep.active_tracks |= other.active_tracks
        keep.removed_tracks |= other.removed_tracks
        keep.last_track = other.last_track or keep.last_track
        if other.berth_in_ts is not None:
            # Giữ camera đi kèm mốc berth_in sớm nhất (tàu IN ở camera nào).
            if keep.berth_in_ts is None or other.berth_in_ts < keep.berth_in_ts:
                keep.berth_in_ts = other.berth_in_ts
                keep.berth_in_camera_id = other.berth_in_camera_id
        if other.berth_out_ts is not None:
            # Giữ camera đi kèm mốc berth_out muộn nhất (tàu OUT ở camera nào).
            if keep.berth_out_ts is None or other.berth_out_ts > keep.berth_out_ts:
                keep.berth_out_ts = other.berth_out_ts
                keep.berth_out_camera_id = other.berth_out_camera_id
        if keep.primary_camera_id is None:
            keep.primary_camera_id = other.primary_camera_id
        for camera_id, track_id in other.camera_tracks.items():
            self._track_to_global[(int(camera_id), str(track_id))] = keep.global_id
        self._identities.pop(other.global_id, None)
        return keep

    def _cameras_are_adjacent_pair(self, cam_a: int, cam_b: int) -> bool:
        if int(cam_a) == int(cam_b):
            return False
        idx_a = self._camera_index.get(int(cam_a))
        idx_b = self._camera_index.get(int(cam_b))
        if idx_a is None or idx_b is None:
            return False
        return abs(idx_a - idx_b) == 1

    def _may_last_chance_merge(
        self,
        left: GlobalIdentity,
        right: GlobalIdentity,
    ) -> bool:
        """Only collapse same-ship inactive identities when they are camera-handoff candidates.

        Multiple boats in one camera can share OCR/ship_id. Merging those inactive
        identities drops one persisted detection, so same-camera identities must stay separate.
        """
        left_cameras = {int(cam) for cam in left.camera_tracks}
        right_cameras = {int(cam) for cam in right.camera_tracks}
        if not left_cameras or not right_cameras:
            return False
        if left_cameras & right_cameras:
            return False
        return any(
            self._cameras_are_adjacent_pair(left_cam, right_cam)
            for left_cam in left_cameras
            for right_cam in right_cameras
        )

    def _allows_ship_id_attach(self, identity: GlobalIdentity, camera_id: int) -> bool:
        """Allow same ship_id on adjacent cameras (seam) but not two tracks on one camera."""
        camera_key = int(camera_id)
        active_cams = [cam for cam, _ in identity.active_tracks]
        if active_cams.count(camera_key) > 0:
            return False
        other_cams = {cam for cam in active_cams if cam != camera_key}
        if not other_cams:
            return True
        return any(self._cameras_are_adjacent_pair(camera_key, oc) for oc in other_cams)

    def _may_merge_identities(self, left: GlobalIdentity, right: GlobalIdentity) -> bool:
        if not left.active_tracks or not right.active_tracks:
            return True
        if self._is_adjacent_seam_visit(left, right):
            return True
        return not self._identities_have_concurrent_active_tracks(left, right)

    def _is_adjacent_seam_visit(self, left: GlobalIdentity, right: GlobalIdentity) -> bool:
        """Same OCR-confirmed ship visible concurrently on adjacent cameras (one boat at seam)."""
        ship_left = (left.ship_id or '').strip().upper()
        ship_right = (right.ship_id or '').strip().upper()
        if not ship_left or ship_left != ship_right:
            return False
        if not left.ocr_confirmed_tracks or not right.ocr_confirmed_tracks:
            return False
        if not left.active_tracks or not right.active_tracks:
            return False

        left_cams = {cam for cam, _ in left.active_tracks}
        right_cams = {cam for cam, _ in right.active_tracks}
        if left_cams & right_cams:
            return False
        if len(left.active_tracks) > len(left_cams) or len(right.active_tracks) > len(right_cams):
            return False

        for left_cam in left_cams:
            if not any(self._cameras_are_adjacent_pair(left_cam, right_cam) for right_cam in right_cams):
                return False
        for right_cam in right_cams:
            if not any(self._cameras_are_adjacent_pair(right_cam, left_cam) for left_cam in left_cams):
                return False
        return True

    def _has_concurrent_active_on_other_camera(
        self,
        identity: GlobalIdentity,
        camera_id: int,
    ) -> bool:
        """True when another camera still has a live track on this identity."""
        camera_key = int(camera_id)
        return any(cam != camera_key for cam, _ in identity.active_tracks)

    def _has_active_track_on_camera(
        self,
        identity: GlobalIdentity,
        camera_id: int,
    ) -> bool:
        """True when this identity already holds a live track on this camera.

        Two separate bboxes concurrently on one camera are two different boats,
        so an incoming track must never merge into an identity already active on
        that same camera — regardless of embedding cosine. Guards the embedding
        and fallback matchers the way _allows_ship_id_attach guards the ship_id
        path.
        """
        camera_key = int(camera_id)
        return any(cam == camera_key for cam, _ in identity.active_tracks)

    def _has_concurrent_active_on_non_adjacent_camera(
        self,
        identity: GlobalIdentity,
        camera_id: int,
    ) -> bool:
        """True when a non-adjacent camera has a live track on this identity.

        Adjacent cameras share overlapping FOV (consecutive in camera_order), so
        a track re-appearing on cam4 while cam3 still holds the identity is a
        valid overlap-merge signal, not a conflict.
        """
        camera_key = int(camera_id)
        candidate_cameras = {camera_key, *self.adjacent_camera_ids(camera_key)}
        return any(cam not in candidate_cameras for cam, _ in identity.active_tracks)

    def _identities_have_concurrent_active_tracks(
        self,
        left: GlobalIdentity,
        right: GlobalIdentity,
    ) -> bool:
        if not left.active_tracks or not right.active_tracks:
            return False
        left_cams = {cam for cam, _ in left.active_tracks}
        right_cams = {cam for cam, _ in right.active_tracks}
        return bool(left_cams & right_cams) or len(left_cams | right_cams) > 1

    def _track_may_display_ship_id(
        self,
        identity: GlobalIdentity,
        track_key: TrackKey,
    ) -> bool:
        """Overlay/API: only show plate after OCR on this track or cross-cam handoff."""
        if track_key in identity.ocr_confirmed_tracks:
            return True
        return self._is_cross_camera_handoff_track(identity, track_key)

    def _should_propagate_ship_id_to_track(
        self,
        identity: GlobalIdentity,
        track_key: TrackKey,
        track: TrackedBoat,
    ) -> bool:
        if not identity.ship_id or track.ship_id:
            return False
        if track_key in identity.ocr_confirmed_tracks:
            return True
        return self._is_cross_camera_handoff_track(identity, track_key)

    def _is_cross_camera_handoff_track(
        self,
        identity: GlobalIdentity,
        track_key: TrackKey,
    ) -> bool:
        """
        Allow inherited plate when the identity is handing off between adjacent cameras:
        no concurrent active tracks elsewhere, and a removed track exists on an adjacent cam.
        """
        if not identity.ship_id:
            return False
        camera_id, _ = track_key
        if self._has_concurrent_active_on_other_camera(identity, camera_id):
            return False
        removed_cameras = {cam for cam, _ in identity.removed_tracks}
        if not removed_cameras:
            return False
        candidate_cameras = {camera_id, *self.adjacent_camera_ids(camera_id)}
        return bool(removed_cameras & set(candidate_cameras))

    def _update_primary_camera(
        self,
        identity: GlobalIdentity,
        camera_id: int,
        track: TrackedBoat,
        frame_shape: tuple[int, int] | None,
    ) -> None:
        if frame_shape is None:
            identity.primary_camera_id = identity.primary_camera_id or int(camera_id)
            return
        height, width = int(frame_shape[0]), int(frame_shape[1])
        if width <= 0 or height <= 0:
            return
        x1, _, x2, _ = track.box.astype(float)
        centroid_x = (x1 + x2) * 0.5
        edge_px = width * self._edge_zone_ratio
        in_primary = edge_px <= centroid_x <= (width - edge_px)
        if in_primary:
            identity.primary_camera_id = int(camera_id)
        elif identity.primary_camera_id is None:
            identity.primary_camera_id = int(camera_id)

    def _best_ship_id(self, identity: GlobalIdentity) -> str | None:
        totals: dict[str, float] = {}
        for ship_id, confidence in identity.ocr_history:
            normalized = str(ship_id).strip().upper()
            if not normalized:
                continue
            totals[normalized] = totals.get(normalized, 0.0) + float(confidence)
        if not totals:
            return identity.ship_id
        return max(totals, key=totals.get)

    def _flush_expired_locked(self, now: float) -> None:
        for identity in list(self._identities.values()):
            if identity.finalized or identity.active_tracks or identity.anchored:
                continue
            if now - identity.last_seen_ts >= self._handoff_window_sec:
                self._finalize_identity_locked(identity)
        self._purge_finalized_locked(now)

    def _purge_finalized_locked(self, now: float) -> None:
        """Evict finalized identities (and their track mappings) to bound RAM.

        Finalized identities are kept for `_finalized_retention_sec` to allow
        late same-ship merges, then dropped. Without this, `_identities` and
        `_track_to_global` grow forever (one entry per vessel/track ever seen),
        leaking memory until the host OOMs.
        """
        expired: list[str] = []
        for global_id, identity in self._identities.items():
            if not identity.finalized:
                continue
            if identity.active_tracks or identity.anchored:
                continue
            if now - identity.finalized_ts >= self._finalized_retention_sec:
                expired.append(global_id)

        # Backstop: if the table is still oversized, drop the oldest finalized
        # identities regardless of retention window.
        if len(self._identities) > self._max_identities:
            finalized_by_age = sorted(
                (
                    (gid, ident)
                    for gid, ident in self._identities.items()
                    if ident.finalized
                    and not ident.active_tracks
                    and not ident.anchored
                    and gid not in expired
                ),
                key=lambda item: item[1].finalized_ts,
            )
            overflow = len(self._identities) - self._max_identities
            for gid, _ in finalized_by_age[:overflow]:
                expired.append(gid)

        if not expired:
            return

        expired_set = set(expired)
        for global_id in expired_set:
            self._identities.pop(global_id, None)
        # Drop track→global mappings that point at purged identities.
        stale_keys = [
            track_key
            for track_key, gid in self._track_to_global.items()
            if gid in expired_set
        ]
        for track_key in stale_keys:
            self._track_to_global.pop(track_key, None)
        if expired_set:
            _log.debug(
                'reid: purged %d finalized identities (table=%d, map=%d)',
                len(expired_set),
                len(self._identities),
                len(self._track_to_global),
            )

    def _finalize_identity_locked(self, identity: GlobalIdentity) -> None:
        if identity.finalized:
            return
        identity.finalized = True
        identity.finalized_ts = time.time()

        # Last-chance merge (C1): before writing, absorb other inactive identities with same ship_id
        if identity.ship_id:
            pre_merge_ship_id = identity.ship_id
            for other in list(self._identities.values()):
                if other is identity or other.finalized:
                    continue
                if (
                    other.ship_id == identity.ship_id
                    and not other.active_tracks
                    and self._may_last_chance_merge(identity, other)
                ):
                    other.finalized = True  # prevent re-visit if loop snapshot still holds this ref
                    identity = self._merge_identities(identity, other)
            # Prevent merged ocr_history from flipping ship_id away from the pre-merge value.
            # _merge_identities calls _best_ship_id which may pick a different ID from combined history.
            if pre_merge_ship_id and identity.ship_id != pre_merge_ship_id:
                identity.ship_id = pre_merge_ship_id

        # Write IN/OUT events exactly once
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
        track.berth_in_camera_id = identity.berth_in_camera_id
        track.berth_out_camera_id = identity.berth_out_camera_id
        history = list(identity.ocr_history)
        self._on_global_track_removed(track, history)

    def _write_boundary_events_locked(self, identity: GlobalIdentity) -> None:
        from app.services.boundary_crossing_event_service import record_boundary_crossing_event

        if identity.berth_in_ts is not None and identity.berth_out_ts is not None:
            if identity.berth_out_ts < identity.berth_in_ts:
                _log.warning(
                    'reid: identity %s berth_out_ts %.1f < berth_in_ts %.1f — writing as-is',
                    identity.global_id,
                    identity.berth_out_ts,
                    identity.berth_in_ts,
                )

        fallback_camera = identity.primary_camera_id or next(iter(identity.camera_tracks), 0)
        track_id = identity.global_id

        if identity.berth_in_ts is not None:
            record_boundary_crossing_event(
                camera_id=int(identity.berth_in_camera_id or fallback_camera),
                track_id=str(track_id),
                direction='in',
                crossed_at_ts=float(identity.berth_in_ts),
                ship_id=identity.ship_id,
            )
        if identity.berth_out_ts is not None:
            record_boundary_crossing_event(
                camera_id=int(identity.berth_out_camera_id or fallback_camera),
                track_id=str(track_id),
                direction='out',
                crossed_at_ts=float(identity.berth_out_ts),
                ship_id=identity.ship_id,
            )

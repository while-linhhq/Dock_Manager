from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import numpy as np

from app.services.ai.boat_tracker import TrackedBoat
from app.services.ai.embedding_extractor import cosine_similarity, normalize_embedding

if TYPE_CHECKING:
    from app.services.ai.seam_anchor_verifier import SeamAnchorVerifier


_log = logging.getLogger(__name__)


TrackKey = tuple[int, str]


@dataclass
class GlobalIdentity:
    global_id: str
    ship_id: str | None
    camera_tracks: dict[int, str]
    embeddings: list[np.ndarray] = field(default_factory=list)
    ocr_history: list[tuple[str, float]] = field(default_factory=list)
    first_seen_ts: float = 0.0
    last_seen_ts: float = 0.0
    primary_camera_id: int | None = None
    active_tracks: set[TrackKey] = field(default_factory=set)
    removed_tracks: set[TrackKey] = field(default_factory=set)
    last_track: TrackedBoat | None = None
    finalized: bool = False
    anchored: bool = False


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
        self._identities: dict[str, GlobalIdentity] = {}
        self._track_to_global: dict[TrackKey, str] = {}
        self._lock = threading.RLock()

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
                    self._identities[global_id] = identity
                else:
                    identity.anchored = True
                    identity.last_seen_ts = max(
                        identity.last_seen_ts, float(state.last_seen_ts)
                    )
                    if state.last_track is not None:
                        identity.last_track = state.last_track

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
            track_key = (camera_key, str(track.track_id))
            global_id = self._track_to_global.get(track_key)
            identity = self._identities.get(global_id) if global_id else None

            if identity is None and self._seam_anchor_verifier is not None:
                resurrected_id = self._seam_anchor_verifier.try_resurrect(
                    camera_key,
                    track.box,
                    embedding,
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

            self._attach_track(identity, camera_key, track, embedding)
            self._track_to_global[track_key] = identity.global_id
            self._update_primary_camera(identity, camera_key, track, frame_shape)
            if identity.ship_id and not track.ship_id:
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
        normalized_ship_id = str(ship_id).strip().upper()
        with self._lock:
            camera_key = int(camera_id)
            track_key = (camera_key, str(track_id))
            identity = self._identity_for_track(track_key)
            if identity is None:
                identity = self._create_empty_identity(camera_key, str(track_id))
                self._track_to_global[track_key] = identity.global_id

            identity.ocr_history.append((normalized_ship_id, float(confidence)))
            identity.ship_id = self._best_ship_id(identity)

            for other in list(self._identities.values()):
                if other.global_id == identity.global_id or other.ship_id != normalized_ship_id:
                    continue
                identity = self._merge_identities(identity, other)

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
            if ocr_history:
                for ship_id, confidence in ocr_history:
                    identity.ocr_history.append((str(ship_id).strip().upper(), float(confidence)))
                identity.ship_id = self._best_ship_id(identity)
            track_key = (camera_key, str(track.track_id))
            identity.active_tracks.discard(track_key)
            identity.removed_tracks.add(track_key)
            identity.last_seen_ts = max(identity.last_seen_ts, float(track.last_seen_ts))
            identity.last_track = track.copy_public()

            if (
                not identity.active_tracks
                and not identity.anchored
                and self._seam_anchor_verifier is not None
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
                )
                if anchored_ok:
                    identity.anchored = True

            self._flush_expired_locked(time.time())
            return identity.global_id

    def get_global_ship_id(self, camera_id: int, track_id: str) -> str | None:
        with self._lock:
            identity = self._identity_for_track((int(camera_id), str(track_id)))
            return identity.ship_id if identity is not None else None

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
        if embedding is not None:
            identity.embeddings.append(normalize_embedding(embedding))
            identity.embeddings = identity.embeddings[-20:]
        if track.ship_id or track.last_known_ship_id:
            identity.ocr_history.append((track.ship_id or track.last_known_ship_id or '', 1.0))
            identity.ship_id = self._best_ship_id(identity)

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
                if identity.ship_id == ship_id:
                    return identity

        if embedding is None:
            return None

        best_identity: GlobalIdentity | None = None
        best_score = 0.0
        for identity in self._identities.values():
            if identity.finalized:
                continue
            if not identity.anchored and now - identity.last_seen_ts > self._handoff_window_sec:
                continue
            if not self._is_camera_candidate(camera_id, identity):
                continue
            score = self._identity_similarity(identity, embedding)
            if score > best_score:
                best_score = score
                best_identity = identity

        if best_identity is not None and best_score >= self._visual_threshold:
            return best_identity
        return None

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
        keep.ship_id = self._best_ship_id(keep)
        keep.first_seen_ts = min(keep.first_seen_ts, other.first_seen_ts)
        keep.last_seen_ts = max(keep.last_seen_ts, other.last_seen_ts)
        keep.active_tracks |= other.active_tracks
        keep.removed_tracks |= other.removed_tracks
        keep.last_track = other.last_track or keep.last_track
        if keep.primary_camera_id is None:
            keep.primary_camera_id = other.primary_camera_id
        for camera_id, track_id in other.camera_tracks.items():
            self._track_to_global[(int(camera_id), str(track_id))] = keep.global_id
        self._identities.pop(other.global_id, None)
        return keep

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

    def _finalize_identity_locked(self, identity: GlobalIdentity) -> None:
        identity.finalized = True
        if self._on_global_track_removed is None or identity.last_track is None:
            return
        track = identity.last_track.copy_public()
        track.track_id = identity.global_id
        track.ship_id = identity.ship_id or track.ship_id or 'UNKNOWN'
        track.last_known_ship_id = track.ship_id
        history = list(identity.ocr_history)
        self._on_global_track_removed(track, history)

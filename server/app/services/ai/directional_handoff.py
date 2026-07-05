"""DirectionalHandoffMatcher — merge identities across adjacent cameras when a
boat leaves one camera and reappears in the neighbouring one *sequentially*
(not concurrently), using motion direction + timing + embedding + colour.

This covers the gap left by OverlapMergeMatcher (which only fires when the boat
is seen on two cameras at the *same* time). Here the boat exits cam A heading
toward the shared border, then appears in cam B at that border after a plausible
transit gap — even when OCR produced no ship_id.

Geometry comes from the camera-group layout (``layout_x`` per camera): the
matcher knows which camera sits to the left/right of which, so a valid handoff
requires the source track's horizontal velocity to point toward the shared
border and the incoming track to appear at that border's edge zone.

The matcher only decides *identity merge* (same boat). Whether a boundary
crossing (IN/OUT) event is emitted is governed separately by the reverse-motion
guard in ``CrossCameraReIdManager.report_boundary_crossing`` — a boat backing
out of a berth and clipping the previous camera must not fabricate a new event.

Spec: docs/superpowers/specs/2026-06-30-reid-seam-anchor-inout-dedup-design.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from app.services.ai.embedding_extractor import cosine_similarity

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DirectionalHandoffConfig:
    enabled: bool = True
    # Max seconds between source track's last sighting and the incoming track's
    # first sighting for the handoff to be plausible.
    max_transit_sec: float = 20.0
    # Small negative tolerance: incoming may appear slightly before source's last
    # frame is processed. Beyond this the boat is "concurrent" (overlap matcher's job).
    min_transit_sec: float = -3.0
    # Minimum |mean vx| (px/sec) on the source identity for its direction to count.
    min_velocity_px: float = 5.0
    # Fraction of frame width defining the border edge zone on the incoming camera.
    edge_zone_ratio: float = 0.2
    embedding_weight: float = 0.5
    direction_weight: float = 0.3
    time_weight: float = 0.2
    accept_threshold: float = 0.6
    # Minimum embedding cosine floor — below this, never merge regardless of
    # direction/time (prevents two different boats moving alike from merging).
    embedding_floor: float = 0.45


def _mean_vx(identity: Any) -> float:
    hist = getattr(identity, 'vx_history', None) or []
    if not hist:
        last = getattr(identity, 'last_track', None)
        vel = getattr(last, 'velocity', None) if last is not None else None
        if vel is not None:
            return float(vel[0])
        return 0.0
    return float(np.mean(hist))


def _best_embedding_cosine(embeddings: list, emb: np.ndarray | None) -> float:
    if not embeddings or emb is None:
        return 0.0
    return max(float(cosine_similarity(existing, emb)) for existing in embeddings)


class DirectionalHandoffMatcher:
    def __init__(
        self,
        config: DirectionalHandoffConfig,
        *,
        is_adjacent: Callable[[int, int], bool] | None = None,
        frame_width_for: Callable[[int], float] | None = None,
        layout_x_for: Callable[[int], float | None] | None = None,
    ) -> None:
        self._config = config
        self._is_adjacent = is_adjacent or (lambda a, b: False)
        self._frame_width_for = frame_width_for or (lambda cam: 0.0)
        self._layout_x_for = layout_x_for or (lambda cam: None)

    # ------------------------------------------------------------------ helpers
    def _border_side(self, source_cam: int, incoming_cam: int) -> int:
        """+1 if incoming camera sits to the RIGHT of the source camera in the
        layout (boat must move right to hand off), -1 if to the LEFT, 0 unknown."""
        xs = self._layout_x_for(int(source_cam))
        xi = self._layout_x_for(int(incoming_cam))
        if xs is None or xi is None:
            return 0
        if xi > xs:
            return 1
        if xi < xs:
            return -1
        return 0

    def _direction_score(self, identity: Any, source_cam: int, track: Any) -> float:
        """1.0 = source motion points toward the shared border AND the incoming
        track sits in the border edge zone. 0.0 = direction contradicts geometry."""
        side = self._border_side(source_cam, int(track.camera_id))
        if side == 0:
            return 0.5  # unknown geometry — neutral, don't reward or punish
        vx = _mean_vx(identity)
        if abs(vx) < float(self._config.min_velocity_px):
            return 0.0  # no clear motion → no directional evidence
        # motion must match the border side (right border → vx>0, left → vx<0)
        if (side > 0 and vx <= 0) or (side < 0 and vx >= 0):
            return 0.0
        # incoming track should appear at the edge nearest the source camera.
        width = float(self._frame_width_for(int(track.camera_id)) or 0.0)
        if width <= 0.0:
            return 0.8  # unknown width — motion matched, give solid but not full
        box = np.asarray(track.box, dtype=np.float32)
        cx = (float(box[0]) + float(box[2])) / 2.0
        margin = width * float(self._config.edge_zone_ratio)
        # if incoming came FROM the left (source on left, side>0), it enters at
        # cam B's LEFT edge; if source on right (side<0), enters at RIGHT edge.
        if side > 0:
            in_edge = cx <= margin
        else:
            in_edge = cx >= (width - margin)
        return 1.0 if in_edge else 0.3

    def _time_score(self, identity: Any, track: Any, now: float) -> float:
        last_seen = float(getattr(identity, 'last_seen_ts', 0.0) or 0.0)
        appear = float(getattr(track, 'first_seen_ts', now) or now)
        gap = appear - last_seen
        lo = float(self._config.min_transit_sec)
        hi = float(self._config.max_transit_sec)
        if gap < lo or gap > hi:
            return 0.0
        if gap <= 0.0:
            return 1.0
        # linear decay from 1.0 (immediate) to 0.0 (at max_transit_sec)
        return max(0.0, 1.0 - gap / hi)

    def _passes_gate(self, identity: Any, track: Any, now: float) -> bool:
        if getattr(identity, 'finalized', False):
            return False
        # identity must have (had) a track on a camera adjacent to the incoming one
        cams = set(getattr(identity, 'camera_tracks', {}).keys())
        if not any(self._is_adjacent(cam, int(track.camera_id)) for cam in cams):
            return False
        # the incoming camera must be NEW to this identity (real handoff, not the
        # same camera re-detecting) OR a reverse re-touch — either way require the
        # source camera differ from the incoming one.
        if int(track.camera_id) in cams and len(cams) == 1:
            return False
        # HARD time gate: a transit gap outside [min_transit_sec, max_transit_sec]
        # is physically implausible — reject regardless of embedding/direction.
        # The boat could not have travelled between the cameras in that window.
        if self._time_score(identity, track, now) <= 0.0:
            return False
        return True

    def _source_camera(self, identity: Any, incoming_cam: int) -> int | None:
        cams = list(getattr(identity, 'camera_tracks', {}).keys())
        adj = [c for c in cams if self._is_adjacent(c, int(incoming_cam))]
        if not adj:
            return None
        return int(adj[0])

    def score(self, identity: Any, track: Any, now: float) -> float:
        source_cam = self._source_camera(identity, int(track.camera_id))
        if source_cam is None:
            return 0.0
        emb_cos = _best_embedding_cosine(
            getattr(identity, 'embeddings', []) or [],
            getattr(track, 'embedding', None),
        )
        if emb_cos < float(self._config.embedding_floor):
            return 0.0
        dir_s = self._direction_score(identity, source_cam, track)
        time_s = self._time_score(identity, track, now)
        return (
            self._config.embedding_weight * emb_cos
            + self._config.direction_weight * dir_s
            + self._config.time_weight * time_s
        )

    def best_match(self, identities: list, track: Any, now: float) -> str | None:
        if not self._config.enabled:
            return None
        candidates = [
            idn for idn in identities if self._passes_gate(idn, track, now)
        ]
        if not candidates:
            return None
        scored = sorted(
            ((self.score(idn, track, now), idn) for idn in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score, best_identity = scored[0]
        if best_score < float(self._config.accept_threshold):
            return None
        return best_identity.global_id

    def diagnose(self, identities: list, track: Any, now: float) -> dict | None:
        """Debug overlay: best directional score vs accept threshold, or None."""
        if not self._config.enabled:
            return None
        candidates = [
            idn for idn in identities if self._passes_gate(idn, track, now)
        ]
        if not candidates:
            return None
        best_score, best_identity = max(
            ((self.score(idn, track, now), idn) for idn in candidates),
            key=lambda pair: pair[0],
        )
        return {
            'score': float(best_score),
            'accept': float(self._config.accept_threshold),
            'target_gid': getattr(best_identity, 'global_id', None),
            'target_ship_id': getattr(best_identity, 'ship_id', None),
        }

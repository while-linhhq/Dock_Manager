"""OverlapMergeMatcher — merge identities seen concurrently on adjacent
overlapping-FOV cameras, using a weighted fusion of embedding, color, and size.

Spec: docs/superpowers/specs/2026-06-30-reid-seam-anchor-inout-dedup-design.md Phần 2.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from app.services.ai.embedding_extractor import cosine_similarity
from app.services.ai.motion_classifier import MOTION_STATIC

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OverlapMergeConfig:
    enabled: bool = True
    edge_zone_ratio: float = 0.15
    embedding_weight: float = 0.6
    color_weight: float = 0.25
    size_weight: float = 0.15
    accept_threshold: float = 0.6
    min_margin: float = 0.12


def _hsv_similarity(a: tuple | None, b: tuple | None) -> float:
    """1.0 = identical hue/sat/val; degrades with circular hue distance and S/V diff."""
    if a is None or b is None:
        return 0.0
    ha, sa, va = float(a[0]), float(a[1]), float(a[2])
    hb, sb, vb = float(b[0]), float(b[1]), float(b[2])
    # OpenCV hue range is 0..179 (degrees/2)
    dh = abs(ha - hb)
    dh = min(dh, 180.0 - dh)
    hue_term = max(0.0, 1.0 - dh / 90.0)
    sat_term = max(0.0, 1.0 - abs(sa - sb) / 255.0)
    val_term = max(0.0, 1.0 - abs(va - vb) / 255.0)
    return (hue_term + sat_term + val_term) / 3.0


def _box_size_ratio(box_a: np.ndarray | None, box_b: np.ndarray | None) -> float:
    """min(area)/max(area) in [0,1]; 0 when either box is missing/degenerate."""
    if box_a is None or box_b is None:
        return 0.0
    area_a = max(0.0, float(box_a[2] - box_a[0])) * max(0.0, float(box_a[3] - box_a[1]))
    area_b = max(0.0, float(box_b[2] - box_b[0])) * max(0.0, float(box_b[3] - box_b[1]))
    if area_a <= 0.0 or area_b <= 0.0:
        return 0.0
    return float(min(area_a, area_b) / max(area_a, area_b))


def _best_embedding_cosine(embeddings: list[np.ndarray], emb: np.ndarray | None) -> float:
    if not embeddings or emb is None:
        return 0.0
    return max(float(cosine_similarity(existing, emb)) for existing in embeddings)


class OverlapMergeMatcher:
    def __init__(
        self,
        config: OverlapMergeConfig,
        *,
        is_adjacent: Callable[[int, int], bool] | None = None,
        frame_width_for: Callable[[int], float] | None = None,
    ) -> None:
        self._config = config
        self._is_adjacent = is_adjacent or (lambda a, b: False)
        self._frame_width_for = frame_width_for or (lambda cam: 0.0)

    def score(self, identity: Any, track: Any) -> float:
        """Weighted fusion in [0,1] of embedding cosine, HSV color similarity, box-size ratio."""
        emb_cos = _best_embedding_cosine(
            getattr(identity, 'embeddings', []) or [],
            getattr(track, 'embedding', None),
        )
        identity_hsv = None
        hist = getattr(identity, 'dominant_hsv_history', None) or []
        if hist:
            identity_hsv = hist[-1]
        color_sim = _hsv_similarity(identity_hsv, getattr(track, 'dominant_color_hsv', None))

        last_track = getattr(identity, 'last_track', None)
        identity_box = getattr(last_track, 'box', None) if last_track is not None else None
        size_ratio = _box_size_ratio(identity_box, getattr(track, 'box', None))

        return (
            self._config.embedding_weight * emb_cos
            + self._config.color_weight * color_sim
            + self._config.size_weight * size_ratio
        )

    def _track_in_edge_zone(self, track: Any) -> bool:
        width = float(self._frame_width_for(int(track.camera_id)) or 0.0)
        if width <= 0.0:
            return True  # unknown frame width → don't block on edge gate
        box = np.asarray(track.box, dtype=np.float32)
        cx = (float(box[0]) + float(box[2])) / 2.0
        margin = width * float(self._config.edge_zone_ratio)
        return cx <= margin or cx >= (width - margin)

    @staticmethod
    def _motion_compatible(identity: Any, track: Any) -> bool:
        last_track = getattr(identity, 'last_track', None)
        id_motion = getattr(last_track, 'motion_state', None) if last_track else None
        tr_motion = getattr(track, 'motion_state', None)
        if id_motion is None or tr_motion is None:
            return True  # unknown motion → don't block (gate is best-effort)
        if id_motion == MOTION_STATIC or tr_motion == MOTION_STATIC:
            return id_motion == tr_motion
        return True  # both moving (maneuvering/transiting) → compatible

    def _passes_gate(self, identity: Any, track: Any) -> bool:
        if getattr(identity, 'finalized', False):
            return False
        active_cams = {cam for cam, _ in getattr(identity, 'active_tracks', set())}
        if not active_cams:
            return False
        # gate: identity must have an active track on a camera adjacent to track's camera
        if not any(self._is_adjacent(cam, int(track.camera_id)) for cam in active_cams):
            return False
        # gate: exactly one active track on the identity (1 boat)
        if len(getattr(identity, 'active_tracks', set())) != 1:
            return False
        # gate: incoming track in edge (overlap) zone
        if not self._track_in_edge_zone(track):
            return False
        # gate A2: motion state compatible
        if not self._motion_compatible(identity, track):
            return False
        return True

    def candidate_identities(self, identities: list, track: Any, now: float) -> list:
        return [idn for idn in identities if self._passes_gate(idn, track)]

    def best_match(self, identities: list, track: Any, now: float) -> str | None:
        if not self._config.enabled:
            return None
        candidates = self.candidate_identities(identities, track, now)
        if not candidates:
            return None
        scored = sorted(
            ((self.score(idn, track), idn) for idn in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score, best_identity = scored[0]
        if best_score < float(self._config.accept_threshold):
            return None
        if len(scored) > 1:
            second_score = scored[1][0]
            if (best_score - second_score) < float(self._config.min_margin):
                return None
        return best_identity.global_id

    def diagnose(self, identities: list, track: Any, now: float) -> dict | None:
        """Debug overlay: best fusion score / accept threshold + margin, or None."""
        if not self._config.enabled:
            return None
        candidates = self.candidate_identities(identities, track, now)
        if not candidates:
            return None
        scored = sorted(
            ((self.score(idn, track), idn) for idn in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score, best_identity = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        return {
            'score': float(best_score),
            'accept': float(self._config.accept_threshold),
            'margin': float(best_score - second_score),
            'min_margin': float(self._config.min_margin),
            'target_gid': getattr(best_identity, 'global_id', None),
            'target_ship_id': getattr(best_identity, 'ship_id', None),
        }

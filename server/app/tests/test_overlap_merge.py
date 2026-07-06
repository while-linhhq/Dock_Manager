"""Tests for OverlapMergeMatcher (cross-camera overlap merge, Phần 2 + A2)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from app.services.ai.handoff_matcher import OverlapMergeConfig, OverlapMergeMatcher


@dataclass
class _Identity:
    """Minimal stand-in for GlobalIdentity for matcher unit tests."""
    global_id: str
    camera_tracks: dict
    active_tracks: set = field(default_factory=set)
    embeddings: list = field(default_factory=list)
    dominant_hsv_history: list = field(default_factory=list)
    last_track: object = None
    finalized: bool = False
    last_seen_ts: float = 0.0


@dataclass
class _Track:
    track_id: str
    camera_id: int
    box: np.ndarray
    embedding: np.ndarray | None = None
    dominant_color_hsv: tuple | None = None
    motion_state: str | None = None


def _cfg(**overrides) -> OverlapMergeConfig:
    base = dict(
        enabled=True,
        edge_zone_ratio=0.15,
        embedding_weight=0.6,
        color_weight=0.25,
        size_weight=0.15,
        accept_threshold=0.6,
        min_margin=0.12,
    )
    base.update(overrides)
    return OverlapMergeConfig(**base)


def _unit(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-9)


def test_score_combines_embedding_color_size():
    """score() = weighted sum of cosine, hsv similarity, size ratio in [0,1]."""
    matcher = OverlapMergeMatcher(_cfg())
    emb = _unit([1.0, 0.0, 0.0])
    identity = _Identity(
        global_id='g1',
        camera_tracks={1: 't1'},
        embeddings=[emb],
        dominant_hsv_history=[(100, 150, 150)],
        last_track=_Track('t1', 1, np.array([0, 0, 40, 40], dtype=np.float32)),
    )
    track = _Track(
        't2', 2, np.array([0, 0, 40, 40], dtype=np.float32),
        embedding=emb, dominant_color_hsv=(100, 150, 150),
    )
    score = matcher.score(identity, track)
    # identical embedding (cos=1), identical color (sim=1), identical size (ratio=1)
    assert score == pytest.approx(1.0, abs=1e-3)


def test_score_zero_without_embedding():
    """No embedding on identity or track → embedding term contributes 0."""
    matcher = OverlapMergeMatcher(_cfg())
    identity = _Identity(
        global_id='g1', camera_tracks={1: 't1'},
        embeddings=[], dominant_hsv_history=[(100, 150, 150)],
        last_track=_Track('t1', 1, np.array([0, 0, 40, 40], dtype=np.float32)),
    )
    track = _Track('t2', 2, np.array([0, 0, 40, 40], dtype=np.float32),
                   embedding=None, dominant_color_hsv=(100, 150, 150))
    score = matcher.score(identity, track)
    # only color (0.25 * 1) + size (0.15 * 1) = 0.40
    assert score == pytest.approx(0.40, abs=1e-3)


def _matcher_with_adjacency(**overrides):
    """Matcher whose adjacency + frame-width context comes from injected callbacks."""
    cfg = _cfg(**overrides)
    # camera_order [1,2,3]; adjacency = |idx diff| == 1
    order = {1: 0, 2: 1, 3: 2}

    def is_adjacent(cam_a: int, cam_b: int) -> bool:
        ia, ib = order.get(int(cam_a)), order.get(int(cam_b))
        return ia is not None and ib is not None and abs(ia - ib) == 1

    def frame_width(cam: int) -> float:
        return 1000.0

    return OverlapMergeMatcher(cfg, is_adjacent=is_adjacent, frame_width_for=frame_width)


def _edge_track(track_id, camera_id, x_left):
    """Track whose box left edge sits at x_left (width 40)."""
    return _Track(
        track_id, camera_id,
        np.array([x_left, 100, x_left + 40, 140], dtype=np.float32),
        embedding=_unit([1.0, 0.0, 0.0]),
        dominant_color_hsv=(100, 150, 150),
        motion_state=MOTION_STATIC,
    )


from app.services.ai.motion_classifier import MOTION_STATIC, MOTION_TRANSITING


def test_best_match_accepts_single_adjacent_edge_candidate():
    """One adjacent identity, track in edge zone, matching motion → merge accepted."""
    matcher = _matcher_with_adjacency()
    emb = _unit([1.0, 0.0, 0.0])
    identity = _Identity(
        global_id='g1', camera_tracks={1: 't1'},
        active_tracks={(1, 't1')},
        embeddings=[emb], dominant_hsv_history=[(100, 150, 150)],
        last_track=_Track('t1', 1, np.array([0, 0, 40, 40], dtype=np.float32),
                          motion_state=MOTION_STATIC),
    )
    # camera 2 track near left edge (x in [0, 150] of width-1000 frame)
    track = _edge_track('t2', 2, x_left=10)
    result = matcher.best_match([identity], track, now=1.0)
    assert result == 'g1'


def test_best_match_rejects_non_adjacent_camera():
    """Identity active only on camera 3, new track on camera 1 → not adjacent → None."""
    matcher = _matcher_with_adjacency()
    emb = _unit([1.0, 0.0, 0.0])
    identity = _Identity(
        global_id='g1', camera_tracks={3: 't3'},
        active_tracks={(3, 't3')},
        embeddings=[emb], dominant_hsv_history=[(100, 150, 150)],
        last_track=_Track('t3', 3, np.array([0, 0, 40, 40], dtype=np.float32),
                          motion_state=MOTION_STATIC),
    )
    track = _edge_track('t1', 1, x_left=10)
    assert matcher.best_match([identity], track, now=1.0) is None


def test_best_match_rejects_track_outside_edge_zone():
    """Track centered mid-frame (not in edge zone) → None."""
    matcher = _matcher_with_adjacency()
    emb = _unit([1.0, 0.0, 0.0])
    identity = _Identity(
        global_id='g1', camera_tracks={1: 't1'},
        active_tracks={(1, 't1')},
        embeddings=[emb], dominant_hsv_history=[(100, 150, 150)],
        last_track=_Track('t1', 1, np.array([0, 0, 40, 40], dtype=np.float32),
                          motion_state=MOTION_STATIC),
    )
    track = _edge_track('t2', 2, x_left=480)  # mid-frame, far from both edges
    assert matcher.best_match([identity], track, now=1.0) is None


def test_best_match_rejects_motion_mismatch_a2():
    """A2: identity STATIC, incoming TRANSITING → motion incompatible → None."""
    matcher = _matcher_with_adjacency()
    emb = _unit([1.0, 0.0, 0.0])
    identity = _Identity(
        global_id='g1', camera_tracks={1: 't1'},
        active_tracks={(1, 't1')},
        embeddings=[emb], dominant_hsv_history=[(100, 150, 150)],
        last_track=_Track('t1', 1, np.array([0, 0, 40, 40], dtype=np.float32),
                          motion_state=MOTION_STATIC),
    )
    track = _edge_track('t2', 2, x_left=10)
    track.motion_state = MOTION_TRANSITING
    assert matcher.best_match([identity], track, now=1.0) is None


def test_best_match_rejects_when_margin_too_small():
    """Two near-identical candidates within min_margin → ambiguous → None (A1 guard)."""
    matcher = _matcher_with_adjacency()
    emb = _unit([1.0, 0.0, 0.0])

    def _id(gid, cam, tid):
        return _Identity(
            global_id=gid, camera_tracks={cam: tid},
            active_tracks={(cam, tid)},
            embeddings=[emb], dominant_hsv_history=[(100, 150, 150)],
            last_track=_Track(tid, cam, np.array([0, 0, 40, 40], dtype=np.float32),
                              motion_state=MOTION_STATIC),
        )

    id1 = _id('g1', 1, 't1')
    id3 = _id('g3', 3, 't3')  # both adjacent to camera 2
    track = _edge_track('t2', 2, x_left=10)
    # both score ~equally high → margin < 0.12 → reject
    assert matcher.best_match([id1, id3], track, now=1.0) is None

"""Tests for E5 — seam resurrect color + OCR-conflict gate."""
from __future__ import annotations

import time

import numpy as np
import pytest

from app.services.ai.background_model import BackgroundModelRegistry, BackgroundModelConfig
from app.services.ai.boat_tracker import TrackState, TrackedBoat
from app.services.ai.seam_anchor_verifier import (
    AnchorState,
    SeamAnchorConfig,
    SeamAnchorVerifier,
)


def _verifier(**cfg_overrides) -> SeamAnchorVerifier:
    cfg_kwargs = dict(
        enabled=True,
        iou_resurrect_threshold=0.3,
        embedding_match_enabled=True,
        embedding_sim_threshold=0.65,
        color_hsv_tolerance_h=15,
    )
    cfg_kwargs.update(cfg_overrides)
    cfg = SeamAnchorConfig(**cfg_kwargs)
    bg_registry = BackgroundModelRegistry(BackgroundModelConfig())
    return SeamAnchorVerifier(
        bg_registry=bg_registry,
        camera_order=[1, 2],
        config=cfg,
    )


def _last_track(camera_id: int = 1) -> TrackedBoat:
    return TrackedBoat(
        track_id='t1',
        state=TrackState.REMOVED,
        box=np.array([10, 10, 50, 50], dtype=np.float32),
        conf=0.9,
        hits=3,
        misses=0,
        first_seen_ts=1.0,
        last_seen_ts=2.0,
        ship_id=None,
        camera_id=camera_id,
        ever_confirmed=True,
    )


def _anchor(
    *,
    global_id: str = 'gid_x',
    ship_id: str | None = None,
    dominant_hsv: tuple[int, int, int] | None = None,
    embedding: np.ndarray | None = None,
) -> AnchorState:
    now = time.time()
    return AnchorState(
        global_id=global_id,
        ship_id=ship_id,
        track_id='t1',
        cam_a_id=1,
        cam_b_id=2,
        bbox_a=(10, 10, 40, 40),  # xywh
        bbox_b=None,
        embedding=embedding,
        first_seen_ts=now,
        last_seen_ts=now,
        last_validated_at=now,
        miss_started_at=None,
        anchored_at=now,
        last_track=_last_track(),
        dominant_color_hsv=dominant_hsv,
    )


def _register(verifier: SeamAnchorVerifier, anchor: AnchorState) -> None:
    """Insert anchor directly into the verifier's internal map for testing."""
    with verifier._lock:
        verifier._anchors[anchor.global_id] = anchor


def _matching_bbox() -> np.ndarray:
    # xyxy overlapping bbox_a=(10,10,40,40) → xyxy (10,10,50,50)
    return np.array([10, 10, 50, 50], dtype=np.float32)


def test_resurrect_succeeds_without_extra_evidence():
    """Baseline: high IoU, no embedding gate, no HSV/ship_id → resurrect succeeds."""
    verifier = _verifier(embedding_match_enabled=False)
    _register(verifier, _anchor())
    result = verifier.try_resurrect(1, _matching_bbox(), embedding=None)
    assert result == 'gid_x'


def test_resurrect_rejected_on_conflicting_ship_id():
    """E5: incoming ship_id differs from anchor ship_id (both known) → reject."""
    verifier = _verifier(embedding_match_enabled=False)
    _register(verifier, _anchor(ship_id='BD-0001'))
    result = verifier.try_resurrect(
        1, _matching_bbox(), embedding=None, ship_id='BD-9999'
    )
    assert result is None


def test_resurrect_allowed_when_ship_ids_match():
    """Same ship_id → gate does not block."""
    verifier = _verifier(embedding_match_enabled=False)
    _register(verifier, _anchor(ship_id='BD-0001'))
    result = verifier.try_resurrect(
        1, _matching_bbox(), embedding=None, ship_id='BD-0001'
    )
    assert result == 'gid_x'


def test_resurrect_allowed_when_incoming_ship_id_unknown():
    """Incoming ship_id is unknown/blank → gate is permissive (no conflict)."""
    verifier = _verifier(embedding_match_enabled=False)
    _register(verifier, _anchor(ship_id='BD-0001'))
    result = verifier.try_resurrect(
        1, _matching_bbox(), embedding=None, ship_id=''
    )
    assert result == 'gid_x'


def test_resurrect_rejected_on_color_mismatch():
    """E5: anchor HSV and incoming HSV differ beyond tolerance → reject."""
    verifier = _verifier(embedding_match_enabled=False, color_hsv_tolerance_h=15)
    _register(verifier, _anchor(dominant_hsv=(20, 200, 200)))
    # incoming hue far from 20 (hue 120), beyond tolerance 15
    result = verifier.try_resurrect(
        1, _matching_bbox(), embedding=None, dominant_hsv=(120, 200, 200)
    )
    assert result is None


def test_resurrect_allowed_on_color_match():
    """Anchor HSV and incoming HSV within tolerance → gate does not block."""
    verifier = _verifier(embedding_match_enabled=False, color_hsv_tolerance_h=15)
    _register(verifier, _anchor(dominant_hsv=(20, 200, 200)))
    result = verifier.try_resurrect(
        1, _matching_bbox(), embedding=None, dominant_hsv=(25, 200, 200)
    )
    assert result == 'gid_x'


def test_resurrect_permissive_when_anchor_has_no_hsv():
    """Anchor has no dominant_color_hsv (e.g. restored from DB) → HSV gate skipped."""
    verifier = _verifier(embedding_match_enabled=False)
    _register(verifier, _anchor(dominant_hsv=None))
    result = verifier.try_resurrect(
        1, _matching_bbox(), embedding=None, dominant_hsv=(120, 200, 200)
    )
    assert result == 'gid_x'

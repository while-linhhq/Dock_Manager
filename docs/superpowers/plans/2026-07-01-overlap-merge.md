# Concurrent Overlap Merge (Phần 2 + A2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge two `GlobalIdentity` records when the same boat is seen **concurrently** on two adjacent (overlapping-FOV) cameras, even without OCR — using a weighted fusion of embedding cosine, HSV color similarity, and box-size ratio, gated by adjacency, edge-zone, single-boat, and motion-state (A2) checks.

**Architecture:** A new `OverlapMergeMatcher` (`handoff_matcher.py`) holds the gate + scoring logic. `CrossCameraReIdManager` stores a rolling `dominant_hsv_history` on each identity, relaxes the non-adjacent concurrent-active block for adjacent+edge-zone tracks, and calls the matcher as step 4 in `_match_existing_identity` (between strong embedding cosine and new-identity creation). All matcher params come from the `reid_*` config keys added in the **Re-ID Config Params (Phần 3)** plan — that plan must land first.

**Tech Stack:** Python, NumPy, dataclasses, pytest. Reuses `extract_dominant_hsv`/`hsv_matches` from `seam_anchor_color.py`, `cosine_similarity` from `embedding_extractor.py`, `MOTION_STATIC` from `motion_classifier.py`.

**Dependency:** Requires `docs/superpowers/plans/2026-07-01-reid-config-params.md` (Phần 3) merged — the `reid_*` keys must exist in `runtime_cfg`.

---

## Files

- Create: `server/app/services/ai/handoff_matcher.py` — `OverlapMergeConfig` + `OverlapMergeMatcher`.
- Modify: `server/app/services/ai/cross_camera_reid.py`:
  - `GlobalIdentity` dataclass (~line 28–46): add `dominant_hsv_history`.
  - `__init__` (~line 58–85): accept overlap-merge config + construct matcher.
  - `_attach_track` (~line 415–435): append HSV history.
  - `_match_existing_identity` (~line 437–474): insert matcher as step 4.
  - `_has_concurrent_active_on_non_adjacent_camera` already relaxes adjacency (line 582) — reuse, no change.
- Modify: `server/app/services/pipeline_service.py:1650-1658` — pass overlap-merge config into `CrossCameraReIdManager`.
- Test: `server/app/tests/test_overlap_merge.py`.

---

### Task 1: `OverlapMergeMatcher` — config + scoring (TDD)

**Files:**
- Create: `server/app/tests/test_overlap_merge.py`
- Create: `server/app/services/ai/handoff_matcher.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run RED**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_overlap_merge.py -v 2>&1 | head -30
```

Expected: FAIL with `ImportError: cannot import name 'OverlapMergeMatcher'`.

- [ ] **Step 3: Implement `handoff_matcher.py`**

```python
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
    def __init__(self, config: OverlapMergeConfig) -> None:
        self._config = config

    def score(self, identity: Any, track: Any) -> float:
        """Weighted fusion in [0,1]. Box uses xyxy via _box_to_xyxy on the caller side;
        here we read identity.last_track.box and track.box directly (both xywh-or-xyxy
        consistent within the manager)."""
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
```

- [ ] **Step 4: Run GREEN**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_overlap_merge.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/handoff_matcher.py server/app/tests/test_overlap_merge.py
git commit -m "feat(reid): add OverlapMergeMatcher scoring fusion"
```

---

### Task 2: Matcher gates — adjacency, edge-zone, single-boat, motion (A2) (TDD)

**Files:**
- Modify: `server/app/tests/test_overlap_merge.py`
- Modify: `server/app/services/ai/handoff_matcher.py`

- [ ] **Step 1: Append failing gate tests**

```python
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


def test_best_match_accepts_single_adjacent_edge_candidate():
    """One adjacent identity, track in edge zone, matching motion → merge accepted."""
    from app.services.ai.motion_classifier import MOTION_STATIC
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
    from app.services.ai.motion_classifier import MOTION_STATIC
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
    from app.services.ai.motion_classifier import MOTION_STATIC
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
    from app.services.ai.motion_classifier import MOTION_STATIC, MOTION_TRANSITING
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
    from app.services.ai.motion_classifier import MOTION_STATIC
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
```

- [ ] **Step 2: Run RED**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_overlap_merge.py -v 2>&1 | head -40
```

Expected: FAIL — `OverlapMergeMatcher.__init__` takes no `is_adjacent`/`frame_width_for`; no `best_match`/`candidate_identities`.

- [ ] **Step 3: Extend the matcher with gates + `best_match`**

Replace the `__init__` and add `candidate_identities`/`best_match` to `OverlapMergeMatcher` in `handoff_matcher.py`:

```python
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
```

- [ ] **Step 4: Run GREEN**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_overlap_merge.py -v
```

Expected: all tests pass (2 from Task 1 + 5 gate tests).

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/handoff_matcher.py server/app/tests/test_overlap_merge.py
git commit -m "feat(reid): OverlapMergeMatcher gates — adjacency, edge-zone, single-boat, A2 motion"
```

---

### Task 3: Store `dominant_hsv_history` on `GlobalIdentity`

**Files:**
- Modify: `server/app/services/ai/cross_camera_reid.py:28-46` (GlobalIdentity dataclass)
- Modify: `server/app/services/ai/cross_camera_reid.py:415-435` (_attach_track)

- [ ] **Step 1: Add the field**

In the `GlobalIdentity` dataclass, after `events_written: bool = False`:

```python
    events_written: bool = False
    dominant_hsv_history: list[tuple[int, int, int]] = field(default_factory=list)
```

- [ ] **Step 2: Append HSV in `_attach_track`**

In `_attach_track`, after the embedding-append block (after `identity.embeddings = identity.embeddings[-20:]`), add:

```python
        hsv = getattr(track, 'dominant_color_hsv', None)
        if hsv is not None:
            identity.dominant_hsv_history.append(tuple(int(v) for v in hsv))
            identity.dominant_hsv_history = identity.dominant_hsv_history[-20:]
```

- [ ] **Step 3: Verify import + dataclass construct**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "from app.services.ai.cross_camera_reid import GlobalIdentity; g=GlobalIdentity(global_id='x', ship_id=None, camera_tracks={}); print(g.dominant_hsv_history)"
```

Expected: `[]`

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/cross_camera_reid.py
git commit -m "feat(reid): store rolling dominant_hsv_history on GlobalIdentity"
```

---

### Task 4: Wire matcher into `CrossCameraReIdManager`

**Files:**
- Modify: `server/app/services/ai/cross_camera_reid.py:58-85` (__init__)
- Modify: `server/app/services/ai/cross_camera_reid.py:437-474` (_match_existing_identity)

- [ ] **Step 1: Accept config + build matcher in `__init__`**

Add an `overlap_merge_config` keyword param to `__init__` (after `is_track_identity_locked`):

```python
        is_track_identity_locked: Callable[[int, str], bool] | None = None,
        overlap_merge_config: 'OverlapMergeConfig | None' = None,
    ) -> None:
```

At the top of the file, add the import (near the other `app.services.ai` imports):

```python
from app.services.ai.handoff_matcher import OverlapMergeConfig, OverlapMergeMatcher
```

At the end of `__init__` (after `self._lock = threading.RLock()`), construct the matcher with adjacency + frame-width callbacks bound to the manager:

```python
        self._frame_width_by_camera: dict[int, float] = {}
        self._overlap_matcher = OverlapMergeMatcher(
            overlap_merge_config or OverlapMergeConfig(),
            is_adjacent=self._cameras_are_adjacent_pair,
            frame_width_for=lambda cam: self._frame_width_by_camera.get(int(cam), 0.0),
        )
```

- [ ] **Step 2: Record frame width in `report_track_update`**

Frame width is needed by the edge-zone gate. In `report_track_update`, right after `camera_key = int(camera_id)` (line ~164), capture width from `frame_shape` (shape is `(h, w)`):

```python
            camera_key = int(camera_id)
            if frame_shape is not None and len(frame_shape) >= 2:
                self._frame_width_by_camera[camera_key] = float(frame_shape[1])
```

- [ ] **Step 3: Insert matcher as step 4 in `_match_existing_identity`**

In `_match_existing_identity`, the current tail is (lines ~472–474):

```python
        if best_identity is not None and best_score >= self._visual_threshold:
            return best_identity
        return None
```

Replace with:

```python
        if best_identity is not None and best_score >= self._visual_threshold:
            return best_identity

        # Step 4: overlap merge (weak fusion signal) — boat seen concurrently on
        # an adjacent overlapping-FOV camera, no strong embedding / OCR.
        try:
            overlap_gid = self._overlap_matcher.best_match(
                list(self._identities.values()),
                track,
                now,
            )
        except Exception:
            _log.exception('reid: overlap merge matcher failed')
            overlap_gid = None
        if overlap_gid is not None:
            return self._identities.get(overlap_gid)

        return None
```

Note: `track.camera_id` must be set for the matcher's adjacency/edge gates. `_match_existing_identity` is called from `report_track_update` where `track` is the live `TrackedBoat`; `camera_id` is already populated by the per-camera pipeline. The matcher reads `track.camera_id`, so no extra threading needed.

- [ ] **Step 4: Run the reid regression suite**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_overlap_merge.py app/tests/test_inout_dedup.py app/tests/test_ship_id_lock.py -v 2>&1 | tail -30
```

Expected: all pass. The overlap matcher only fires when strong embedding (step 3) already failed, so existing tests are unaffected.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/cross_camera_reid.py
git commit -m "feat(reid): wire OverlapMergeMatcher as step 4 in identity matching"
```

---

### Task 5: Pass config from pipeline into the manager

**Files:**
- Modify: `server/app/services/pipeline_service.py:1650-1658` (CrossCameraReIdManager construction)

- [ ] **Step 1: Build `OverlapMergeConfig` from runtime_cfg and pass it**

Locate the `CrossCameraReIdManager(...)` construction (lines 1650–1658). Add the import near the top of the file (with the other `app.services.ai` imports):

```python
from app.services.ai.handoff_matcher import OverlapMergeConfig
```

Update the construction to pass the config:

```python
        self._reid_manager = CrossCameraReIdManager(
            camera_order=camera_order,
            visual_threshold=runtime_cfg['reid_visual_threshold'],
            handoff_window_sec=runtime_cfg['reid_handoff_window_sec'],
            primary_zone_ratio=runtime_cfg['primary_zone_ratio'],
            edge_zone_ratio=runtime_cfg['edge_zone_ratio'],
            on_global_track_removed=combined_on_removed,
            ship_id_catalog=self._ship_id_catalog,
            overlap_merge_config=OverlapMergeConfig(
                enabled=bool(runtime_cfg['reid_overlap_merge_enabled']),
                edge_zone_ratio=float(runtime_cfg['reid_edge_zone_ratio']),
                embedding_weight=float(runtime_cfg['reid_embedding_weight']),
                color_weight=float(runtime_cfg['reid_color_weight']),
                size_weight=float(runtime_cfg['reid_size_weight']),
                accept_threshold=float(runtime_cfg['reid_accept_threshold']),
                min_margin=float(runtime_cfg['reid_min_margin']),
            ),
        )
```

- [ ] **Step 2: Verify import**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "from app.services.pipeline_service import PipelineService; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full server test suite**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/ --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/pipeline_service.py
git commit -m "feat(reid): pass overlap-merge config into CrossCameraReIdManager"
```

---

## Self-review

- **Spec coverage (Phần 2):** `OverlapMergeMatcher` with `candidate_identities`/`score`/`best_match` (spec lines 61–76) ✓; gate cứng (adjacency, edge-zone, single-boat per camera, motion A2) ✓; fusion weights `reid_embedding_weight`/`reid_color_weight`/`reid_size_weight` ✓; accept on `reid_accept_threshold` + `reid_min_margin` ✓; inserted as step 4 between strong embedding and new-identity (spec lines 78–86) ✓; `dominant_hsv_history` rolling cap 20 (spec line 88) ✓.
- **A2 motion gate (Phần 4):** folded into `_motion_compatible` — merge only when motion states compatible (both STATIC, or both moving). Unknown motion is permissive so the gate never blocks legitimate merges when classifier output is absent.
- **Relaxing the concurrent-active block:** the spec asks to stop blocking embedding match for adjacent+edge pairs. The codebase already split this into `_has_concurrent_active_on_non_adjacent_camera` (line 582, used by step 3) which permits adjacent concurrency — so the strong-embedding path already allows adjacent overlap; the matcher adds the weak-signal path. No further change needed there.
- **Type consistency:** `OverlapMergeConfig` field names match across `handoff_matcher.py`, the manager `__init__`, and `pipeline_service.py`. `best_match` returns `global_id: str | None`; the manager maps it back to a `GlobalIdentity` via `self._identities.get(...)`. `score()` signature is identical in both tasks.
- **Box coordinate note:** `score()`'s `_box_size_ratio` and the edge-zone center use `box` as xyxy. `TrackedBoat.box` in this codebase is xyxy (per `bbox_to_xyxy` usage in seam anchor), so area = `(x2-x1)*(y2-y1)` is correct. Tests construct boxes as `[x1,y1,x2,y2]`.

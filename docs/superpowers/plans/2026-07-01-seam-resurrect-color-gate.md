# Seam Resurrect Color + OCR-Conflict Gate (E5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chặn seam-anchor resurrect nhầm tàu khác: thêm HSV color gate (cạnh embedding gate 0.65 sẵn có) và từ chối resurrect khi incoming track có OCR ship_id khác ship_id của anchor.

**Architecture:** Mở rộng `SeamAnchorVerifier.try_resurrect()` nhận thêm 2 tham số optional (`dominant_hsv`, `ship_id`). Sau khi qua gate IoU và embedding, chạy thêm: (1) ship_id gate — nếu cả hai ship_id đều hợp lệ (known) và khác nhau → từ chối; (2) HSV gate — nếu anchor có `dominant_color_hsv` và incoming có HSV, dùng `hsv_matches()` với `color_hsv_tolerance_h`; không khớp → từ chối. Cập nhật call site trong `cross_camera_reid.py` để truyền HSV + ship_id từ `TrackedBoat`.

**Tech Stack:** Python, NumPy, pytest. Tái dùng `hsv_matches` từ `seam_anchor_color.py`, `normalize_ship_id`/`is_unknown_ship_id` từ `ship_id_utils.py`. Không thêm config key mới — dùng `SeamAnchorConfig.color_hsv_tolerance_h` (default 15) đã có.

**Dependency:** Không phụ thuộc plan khác. Có thể land độc lập.

---

## Files

- Modify: `server/app/services/ai/seam_anchor_verifier.py`:
  - `try_resurrect` (~line 344–395): thêm params `dominant_hsv`, `ship_id`; thêm 2 gate.
- Modify: `server/app/services/ai/cross_camera_reid.py`:
  - call site `try_resurrect` (~line 170–174): truyền HSV + ship_id.
- Create: `server/app/tests/test_seam_resurrect_gate.py` — test 2 gate.

---

### Task 1: Viết failing tests cho ship_id gate + HSV gate

**Files:**
- Create: `server/app/tests/test_seam_resurrect_gate.py`

- [ ] **Step 1: Tạo file test**

```python
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
    cfg = SeamAnchorConfig(
        enabled=True,
        iou_resurrect_threshold=0.3,
        embedding_match_enabled=True,
        embedding_sim_threshold=0.65,
        color_hsv_tolerance_h=15,
        **cfg_overrides,
    )
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
```

- [ ] **Step 2: Chạy RED**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_seam_resurrect_gate.py -v 2>&1 | head -40
```

Expected: FAIL — `try_resurrect()` chưa nhận `ship_id`/`dominant_hsv` (TypeError: unexpected keyword argument), hoặc gate chưa tồn tại nên `test_resurrect_rejected_*` fail (trả về `'gid_x'` thay vì `None`).

- [ ] **Step 3: Commit test**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/tests/test_seam_resurrect_gate.py
git commit -m "test(reid): add failing seam resurrect color + ship_id gate tests"
```

---

### Task 2: Thêm ship_id gate + HSV gate vào `try_resurrect`

**Files:**
- Modify: `server/app/services/ai/seam_anchor_verifier.py:344-395`

- [ ] **Step 1: Thêm import `is_unknown_ship_id`, `normalize_ship_id`**

Ở đầu file, sau dòng import `from app.services.ai.motion_classifier import MOTION_STATIC`, thêm:

```python
from app.services.ship_id_utils import is_unknown_ship_id, normalize_ship_id
```

- [ ] **Step 2: Sửa signature + thêm 2 gate**

Thay method `try_resurrect` (dòng ~344–395) bằng:

```python
    def try_resurrect(
        self,
        camera_id: int,
        bbox: np.ndarray,
        embedding: np.ndarray | None = None,
        *,
        dominant_hsv: tuple[int, int, int] | None = None,
        ship_id: str | None = None,
    ) -> str | None:
        if not self._config.enabled:
            return None

        best_id: str | None = None
        best_iou = 0.0

        with self._lock:
            candidates = list(self._anchors.values())

        for anchor in candidates:
            roi: tuple[int, int, int, int] | None = None
            if anchor.cam_a_id == int(camera_id):
                roi = anchor.bbox_a
            elif anchor.cam_b_id == int(camera_id) and anchor.bbox_b is not None:
                roi = anchor.bbox_b
            if roi is None:
                continue
            iou = _iou_xyxy_from_xywh(bbox_to_xyxy(np.asarray(bbox, dtype=np.float32)), roi)
            if iou > best_iou:
                best_iou = iou
                best_id = anchor.global_id

        if best_id is None or best_iou < self._config.iou_resurrect_threshold:
            return None

        with self._lock:
            anchor = self._anchors.get(best_id)

        # E5 gate 1: reject if incoming OCR ship_id conflicts with anchor ship_id
        if anchor is not None and anchor.ship_id:
            incoming = normalize_ship_id(ship_id) if ship_id else ''
            anchor_sid = normalize_ship_id(anchor.ship_id)
            if (
                incoming
                and not is_unknown_ship_id(incoming)
                and anchor_sid
                and not is_unknown_ship_id(anchor_sid)
                and incoming != anchor_sid
            ):
                _log.info(
                    'seam_anchor: skip resurrect %s — ship_id conflict incoming=%s anchor=%s',
                    best_id,
                    incoming,
                    anchor_sid,
                )
                return None

        # E5 gate 2: reject if dominant color mismatches beyond hue tolerance
        if (
            anchor is not None
            and anchor.dominant_color_hsv is not None
            and dominant_hsv is not None
        ):
            if not hsv_matches(
                anchor.dominant_color_hsv,
                tuple(int(v) for v in dominant_hsv),
                tolerance_h=self._config.color_hsv_tolerance_h,
            ):
                _log.info(
                    'seam_anchor: skip resurrect %s — color mismatch anchor=%s incoming=%s',
                    best_id,
                    anchor.dominant_color_hsv,
                    tuple(int(v) for v in dominant_hsv),
                )
                return None

        if self._config.embedding_match_enabled and embedding is not None:
            if anchor is not None and anchor.embedding is not None:
                sim = cosine_similarity(anchor.embedding, embedding)
                if sim < self._config.embedding_sim_threshold:
                    _log.info(
                        'seam_anchor: skip resurrect %s due to low embedding sim=%.3f',
                        best_id,
                        sim,
                    )
                    return None

        self._release_internal(best_id, notify_release=False)
        _log.info(
            'seam_anchor: resurrect global_id=%s camera_id=%s iou=%.3f',
            best_id,
            camera_id,
            best_iou,
        )
        return best_id
```

Note: `hsv_matches` đã được import ở đầu file (dòng `from app.services.ai.seam_anchor_color import extract_dominant_hsv, hsv_matches`). Không cần import lại.

- [ ] **Step 3: Chạy GREEN**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_seam_resurrect_gate.py -v
```

Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/seam_anchor_verifier.py
git commit -m "feat(reid): add color + ship_id conflict gate to seam resurrect (E5)"
```

---

### Task 3: Truyền HSV + ship_id từ call site trong `cross_camera_reid.py`

**Files:**
- Modify: `server/app/services/ai/cross_camera_reid.py:170-174`

- [ ] **Step 1: Cập nhật call site `try_resurrect`**

Tìm block (dòng ~169–174):

```python
            if identity is None and self._seam_anchor_verifier is not None:
                resurrected_id = self._seam_anchor_verifier.try_resurrect(
                    camera_key,
                    track.box,
                    embedding,
                )
```

Thay bằng:

```python
            if identity is None and self._seam_anchor_verifier is not None:
                resurrected_id = self._seam_anchor_verifier.try_resurrect(
                    camera_key,
                    track.box,
                    embedding,
                    dominant_hsv=getattr(track, 'dominant_color_hsv', None),
                    ship_id=track.ship_id or track.last_known_ship_id,
                )
```

- [ ] **Step 2: Verify import + no regression trên reid suite**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "from app.services.ai.cross_camera_reid import CrossCameraReIdManager; print('OK')"
conda run -n demo_core python -m pytest app/tests/test_seam_resurrect_gate.py app/tests/test_inout_dedup.py app/tests/test_ship_id_lock.py -v 2>&1 | tail -20
```

Expected: `OK`, tất cả test pass. Call site mới chỉ thêm 2 kwarg optional; các gate permissive khi thiếu HSV/ship_id nên hành vi cũ (resurrect khi khớp IoU + embedding) không đổi.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/cross_camera_reid.py
git commit -m "feat(reid): pass dominant_hsv + ship_id into seam resurrect gate (E5)"
```

---

## Self-review

- **Spec coverage (E5):** "thêm HSV gate cạnh embedding gate 0.65" → gate 2 dùng `hsv_matches` với `color_hsv_tolerance_h`, chạy trước embedding gate ✓. "nếu incoming có OCR ship_id khác anchor → từ chối resurrect" → gate 1, chỉ chặn khi cả hai ship_id đều known và khác nhau ✓.
- **No new config key:** dùng `SeamAnchorConfig.color_hsv_tolerance_h` (default 15) — spec Phần 3 không liệt kê key mới cho E5, đúng chủ trương "Giữ nguyên param seam anchor".
- **Backward compat:** cả 2 param mới là keyword-only optional với default `None`. Gate permissive khi thiếu dữ liệu (anchor không có HSV — ví dụ anchor khôi phục từ DB không persist `dominant_color_hsv`; incoming ship_id blank/unknown). Nên không phá vỡ resurrect hợp lệ hiện tại.
- **Type consistency:** `try_resurrect` giữ nguyên return `str | None`. `dominant_hsv` là `tuple[int,int,int] | None`, ép `tuple(int(v) for v in ...)` trước khi so khớp — khớp chữ ký `hsv_matches(baseline, sample, *, tolerance_h)`. `normalize_ship_id`/`is_unknown_ship_id` cùng nguồn `ship_id_utils` đã dùng trong `report_ocr_result`.
- **Anchor lookup:** dùng lại `self._anchors.get(best_id)` dưới lock (giống block embedding gốc) để đọc `ship_id`/`dominant_color_hsv`/`embedding` an toàn.

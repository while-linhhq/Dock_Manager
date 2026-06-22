# Berth Zone Overlap % Overlay — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiển thị % diện tích bbox nằm trong vùng nhận (`berth_zone`) trên overlay camera đơn và fused dashboard preview.

**Architecture:** `BoundaryCrossingTracker` expose `zone_overlap_ratio()`. Mỗi frame CONFIRMED, `PerCameraPipeline` gán `berth_zone_overlap` + `berth_zone_threshold` lên `TrackedBoat`. Helper chung trong `overlay.py` format text/màu; `draw_ship_detection_overlay` và `draw_fused_track_overlay` đọc từ track.

**Tech Stack:** Python 3.11, OpenCV, pytest; không đổi frontend/DB/port_configs.

---

## File Map

| File | Thay đổi |
|------|----------|
| `server/app/services/ai/boundary_crossing.py` | Public `zone_overlap_ratio()` |
| `server/app/services/ai/boat_tracker.py` | 2 field mới + `copy_public()` |
| `server/app/services/ai/per_camera_pipeline.py` | Gán overlap mỗi frame |
| `server/app/utils/ai/overlay.py` | Helper `berth_zone_overlay_line()` + vẽ trên single-cam |
| `server/app/utils/ai/fused_track_overlay.py` | Thêm dòng ZONE vào panel |
| `server/app/tests/test_boundary_crossing.py` | Test public API overlap |

---

## Task 1: Public `zone_overlap_ratio` trên `BoundaryCrossingTracker`

**Files:**
- Modify: `server/app/services/ai/boundary_crossing.py:253-260`
- Test: `server/app/tests/test_boundary_crossing.py`

- [ ] **Step 1.1: Thêm failing test**

Thêm vào cuối `server/app/tests/test_boundary_crossing.py`:

```python
def test_zone_overlap_ratio_public_api_matches_internal_geometry():
    trk = BoundaryCrossingTracker(_cfg(threshold=0.30))
    # bbox fully inside zone -> ~100%
    ratio = trk.zone_overlap_ratio((35, 40, 55, 60), frame_w=100, frame_h=100)
    assert ratio >= 0.99

    # bbox fully outside -> 0%
    ratio_out = trk.zone_overlap_ratio((5, 40, 20, 60), frame_w=100, frame_h=100)
    assert ratio_out == 0.0

    assert trk.config.bbox_cross_threshold == 0.30
```

- [ ] **Step 1.2: Chạy test — expect FAIL**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n bason-dock pytest app/tests/test_boundary_crossing.py::test_zone_overlap_ratio_public_api_matches_internal_geometry -v
```

Expected: `AttributeError: 'BoundaryCrossingTracker' object has no attribute 'zone_overlap_ratio'`

- [ ] **Step 1.3: Thêm method public**

Trong `BoundaryCrossingTracker`, ngay sau `_zone_overlap_ratio`:

```python
    def zone_overlap_ratio(
        self,
        box: Bbox,
        frame_w: int,
        frame_h: int,
    ) -> float:
        """Fraction of bbox area inside berth_zone (0.0–1.0), scaled to current frame."""
        scaled_box = self._scaled_box(box, frame_w, frame_h)
        return self._zone_overlap_ratio(scaled_box, frame_w, frame_h)
```

- [ ] **Step 1.4: Chạy test — expect PASS**

```bash
conda run -n bason-dock pytest app/tests/test_boundary_crossing.py::test_zone_overlap_ratio_public_api_matches_internal_geometry -v
```

- [ ] **Step 1.5: Commit**

```bash
git add server/app/services/ai/boundary_crossing.py server/app/tests/test_boundary_crossing.py
git commit -m "feat(boundary): expose zone_overlap_ratio on BoundaryCrossingTracker"
```

---

## Task 2: Thêm field overlap lên `TrackedBoat`

**Files:**
- Modify: `server/app/services/ai/boat_tracker.py:59-105`

- [ ] **Step 2.1: Thêm fields**

Sau `berth_out_ts`:

```python
    berth_zone_overlap: float | None = None   # 0.0–1.0, None = no boundary config
    berth_zone_threshold: float | None = None  # bbox_cross_threshold when boundary active
```

- [ ] **Step 2.2: Cập nhật `copy_public()`**

```python
            berth_zone_overlap=self.berth_zone_overlap,
            berth_zone_threshold=self.berth_zone_threshold,
```

- [ ] **Step 2.3: Smoke test**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n bason-dock python -c "
from app.services.ai.boat_tracker import TrackedBoat, TrackState
import numpy as np
t = TrackedBoat(track_id='t1', state=TrackState.CONFIRMED, box=np.zeros(4),
                conf=0.9, hits=1, misses=0, first_seen_ts=0.0, last_seen_ts=0.0,
                berth_zone_overlap=0.42, berth_zone_threshold=0.30)
cp = t.copy_public()
assert cp.berth_zone_overlap == 0.42
assert cp.berth_zone_threshold == 0.30
print('OK')
"
```

- [ ] **Step 2.4: Commit**

```bash
git commit -am "feat(tracker): add berth zone overlap fields to TrackedBoat"
```

---

## Task 3: Gán overlap mỗi frame trong `PerCameraPipeline`

**Files:**
- Modify: `server/app/services/ai/per_camera_pipeline.py:261-291`

- [ ] **Step 3.1: Reset + gán trong boundary loop**

Trong `_process_frame`, block `if self._boundary_tracker is not None:` — đầu vòng `for track in tracked_boats`:

```python
        if self._boundary_tracker is not None:
            h, w = raw_frame.shape[:2]
            now_ts = time.time()
            threshold = float(self._boundary_tracker.config.bbox_cross_threshold)
            for track in tracked_boats:
                if track.state != TrackState.CONFIRMED:
                    track.berth_zone_overlap = None
                    track.berth_zone_threshold = None
                    continue
                box = track.box
                track.berth_zone_overlap = self._boundary_tracker.zone_overlap_ratio(
                    (float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    w,
                    h,
                )
                track.berth_zone_threshold = threshold
                direction = self._boundary_tracker.update(
                    ...
```

Thêm nhánh `else` sau block boundary (khi không có boundary tracker) để clear field:

```python
        else:
            for track in tracked_boats:
                track.berth_zone_overlap = None
                track.berth_zone_threshold = None
```

- [ ] **Step 3.2: Import smoke**

```bash
conda run -n bason-dock python -c "from app.services.ai.per_camera_pipeline import PerCameraPipeline; print('OK')"
```

- [ ] **Step 3.3: Commit**

```bash
git add server/app/services/ai/per_camera_pipeline.py
git commit -m "feat(pipeline): populate berth zone overlap on TrackedBoat each frame"
```

---

## Task 4: Helper overlay + single-camera display

**Files:**
- Modify: `server/app/utils/ai/overlay.py`

- [ ] **Step 4.1: Thêm helper** (trước `draw_ship_detection_overlay`)

```python
def berth_zone_overlay_line(
    overlap: float | None,
    threshold: float | None,
) -> tuple[str, tuple[int, int, int]] | None:
    """Return (label, bgr_color) e.g. ('ZONE: 42% / 30%', green)."""
    if overlap is None or threshold is None:
        return None
    pct = int(round(max(0.0, min(1.0, overlap)) * 100))
    thr = int(round(max(0.0, min(1.0, threshold)) * 100))
    label = f'ZONE: {pct}% / {thr}%'
    if overlap >= threshold:
        color = (80, 220, 80)       # green — đạt ngưỡng IN
    elif overlap >= threshold * 0.85:
        color = (0, 210, 255)       # yellow — gần ngưỡng
    else:
        color = (80, 80, 255)       # red — dưới ngưỡng
    return label, color
```

- [ ] **Step 4.2: Vẽ trên single-cam** — trong vòng `for tb in tracked_boats:` đầu hàm, sau dòng `det:` (y - 38), thêm dòng ZONE ở y - 14:

```python
        zone_line = berth_zone_overlay_line(tb.berth_zone_overlap, tb.berth_zone_threshold)
        if zone_line is not None:
            zone_text, zone_color = zone_line
            cv2.putText(
                display_frame,
                zone_text,
                (x1, y1 - 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                zone_color,
                2,
            )
```

- [ ] **Step 4.3: Smoke import**

```bash
conda run -n bason-dock python -c "from app.utils.ai.overlay import berth_zone_overlay_line; print(berth_zone_overlay_line(0.42, 0.30))"
```

Expected: `('ZONE: 42% / 30%', ...)`

- [ ] **Step 4.4: Commit**

```bash
git add server/app/utils/ai/overlay.py
git commit -m "feat(overlay): show berth zone overlap percent on single-camera preview"
```

---

## Task 5: Fused overlay panel

**Files:**
- Modify: `server/app/utils/ai/fused_track_overlay.py`

- [ ] **Step 5.1: Import helper**

```python
from app.utils.ai.overlay import (
    BERTH_FILL_ALPHA,
    berth_fill_color_for_state,
    berth_zone_overlay_line,
    resolve_berth_visual_state,
    tint_bbox_overlay,
)
```

- [ ] **Step 5.2: Thêm vào `panel_lines`** — sau dòng ship_id/state, trước OCR block:

```python
            zone_line = berth_zone_overlay_line(
                track.berth_zone_overlap,
                track.berth_zone_threshold,
            )
            if zone_line is not None:
                zone_text, zone_color = zone_line
                panel_lines.append((zone_text.replace('ZONE: ', 'ZONE '), zone_color, 0.38))
```

- [ ] **Step 5.3: Smoke import**

```bash
conda run -n bason-dock python -c "from app.utils.ai.fused_track_overlay import draw_fused_track_overlay; print('OK')"
```

- [ ] **Step 5.4: Commit**

```bash
git add server/app/utils/ai/fused_track_overlay.py
git commit -m "feat(overlay): show berth zone overlap in fused track panel"
```

---

## Task 6: Full test suite + manual verify

- [ ] **Step 6.1: Chạy tests**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n bason-dock pytest app/tests/test_boundary_crossing.py -v
```

Expected: all PASS (including new test).

- [ ] **Step 6.2: Manual verify** (pipeline hybrid đang chạy)

1. Restart server nếu cần reload code
2. Mở dashboard preview (fused) + camera đơn có `boundary_lines` + `berth_zone`
3. Khi tàu CONFIRMED trong frame, thấy `ZONE: XX% / 30%` (XX thay đổi theo vị trí bbox)
4. Màu: xanh khi XX ≥ 30, vàng khi gần, đỏ khi thấp
5. Camera không có boundary → không hiện dòng ZONE

---

## Checklist hoàn thành

- [ ] `BoundaryCrossingTracker.zone_overlap_ratio()` public + tested
- [ ] `TrackedBoat.berth_zone_overlap` / `berth_zone_threshold` populated mỗi frame
- [ ] Single-cam overlay hiện `ZONE: XX% / YY%`
- [ ] Fused overlay panel hiện cùng thông tin
- [ ] Không đổi logic IN/OUT, không đổi port_configs / Boundary Editor

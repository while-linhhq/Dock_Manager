# OCR + Embedding Consensus Fusion & Enhanced Overlay — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay thế fallback OCR→embedding bằng consensus fusion song song, đồng thời hiển thị `global_id`, OCR, embedding, và kết quả cuối cùng lên frame overlay.

**Architecture:** `resolve_visual_match` được mở rộng thêm `conflict_threshold` param để xử lý 6 trường hợp (consensus / conflict-ocr / conflict-visual / ocr-hint / visual / unknown). `TrackedBoat` nhận thêm field `global_id` được gán tại `_enrich_track`. Overlay được viết lại để hiển thị 6 dòng thông tin per-track.

**Tech Stack:** Python 3.11, FastAPI, OpenCV, Qdrant, pytest; TypeScript + React (1 file frontend)

---

## File Map

| File | Thay đổi |
|------|----------|
| `server/app/utils/ai/visual_ship_matching.py` | Thêm `conflict_threshold` param, viết lại `if normalized_ocr:` branch |
| `server/app/services/ai/identity_fusion.py` | Thêm `conflict_threshold` vào `__init__`, pass to `resolve_visual_match` |
| `server/app/services/pipeline_service.py` | Load `visual_conflict_threshold` từ config, pass to `IdentityFusion` |
| `server/app/db/schema_patches.py` | Thêm `visual_conflict_threshold` vào `_DINOV2_PORT_CONFIG_VALUES` |
| `server/app/services/ai/boat_tracker.py` | Thêm `global_id: str | None = None` vào `TrackedBoat` + `copy_public` |
| `server/app/services/ai/cross_camera_reid.py` | Thêm `get_global_id()` method |
| `server/app/services/ai/per_camera_pipeline.py` | Set `track.global_id` trong `_enrich_track` |
| `server/app/utils/ai/overlay.py` | Viết lại per-track header, thêm `Final:` line, đổi `VEC`→`EMB` |
| `server/app/utils/ai/fused_track_overlay.py` | Thêm `gid:` line vào fused preview |
| `client/src/features/port/components/PortConfigsSection.tsx` | Thêm `visual_conflict_threshold: 'visual'` vào `KEY_PREFIX_MAP` |
| `server/app/tests/test_visual_ship_matching.py` | Cập nhật test cũ, thêm test mới cho consensus/conflict cases |

---

## Task 1: Cập nhật `resolve_visual_match` — consensus fusion logic

**Files:**
- Modify: `server/app/utils/ai/visual_ship_matching.py:72-143`
- Test: `server/app/tests/test_visual_ship_matching.py`

### Background

Hàm `resolve_visual_match` hiện tại có branch `if normalized_ocr:` trả về OCR unconditionally. Cần thay bằng 3 cases:
1. **Consensus**: OCR và visual khớp nhau → `source='consensus'`, conf boosted
2. **Conflict-visual-wins**: Khác nhau và `best.aggregated_score >= conflict_threshold` → visual wins
3. **Conflict-ocr-wins**: Khác nhau và `best.aggregated_score < conflict_threshold` → OCR wins

- [ ] **Step 1.1: Viết failing tests trước**

Mở `server/app/tests/test_visual_ship_matching.py`, thay toàn bộ nội dung thành:

```python
from app.utils.ai.visual_ship_matching import aggregate_visual_hits, resolve_visual_match


def test_aggregate_groups_by_ship_id():
    hits = [
        {'id': 'a1', 'score': 0.9, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'a2', 'score': 0.85, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'b1', 'score': 0.8, 'payload': {'ship_id': 'SG-7082'}},
    ]
    ranked = aggregate_visual_hits(hits, top_m_for_mean=2)
    assert ranked[0].ship_id == 'BD-0077'
    assert ranked[0].hit_count == 2
    assert ranked[0].aggregated_score > ranked[1].aggregated_score


def test_resolve_accepts_on_match_threshold_only():
    hits_ok = [
        {'id': 'a1', 'score': 0.82, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'b1', 'score': 0.68, 'payload': {'ship_id': 'SG-7082'}},
    ]
    decision_ok = resolve_visual_match(hits_ok, match_threshold=0.55)
    assert decision_ok.accepted is True
    assert decision_ok.ship_id == 'BD-0077'

    hits_low = [
        {'id': 'a1', 'score': 0.5, 'payload': {'ship_id': 'BD-0077'}},
    ]
    decision_low = resolve_visual_match(hits_low, match_threshold=0.55)
    assert decision_low.accepted is False
    assert decision_low.ship_id is None


def test_resolve_consensus_when_ocr_and_visual_agree():
    """Both OCR and visual return the same ship ID → source='consensus'."""
    hits = [
        {'id': 'a1', 'score': 0.9, 'payload': {'ship_id': 'BD-0077'}},
        {'id': 'b1', 'score': 0.6, 'payload': {'ship_id': 'SG-7082'}},
    ]
    decision = resolve_visual_match(
        hits, match_threshold=0.55, ocr_hint='BD-0077', conflict_threshold=0.96
    )
    assert decision.ship_id == 'BD-0077'
    assert decision.source == 'consensus'
    assert decision.accepted is True
    assert decision.confidence > 0.9  # boosted


def test_resolve_conflict_visual_wins_above_threshold():
    """OCR and visual disagree; visual score >= conflict_threshold → visual wins."""
    hits = [
        {'id': 'a1', 'score': 0.97, 'payload': {'ship_id': 'SG-7082'}},
    ]
    decision = resolve_visual_match(
        hits, match_threshold=0.55, ocr_hint='BD-0077', conflict_threshold=0.96
    )
    assert decision.ship_id == 'SG-7082'
    assert decision.source == 'conflict-visual-wins'
    assert decision.accepted is True


def test_resolve_conflict_ocr_wins_below_threshold():
    """OCR and visual disagree; visual score < conflict_threshold → OCR wins."""
    hits = [
        {'id': 'a1', 'score': 0.9, 'payload': {'ship_id': 'SG-7082'}},
    ]
    decision = resolve_visual_match(
        hits, match_threshold=0.55, ocr_hint='BD-0077', conflict_threshold=0.96
    )
    assert decision.ship_id == 'BD-0077'
    assert decision.source == 'conflict-ocr-wins'
    assert decision.accepted is True


def test_resolve_ocr_hint_only_when_no_visual_hits():
    """OCR present but no visual hits → source='ocr-hint'."""
    decision = resolve_visual_match(
        [], match_threshold=0.55, ocr_hint='BD-0077', conflict_threshold=0.96
    )
    assert decision.ship_id == 'BD-0077'
    assert decision.source == 'ocr-hint'


def test_resolve_visual_only_when_no_ocr():
    """No OCR hint, visual score above threshold → source='visual'."""
    hits = [{'id': 'a1', 'score': 0.82, 'payload': {'ship_id': 'BD-0077'}}]
    decision = resolve_visual_match(hits, match_threshold=0.55, conflict_threshold=0.96)
    assert decision.ship_id == 'BD-0077'
    assert decision.source == 'visual'


def test_resolve_default_conflict_threshold_is_096():
    """Default conflict_threshold=0.96: score=0.97 above threshold → visual wins."""
    hits = [{'id': 'a1', 'score': 0.97, 'payload': {'ship_id': 'SG-7082'}}]
    decision = resolve_visual_match(hits, match_threshold=0.55, ocr_hint='BD-0077')
    assert decision.source == 'conflict-visual-wins'
    assert decision.ship_id == 'SG-7082'
```

- [ ] **Step 1.2: Chạy tests — xác nhận fail**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core pytest app/tests/test_visual_ship_matching.py -v 2>&1 | tail -30
```

Expected: `test_resolve_consensus_when_ocr_and_visual_agree` FAIL, `test_resolve_conflict_*` FAIL, `test_resolve_ocr_hint_takes_priority` không còn (đã xóa).

- [ ] **Step 1.3: Cập nhật `resolve_visual_match`**

Thay toàn bộ nội dung `server/app/utils/ai/visual_ship_matching.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ShipMatchCandidate:
    ship_id: str
    aggregated_score: float
    hit_count: int
    point_ids: list[str]
    filenames: list[str]


def _ship_id_from_hit(hit: dict[str, Any]) -> str:
    payload = hit.get('payload') or {}
    return str(payload.get('ship_id') or payload.get('ship_code') or '').strip().upper()


def aggregate_visual_hits(
    hits: list[dict[str, Any]],
    *,
    top_m_for_mean: int = 3,
) -> list[ShipMatchCandidate]:
    """Group Qdrant hits by ship_id; score = mean of top-m point scores per ship."""
    if not hits:
        return []

    grouped: dict[str, list[tuple[float, str, str]]] = {}
    for hit in hits:
        ship_id = _ship_id_from_hit(hit)
        if not ship_id:
            continue
        score = float(hit.get('score') or 0.0)
        point_id = str(hit.get('id') or '')
        payload = hit.get('payload') or {}
        filename = str(payload.get('filename') or '')
        grouped.setdefault(ship_id, []).append((score, point_id, filename))

    ranked: list[ShipMatchCandidate] = []
    top_m = max(1, int(top_m_for_mean))
    for ship_id, entries in grouped.items():
        entries.sort(key=lambda item: item[0], reverse=True)
        top_scores = [score for score, _, _ in entries[:top_m]]
        aggregated = sum(top_scores) / len(top_scores)
        ranked.append(
            ShipMatchCandidate(
                ship_id=ship_id,
                aggregated_score=aggregated,
                hit_count=len(entries),
                point_ids=[point_id for _, point_id, _ in entries[:top_m]],
                filenames=[name for _, _, name in entries[:top_m] if name],
            )
        )

    ranked.sort(key=lambda item: item.aggregated_score, reverse=True)
    return ranked


@dataclass(frozen=True)
class VisualMatchDecision:
    accepted: bool
    ship_id: str | None
    confidence: float
    source: str
    best: ShipMatchCandidate | None
    ranked_ships: list[ShipMatchCandidate]
    margin: float


def resolve_visual_match(
    hits: list[dict[str, Any]],
    *,
    match_threshold: float,
    top_m_for_mean: int = 3,
    ocr_hint: str | None = None,
    conflict_threshold: float = 0.96,
) -> VisualMatchDecision:
    """Fuse OCR hint and visual Qdrant results using consensus logic.

    Decision matrix:
    - Both present, same ID              → source='consensus'         (conf boosted)
    - Both present, different, vis>=thr  → source='conflict-visual-wins'
    - Both present, different, vis<thr   → source='conflict-ocr-wins'
    - OCR only (no visual hits)          → source='ocr-hint'
    - Visual only (no OCR hint)          → source='visual' if score>=match_threshold
    - Neither                            → source='unknown'
    """
    ranked = aggregate_visual_hits(hits, top_m_for_mean=top_m_for_mean)
    normalized_ocr = ocr_hint.strip().upper() if ocr_hint else None

    # No visual hits at all
    if not ranked:
        return VisualMatchDecision(
            accepted=bool(normalized_ocr),
            ship_id=normalized_ocr,
            confidence=0.0,
            source='ocr-hint' if normalized_ocr else 'unknown',
            best=None,
            ranked_ships=[],
            margin=0.0,
        )

    best = ranked[0]
    second_score = ranked[1].aggregated_score if len(ranked) > 1 else 0.0
    margin = best.aggregated_score - second_score

    if normalized_ocr:
        if best.ship_id == normalized_ocr:
            # Both methods agree → consensus
            boosted = min(1.0, best.aggregated_score + 0.05)
            return VisualMatchDecision(
                accepted=True,
                ship_id=best.ship_id,
                confidence=boosted,
                source='consensus',
                best=best,
                ranked_ships=ranked,
                margin=margin,
            )
        # Methods disagree — use conflict_threshold to pick winner
        if best.aggregated_score >= float(conflict_threshold):
            return VisualMatchDecision(
                accepted=True,
                ship_id=best.ship_id,
                confidence=best.aggregated_score,
                source='conflict-visual-wins',
                best=best,
                ranked_ships=ranked,
                margin=margin,
            )
        return VisualMatchDecision(
            accepted=True,
            ship_id=normalized_ocr,
            confidence=best.aggregated_score,
            source='conflict-ocr-wins',
            best=best,
            ranked_ships=ranked,
            margin=margin,
        )

    # No OCR hint — pure visual path (unchanged)
    accepted = best.aggregated_score >= float(match_threshold)
    if accepted:
        return VisualMatchDecision(
            accepted=True,
            ship_id=best.ship_id,
            confidence=best.aggregated_score,
            source='visual',
            best=best,
            ranked_ships=ranked,
            margin=margin,
        )

    return VisualMatchDecision(
        accepted=False,
        ship_id=None,
        confidence=best.aggregated_score,
        source='unknown',
        best=best,
        ranked_ships=ranked,
        margin=margin,
    )
```

- [ ] **Step 1.4: Chạy tests — xác nhận pass**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core pytest app/tests/test_visual_ship_matching.py -v 2>&1 | tail -20
```

Expected: 8 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/utils/ai/visual_ship_matching.py server/app/tests/test_visual_ship_matching.py
git commit -m "feat(pipeline): consensus fusion logic in resolve_visual_match"
```

---

## Task 2: Cập nhật `IdentityFusion` — pass `conflict_threshold`

**Files:**
- Modify: `server/app/services/ai/identity_fusion.py`

`IdentityFusion.fuse()` hiện kiểm tra `decision.source == 'ocr-hint'` để assign `ship_id`. Với sources mới (`conflict-ocr-wins`, `conflict-visual-wins`, `consensus`), logic này cần được đơn giản hóa thành: assign `ship_id` whenever `decision.ship_id is not None`.

- [ ] **Step 2.1: Thay toàn bộ `identity_fusion.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from app.utils.ai.visual_ship_matching import resolve_visual_match


@dataclass(frozen=True)
class IdentityFusionResult:
    ship_id: str | None
    confidence: float
    source: str
    top_k: list[dict]


class IdentityFusion:
    def __init__(self, *, match_threshold: float, conflict_threshold: float = 0.96) -> None:
        self._match_threshold = float(match_threshold)
        self._conflict_threshold = float(conflict_threshold)

    def fuse(
        self,
        *,
        visual_top_k: list[dict],
        ocr_hint: str | None = None,
    ) -> IdentityFusionResult:
        decision = resolve_visual_match(
            visual_top_k,
            match_threshold=self._match_threshold,
            ocr_hint=ocr_hint,
            conflict_threshold=self._conflict_threshold,
        )
        ship_id = decision.ship_id if decision.ship_id else None
        return IdentityFusionResult(
            ship_id=ship_id,
            confidence=decision.confidence,
            source=decision.source,
            top_k=visual_top_k,
        )
```

- [ ] **Step 2.2: Chạy lại tests để xác nhận không bị break**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core pytest app/tests/test_visual_ship_matching.py -v 2>&1 | tail -10
```

Expected: 8 PASS (identity_fusion chưa có unit test riêng, covered qua integration).

- [ ] **Step 2.3: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/identity_fusion.py
git commit -m "feat(pipeline): pass conflict_threshold through IdentityFusion"
```

---

## Task 3: Config — `visual_conflict_threshold` trong DB + backend

**Files:**
- Modify: `server/app/db/schema_patches.py:621-650`
- Modify: `server/app/services/pipeline_service.py:450-453` và `185-187`

- [ ] **Step 3.1: Thêm vào `_DINOV2_PORT_CONFIG_VALUES`**

Trong `server/app/db/schema_patches.py`, tìm `_DINOV2_PORT_CONFIG_VALUES` (khoảng dòng 621). Thêm entry sau `'visual_match_threshold'`:

```python
_DINOV2_PORT_CONFIG_VALUES: dict[str, tuple[str, str]] = {
    'visual_match_threshold': (
        '0.55',
        'Minimum aggregated similarity to accept ship ID when OCR has no result.',
    ),
    'visual_conflict_threshold': (
        '0.96',
        'Minimum visual embedding score to override OCR when both methods disagree.',
    ),
    # ... rest unchanged
```

- [ ] **Step 3.2: Load từ `_load_runtime_cfg` trong `pipeline_service.py`**

Tìm block load `visual_match_threshold` (dòng ~450):

```python
'visual_match_threshold': self._to_float(
    cfg_map.get('visual_match_threshold', ''),
    float(settings.VISUAL_MATCH_THRESHOLD),
),
```

Thêm ngay sau đó:

```python
'visual_conflict_threshold': self._to_float(
    cfg_map.get('visual_conflict_threshold', ''), 0.96
),
```

- [ ] **Step 3.3: Pass to `IdentityFusion` trong `_init_visual_stack`**

Tìm dòng ~185:

```python
self._identity_fusion = IdentityFusion(
    match_threshold=runtime_cfg['visual_match_threshold'],
)
```

Thay bằng:

```python
self._identity_fusion = IdentityFusion(
    match_threshold=runtime_cfg['visual_match_threshold'],
    conflict_threshold=runtime_cfg['visual_conflict_threshold'],
)
```

- [ ] **Step 3.4: Kiểm tra server khởi động không lỗi**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "
from app.services.pipeline_service import PipelineService
print('import OK')
" 2>&1
```

Expected: `import OK` (không có exception).

- [ ] **Step 3.5: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/db/schema_patches.py server/app/services/pipeline_service.py
git commit -m "feat(config): add visual_conflict_threshold to port_configs"
```

---

## Task 4: Thêm `global_id` field vào `TrackedBoat`

**Files:**
- Modify: `server/app/services/ai/boat_tracker.py:59-103`

`TrackedBoat` là dataclass. Cần thêm `global_id` field và cập nhật `copy_public()` để copy field này.

- [ ] **Step 4.1: Thêm field `global_id` vào `TrackedBoat` dataclass**

Trong `server/app/services/ai/boat_tracker.py`, tìm `@dataclass` trước `class TrackedBoat` (dòng 59). Thêm `global_id` sau `last_known_ship_id` (dòng 76):

```python
@dataclass
class TrackedBoat:
    track_id: str
    state: TrackState
    box: np.ndarray
    conf: float
    hits: int
    misses: int
    first_seen_ts: float
    last_seen_ts: float
    ship_id: str | None = None
    camera_id: int | None = None
    velocity: tuple[float, float] | None = None
    embedding: np.ndarray | None = None
    motion_state: str | None = None
    static_since_ts: float | None = None
    dominant_color_hsv: tuple[int, int, int] | None = None
    last_known_ship_id: str | None = None
    global_id: str | None = None
    ever_confirmed: bool = False
    berth_in_ts: float | None = None
    berth_out_ts: float | None = None
```

- [ ] **Step 4.2: Thêm `global_id` vào `copy_public()`**

Trong cùng file, tìm method `copy_public` (dòng 81). Thêm `global_id=self.global_id,` vào constructor call:

```python
def copy_public(self) -> TrackedBoat:
    """Shallow copy with copied box array (safe for queue consumers)."""
    return TrackedBoat(
        track_id=self.track_id,
        state=self.state,
        box=self.box.copy(),
        conf=self.conf,
        hits=self.hits,
        misses=self.misses,
        first_seen_ts=self.first_seen_ts,
        last_seen_ts=self.last_seen_ts,
        ship_id=self.ship_id,
        camera_id=self.camera_id,
        velocity=self.velocity,
        embedding=self.embedding.copy() if self.embedding is not None else None,
        motion_state=self.motion_state,
        static_since_ts=self.static_since_ts,
        dominant_color_hsv=self.dominant_color_hsv,
        last_known_ship_id=self.last_known_ship_id,
        global_id=self.global_id,
        ever_confirmed=self.ever_confirmed,
        berth_in_ts=self.berth_in_ts,
        berth_out_ts=self.berth_out_ts,
    )
```

- [ ] **Step 4.3: Kiểm tra import không lỗi**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "
from app.services.ai.boat_tracker import TrackedBoat, TrackState
import numpy as np
t = TrackedBoat(track_id='trk_1', state=TrackState.CONFIRMED, box=np.zeros(4),
                conf=0.9, hits=1, misses=0, first_seen_ts=0.0, last_seen_ts=0.0)
assert t.global_id is None
cp = t.copy_public()
assert cp.global_id is None
t.global_id = 'gid_abc'
cp2 = t.copy_public()
assert cp2.global_id == 'gid_abc'
print('TrackedBoat.global_id OK')
" 2>&1
```

Expected: `TrackedBoat.global_id OK`

- [ ] **Step 4.4: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/boat_tracker.py
git commit -m "feat(tracker): add global_id field to TrackedBoat"
```

---

## Task 5: `get_global_id()` trong `CrossCameraReIdManager` + gán tại `_enrich_track`

**Files:**
- Modify: `server/app/services/ai/cross_camera_reid.py` (thêm method sau `get_global_ship_id` ~dòng 309)
- Modify: `server/app/services/ai/per_camera_pipeline.py:409-416`
- Test: `server/app/tests/test_cross_camera_reid.py`

- [ ] **Step 5.1: Xem cuối method `get_global_ship_id` để biết vị trí chèn**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
grep -n "def get_global_ship_id\|def resolve_lookup" server/app/services/ai/cross_camera_reid.py
```

Expected: dòng ~309 và ~319. Thêm `get_global_id` giữa hai methods này.

- [ ] **Step 5.2: Thêm `get_global_id` method vào `CrossCameraReIdManager`**

Trong `server/app/services/ai/cross_camera_reid.py`, tìm `def resolve_lookup_track_ids` (dòng ~319). Chèn ngay trước nó:

```python
    def get_global_id(self, camera_id: int, track_id: str) -> str | None:
        """Return the gid_* identifier for this (camera_id, track_id) pair, or None."""
        with self._lock:
            return self._track_to_global.get((int(camera_id), str(track_id)))
```

- [ ] **Step 5.3: Thêm test cho `get_global_id`**

Mở `server/app/tests/test_cross_camera_reid.py`. Thêm test ở cuối file:

```python
def test_get_global_id_returns_gid_after_track_report():
    """get_global_id returns the gid_* string after a track is reported."""
    from app.services.ai.cross_camera_reid import CrossCameraReIdManager
    import numpy as np
    from app.services.ai.boat_tracker import TrackedBoat, TrackState

    manager = CrossCameraReIdManager(
        visual_threshold=0.7,
        handoff_window_sec=5.0,
    )
    track = TrackedBoat(
        track_id='trk_001',
        state=TrackState.CONFIRMED,
        box=np.array([10.0, 10.0, 50.0, 50.0]),
        conf=0.9,
        hits=3,
        misses=0,
        first_seen_ts=0.0,
        last_seen_ts=1.0,
        camera_id=1,
    )
    embedding = np.random.rand(128).astype(np.float32)
    manager.report_track_update(1, track, embedding=embedding, frame_shape=(480, 640))

    gid = manager.get_global_id(1, 'trk_001')
    assert gid is not None
    assert gid.startswith('gid_')

    # Non-existent track returns None
    assert manager.get_global_id(1, 'trk_999') is None
    assert manager.get_global_id(99, 'trk_001') is None
```

- [ ] **Step 5.4: Chạy test**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core pytest app/tests/test_cross_camera_reid.py::test_get_global_id_returns_gid_after_track_report -v 2>&1 | tail -15
```

Expected: 1 PASS. Nếu `CrossCameraReIdManager.__init__` có signature khác, điều chỉnh params cho khớp (chạy `grep -n "def __init__" server/app/services/ai/cross_camera_reid.py` để xem).

- [ ] **Step 5.5: Gán `global_id` trong `_enrich_track`**

Trong `server/app/services/ai/per_camera_pipeline.py`, tìm block `_enrich_track` kết thúc (dòng ~409-416):

```python
        global_ship_id = self._reid_manager.get_global_ship_id(
            int(self.config.camera_id),
            str(track.track_id),
        )
        if global_ship_id:
            track.ship_id = global_ship_id
            track.last_known_ship_id = global_ship_id
            self._tracker.update_track_metadata(str(track.track_id), ship_id=global_ship_id)
```

Thêm ngay sau block đó (trước khi hàm kết thúc):

```python
        track.global_id = self._reid_manager.get_global_id(
            int(self.config.camera_id), str(track.track_id)
        )
```

- [ ] **Step 5.6: Kiểm tra import**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "
from app.services.ai.cross_camera_reid import CrossCameraReIdManager
from app.services.ai.per_camera_pipeline import PerCameraPipeline
print('import OK')
" 2>&1
```

Expected: `import OK`

- [ ] **Step 5.7: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/ai/cross_camera_reid.py \
        server/app/services/ai/per_camera_pipeline.py \
        server/app/tests/test_cross_camera_reid.py
git commit -m "feat(reid): add get_global_id() and populate TrackedBoat.global_id"
```

---

## Task 6: Viết lại overlay per-track (`overlay.py`)

**Files:**
- Modify: `server/app/utils/ai/overlay.py:96-217`

### Layout mới (6 dòng per track)

```
Above bbox:
  y-86: gid: {tb.global_id or tb.track_id}           purple  (200,160,255)
  y-62: trk: {tb.track_id} [{state}]                 gray    (180,180,180)
  y-38: det: {conf:.2f}                               cyan    (180,220,255)

Below bbox (requires ocr_cache entry):
  y+24: OCR: {text}                                   yellow  (0,220,255)
  y+44: EMB: {visual_ship_id} ({conf:.1f}%)           green   (120,255,120)
  y+64: Final: {tb.ship_id or 'N/A'} [{source}]      orange  (255,220,80)
```

`source` = `ent.get('visual_source', 'ocr')` từ ocr_cache. Nếu không có cache entry nhưng `tb.ship_id` có giá trị, hiển thị `Final: {tb.ship_id} [ocr]`.

- [ ] **Step 6.1: Thay hàm `draw_ship_detection_overlay` trong `overlay.py`**

Trong `server/app/utils/ai/overlay.py`, thay toàn bộ hàm `draw_ship_detection_overlay` (dòng 96–216):

```python
def draw_ship_detection_overlay(
    display_frame,
    tracked_boats: list[TrackedBoat],
    ocr_cache: dict | None,
    ocr_lock,
    ocr_label_ttl: float,
    fps: float,
    resize_scale: float,
    *,
    frame_captured_mono: float | None = None,
    camera_id: int | None = None,
):
    """
    Vẽ 3 dòng trên bbox: gid / trk+state / det conf.
    Vẽ 3 dòng dưới bbox: OCR / EMB / Final (từ ocr_cache).
    """
    now = time.time()

    for tb in tracked_boats:
        b = tb.box
        x1 = int(b[0])
        y1 = int(b[1])

        # Line 1 (top): actual global_id
        gid_label = f"gid: {tb.global_id or tb.track_id}"
        cv2.putText(
            display_frame,
            gid_label,
            (x1, y1 - 86),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (200, 160, 255),
            2,
        )

        # Line 2: local track_id + state
        trk_label = f"trk: {tb.track_id} [{tb.state.value}]"
        cv2.putText(
            display_frame,
            trk_label,
            (x1, y1 - 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 180, 180),
            2,
        )

        # Line 3: detection confidence
        cv2.putText(
            display_frame,
            f"det: {tb.conf:.2f}",
            (x1, y1 - 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 220, 255),
            2,
        )

    if ocr_cache is not None and ocr_lock is not None:
        with ocr_lock:
            for k in list(ocr_cache.keys()):
                if now - ocr_cache[k]['time'] >= ocr_label_ttl:
                    del ocr_cache[k]
            for tb in tracked_boats:
                ck = ocr_cache_key_track(tb.track_id, tb.camera_id)
                ent = ocr_cache.get(ck)
                b = tb.box
                y_base = min(int(b[3]) + 24, display_frame.shape[0] - 6)

                if ent:
                    ocr_text = str(ent.get('text') or '').strip()
                    if ocr_text:
                        cv2.putText(
                            display_frame,
                            f"OCR: {ocr_text}",
                            (int(b[0]), y_base),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.55,
                            (0, 220, 255),
                            2,
                        )
                    y_base = min(y_base + 20, display_frame.shape[0] - 6)

                    visual_ship_id = str(ent.get('visual_ship_id') or '').strip()
                    visual_conf = float(ent.get('visual_confidence') or 0.0)
                    if visual_ship_id:
                        conf_pct = max(0.0, min(1.0, visual_conf)) * 100.0
                        cv2.putText(
                            display_frame,
                            f"EMB: {visual_ship_id} ({conf_pct:.1f}%)",
                            (int(b[0]), y_base),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.52,
                            (120, 255, 120),
                            2,
                        )
                    y_base = min(y_base + 20, display_frame.shape[0] - 6)

                    source = str(ent.get('visual_source') or 'ocr').strip()
                    final_id = str(tb.ship_id or 'N/A')
                    cv2.putText(
                        display_frame,
                        f"Final: {final_id} [{source}]",
                        (int(b[0]), y_base),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.52,
                        (255, 220, 80),
                        2,
                    )
                elif tb.ship_id:
                    # OCR voted but no visual cache entry yet — show Final from OCR
                    cv2.putText(
                        display_frame,
                        f"Final: {tb.ship_id} [ocr]",
                        (int(b[0]), y_base),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.52,
                        (255, 220, 80),
                        2,
                    )

    if frame_captured_mono is not None:
        sync_label = format_capture_wall_clock(frame_captured_mono, camera_id=camera_id)
        cv2.putText(
            display_frame,
            sync_label,
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (80, 220, 255),
            2,
        )

    cv2.putText(
        display_frame,
        f"FPS: {fps:.1f}",
        (10, 58 if frame_captured_mono is not None else 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2,
    )

    n_conf = sum(1 for t in tracked_boats if t.state == TrackState.CONFIRMED)
    cv2.putText(
        display_frame,
        f"confirmed: {n_conf}",
        (10, 88 if frame_captured_mono is not None else 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (200, 255, 200),
        2,
    )

    if resize_scale != 1.0:
        hh, ww = display_frame.shape[:2]
        display_frame = cv2.resize(
            display_frame,
            (int(ww * resize_scale), int(hh * resize_scale)),
        )

    return display_frame
```

- [ ] **Step 6.2: Kiểm tra import**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "
from app.utils.ai.overlay import draw_ship_detection_overlay
print('overlay import OK')
" 2>&1
```

Expected: `overlay import OK`

- [ ] **Step 6.3: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/utils/ai/overlay.py
git commit -m "feat(overlay): show gid/trk/det/OCR/EMB/Final per-track"
```

---

## Task 7: Cập nhật fused overlay (`fused_track_overlay.py`)

**Files:**
- Modify: `server/app/utils/ai/fused_track_overlay.py:86-97`

Fused overlay hiện chỉ vẽ `ship_id or T{track_id}`. Cần thêm dòng `gid:` bên trên.

- [ ] **Step 7.1: Thay block vẽ label trong `draw_fused_track_overlay`**

Trong `server/app/utils/ai/fused_track_overlay.py`, tìm block (dòng 86–97):

```python
            color = _color_for_track(track)
            cv2.rectangle(fused, (x1, y1), (x2, y2), color, 2)
            label = track.ship_id or f'T{track.track_id}'
            cv2.putText(
                fused,
                label,
                (x1, max(12, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                2,
            )
```

Thay bằng:

```python
            color = _color_for_track(track)
            cv2.rectangle(fused, (x1, y1), (x2, y2), color, 2)
            # gid line (actual global identity)
            gid_text = f"gid: {track.global_id or track.track_id}"
            cv2.putText(
                fused,
                gid_text,
                (x1, max(12, y1 - 22)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (200, 160, 255),
                1,
            )
            # ship_id / plate line
            plate_text = track.ship_id or f'T{track.track_id}'
            cv2.putText(
                fused,
                plate_text,
                (x1, max(12, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                2,
            )
```

- [ ] **Step 7.2: Kiểm tra import**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "
from app.utils.ai.fused_track_overlay import draw_fused_track_overlay
print('fused overlay import OK')
" 2>&1
```

Expected: `fused overlay import OK`

- [ ] **Step 7.3: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/utils/ai/fused_track_overlay.py
git commit -m "feat(overlay): add global_id line to fused track overlay"
```

---

## Task 8: Frontend config key mapping

**Files:**
- Modify: `client/src/features/port/components/PortConfigsSection.tsx:64-130`

Chỉ cần thêm 1 dòng vào `KEY_PREFIX_MAP`. UI tự render field trong category "Visual ID".

- [ ] **Step 8.1: Thêm key vào `KEY_PREFIX_MAP`**

Trong `client/src/features/port/components/PortConfigsSection.tsx`, tìm block:

```ts
  visual_match_threshold: 'visual',
```

Thêm ngay sau:

```ts
  visual_conflict_threshold: 'visual',
```

- [ ] **Step 8.2: Build frontend để check TypeScript errors**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/client
npm run build 2>&1 | tail -20
```

Expected: build thành công, không có TypeScript errors.

- [ ] **Step 8.3: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add client/src/features/port/components/PortConfigsSection.tsx
git commit -m "feat(config): add visual_conflict_threshold to Visual ID config category"
```

---

## Task 9: Chạy full test suite

- [ ] **Step 9.1: Chạy tất cả server tests**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core pytest app/tests/ -v 2>&1 | tail -30
```

Expected: tất cả tests PASS. Nếu có test nào fail do thay đổi `source` string, cập nhật assertion cho phù hợp với sources mới (`consensus`, `conflict-ocr-wins`, `conflict-visual-wins`).

- [ ] **Step 9.2: Kiểm tra schema patch chạy được**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "
from app.db.schema_patches import _DINOV2_PORT_CONFIG_VALUES
assert 'visual_conflict_threshold' in _DINOV2_PORT_CONFIG_VALUES
val, desc = _DINOV2_PORT_CONFIG_VALUES['visual_conflict_threshold']
assert val == '0.96'
print('schema patch config OK:', desc)
" 2>&1
```

Expected: `schema patch config OK: Minimum visual embedding score to override OCR when both methods disagree.`

- [ ] **Step 9.3: Final commit nếu cần**

Nếu Task 9.1 có fixes bổ sung:

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add -A
git commit -m "fix(tests): update assertions for new consensus/conflict source strings"
```

---

## Checklist xác nhận hoàn thành

- [ ] `resolve_visual_match` có 6 source cases và `conflict_threshold` param
- [ ] `IdentityFusion` nhận và truyền `conflict_threshold`
- [ ] `visual_conflict_threshold = 0.96` có trong `_DINOV2_PORT_CONFIG_VALUES`
- [ ] `pipeline_service.py` load và pass `visual_conflict_threshold` tới `IdentityFusion`
- [ ] `TrackedBoat.global_id` field tồn tại và được copy trong `copy_public()`
- [ ] `CrossCameraReIdManager.get_global_id()` hoạt động
- [ ] `_enrich_track` gán `track.global_id`
- [ ] Overlay hiển thị `gid:` / `trk:` / `det:` / `OCR:` / `EMB:` / `Final:` đúng
- [ ] Fused overlay có dòng `gid:`
- [ ] `PortConfigsSection.tsx` có `visual_conflict_threshold: 'visual'`
- [ ] Tất cả tests PASS

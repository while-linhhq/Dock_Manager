# Ship ID Evidence Pools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split OCR and embedding evidence pools, but use only existing runtime config thresholds for final `ship_id` decisions.

**Architecture:** `ship_id_evidence.py` resolves OCR/embedding pool winners from existing config. `BoatTracker` stores per-track evidence and receives thresholds from pipeline runtime config. `PerCameraPipeline` routes visual top hit into embedding evidence, not OCR evidence.

**Tech Stack:** Python, dataclasses, pytest, existing FastAPI/AI services.

---

## Files

- `server/app/services/ai/ship_id_evidence.py`: evidence pools and config-driven resolver.
- `server/app/services/ai/boat_tracker.py`: per-track evidence storage and lock decision integration.
- `server/app/services/ai/per_camera_pipeline.py`: visual result wiring into embedding pool.
- `server/app/services/pipeline_service.py`: pass existing `port_configs` thresholds into trackers.
- `server/app/tests/test_ship_id_evidence.py`: resolver tests.
- `server/app/tests/test_ship_id_lock.py`: tracker/lock integration tests.

---

### Task 1: Resolver Tests

- [x] Write `test_ship_id_evidence.py` for config-driven decisions:
  - OCR uses `detection_confidence_threshold`.
  - Embedding uses `visual_no_ocr_match_threshold` without OCR.
  - Consensus when OCR and embedding agree.
  - Single wrong OCR loses to valid embedding.
  - Repeated OCR beats conflicting embedding below `visual_conflict_threshold`.
  - Embedding above `visual_conflict_threshold` beats conflicting OCR.

- [x] Run RED:

```bash
pytest server/app/tests/test_ship_id_evidence.py -q
```

Expected before implementation: import/signature failure.

### Task 2: Resolver Implementation

- [x] Implement `ShipIdEvidenceConfig` with existing threshold names:

```python
ShipIdEvidenceConfig(
    ocr_confidence_threshold=float(...),
    visual_match_threshold=float(...),
    visual_no_ocr_match_threshold=float(...),
    visual_conflict_threshold=float(...),
)
```

- [x] Remove new constants. Resolver receives config via `resolve(config)`.

- [x] Run:

```bash
pytest server/app/tests/test_ship_id_evidence.py -q
```

Expected: pass.

### Task 3: Tracker Integration

- [x] Extend `BoatTracker.__init__()` with existing threshold params and defaults.
- [x] Store `ShipIdEvidenceConfig` inside tracker.
- [x] Resolve evidence using `evidence.resolve(self._ship_id_evidence_config)`.
- [x] Add `add_embedding_vote()`.
- [x] Lock only resolved final decisions.

- [x] Run:

```bash
pytest server/app/tests/test_ship_id_lock.py -q
```

Expected: pass.

### Task 4: Runtime Config Wiring

- [x] Load `detection_confidence_threshold` from `port_configs` in `PipelineService._load_runtime_config()`.
- [x] Pass existing thresholds through `_tracker_kwargs()`.
- [x] Pass thresholds into per-camera `BoatTracker` via `PerCameraPipelineConfig`.
- [x] Keep existing `visual_match_threshold`, `visual_no_ocr_match_threshold`, and `visual_conflict_threshold` behavior.

### Task 5: Visual Wiring

- [x] In `_on_visual_result()`, add embedding top hit via `self._tracker.add_embedding_vote(...)`.
- [x] Remove visual-as-OCR reporting through `report_ocr_result()`.
- [x] Preserve `ocr-hint` metadata fallback only.

### Task 6: Verification

- [x] Run focused suite:

```bash
pytest server/app/tests/test_ship_id_lock.py server/app/tests/test_ship_id_evidence.py server/app/tests/test_zone_gated_vote.py -q
```

Expected: all pass.

---

### Task 7: Wire `detection_confidence_threshold` into OCR validity gate

**Gap found:** `ShipIdEvidenceConfig` has no `ocr_confidence_threshold` field. `_ocr_is_valid` accepts any non-None stats regardless of total confidence. The spec requires minimum OCR pool total confidence to accept OCR winner.

**Files:**
- Modify: `server/app/services/ai/ship_id_evidence.py`
- Modify: `server/app/services/ai/boat_tracker.py`
- Modify: `server/app/services/ai/per_camera_pipeline.py`
- Modify: `server/app/services/pipeline_service.py`
- Modify: `server/app/tests/test_ship_id_evidence.py`

- [ ] **Step 1: Add failing test for OCR confidence threshold**

Add to `server/app/tests/test_ship_id_evidence.py`:

```python
def test_ocr_below_confidence_threshold_is_not_valid():
    cfg = ShipIdEvidenceConfig(
        ocr_confidence_threshold=0.6,
        visual_match_threshold=0.55,
        visual_no_ocr_match_threshold=0.55,
        visual_conflict_threshold=0.96,
    )
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-0001', 0.50, now=1.0)  # total=0.50 < 0.6

    decision = evidence.resolve(cfg)

    assert decision.state == 'none'
    assert decision.ship_id is None


def test_ocr_meets_confidence_threshold_is_valid():
    cfg = ShipIdEvidenceConfig(
        ocr_confidence_threshold=0.6,
        visual_match_threshold=0.55,
        visual_no_ocr_match_threshold=0.55,
        visual_conflict_threshold=0.96,
    )
    evidence = ShipIdEvidence()
    evidence.add_ocr('BD-0001', 0.70, now=1.0)  # total=0.70 >= 0.6

    decision = evidence.resolve(cfg)

    assert decision.state == 'final'
    assert decision.ship_id == 'BD-0001'
    assert decision.source == 'ocr'
```

- [ ] **Step 2: Run to confirm RED**

```bash
pytest server/app/tests/test_ship_id_evidence.py::test_ocr_below_confidence_threshold_is_not_valid server/app/tests/test_ship_id_evidence.py::test_ocr_meets_confidence_threshold_is_valid -v
```

Expected: FAIL — `ShipIdEvidenceConfig` has no `ocr_confidence_threshold`.

- [ ] **Step 3: Add `ocr_confidence_threshold` to `ShipIdEvidenceConfig` and update `_ocr_is_valid`**

In `server/app/services/ai/ship_id_evidence.py`:

```python
@dataclass(frozen=True)
class ShipIdEvidenceConfig:
    ocr_confidence_threshold: float
    visual_match_threshold: float
    visual_no_ocr_match_threshold: float
    visual_conflict_threshold: float
```

Change `_ocr_is_valid` signature and logic:

```python
def _ocr_is_valid(stats: EvidenceStats | None, *, config: ShipIdEvidenceConfig) -> bool:
    if stats is None:
        return False
    return stats.total_score >= float(config.ocr_confidence_threshold)
```

Update `ShipIdEvidence.resolve` to pass `config` to `_ocr_is_valid`:

```python
ocr_valid = _ocr_is_valid(ocr, config=config)
```

- [ ] **Step 4: Fix existing `CFG` in test file to include `ocr_confidence_threshold`**

In `server/app/tests/test_ship_id_evidence.py`, update the top-level `CFG`:

```python
CFG = ShipIdEvidenceConfig(
    ocr_confidence_threshold=0.0,
    visual_match_threshold=0.55,
    visual_no_ocr_match_threshold=0.55,
    visual_conflict_threshold=0.96,
)
```

Setting `ocr_confidence_threshold=0.0` keeps all existing tests passing (any positive total clears it).

- [ ] **Step 5: Run evidence tests GREEN**

```bash
pytest server/app/tests/test_ship_id_evidence.py -v
```

Expected: all pass.

- [ ] **Step 6: Add `ocr_confidence_threshold` param to `BoatTracker.__init__`**

In `server/app/services/ai/boat_tracker.py`, add parameter (default `0.0` for backward compat) and wire into config:

```python
def __init__(
    self,
    ...
    visual_match_threshold: float = 0.55,
    visual_no_ocr_match_threshold: float = 0.55,
    visual_conflict_threshold: float = 0.96,
    ocr_confidence_threshold: float = 0.0,
):
    ...
    self._ship_id_evidence_config = ShipIdEvidenceConfig(
        ocr_confidence_threshold=float(ocr_confidence_threshold),
        visual_match_threshold=float(visual_match_threshold),
        visual_no_ocr_match_threshold=float(visual_no_ocr_match_threshold),
        visual_conflict_threshold=float(visual_conflict_threshold),
    )
```

- [ ] **Step 7: Add `ocr_confidence_threshold` to `PerCameraPipelineConfig` and thread through**

In `server/app/services/ai/per_camera_pipeline.py`, add field:

```python
@dataclass(frozen=True)
class PerCameraPipelineConfig:
    ...
    ocr_confidence_threshold: float = 0.0
```

Pass to `BoatTracker` constructor in `__init__`:

```python
self._tracker = BoatTracker(
    ...
    visual_match_threshold=config.visual_match_threshold,
    visual_no_ocr_match_threshold=config.visual_no_ocr_match_threshold,
    visual_conflict_threshold=config.visual_conflict_threshold,
    ocr_confidence_threshold=config.ocr_confidence_threshold,
)
```

- [ ] **Step 8: Load `detection_confidence_threshold` in `pipeline_service.py` `_load_runtime_config`**

In `server/app/services/pipeline_service.py`, add to the `runtime_cfg` dict (near the other OCR thresholds):

```python
'ocr_confidence_threshold': self._to_float(
    cfg_map.get('detection_confidence_threshold', ''),
    0.0,
),
```

Pass it through `PerCameraPipelineConfig` construction:

```python
pipeline_config = PerCameraPipelineConfig(
    ...
    visual_match_threshold=runtime_cfg['visual_match_threshold'],
    visual_no_ocr_match_threshold=runtime_cfg['visual_no_ocr_match_threshold'],
    visual_conflict_threshold=runtime_cfg['visual_conflict_threshold'],
    ocr_confidence_threshold=runtime_cfg['ocr_confidence_threshold'],
)
```

- [ ] **Step 9: Run full suite GREEN**

```bash
pytest server/app/tests/test_ship_id_lock.py server/app/tests/test_ship_id_evidence.py server/app/tests/test_zone_gated_vote.py -q
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add server/app/services/ai/ship_id_evidence.py \
        server/app/services/ai/boat_tracker.py \
        server/app/services/ai/per_camera_pipeline.py \
        server/app/services/pipeline_service.py \
        server/app/tests/test_ship_id_evidence.py
git commit -m "feat(ship-id): wire detection_confidence_threshold as OCR pool total confidence gate"
```

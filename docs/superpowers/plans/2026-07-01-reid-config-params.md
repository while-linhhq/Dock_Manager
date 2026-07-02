# Re-ID Config Params (Phần 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seed the 7 new `reid_*` overlap-merge config keys into the database (init + runtime patch), expose them as typed settings, load them in the pipeline runtime config, and surface them in the port-config UI — so that the Phần 2 (overlap merge) and Phần 4 (edge cases) plans have their parameters available.

**Architecture:** Config flows: `core/config.py` (env defaults) → `db/init_db.py` + `db/schema_patches.py` (DB seed) → `pipeline_service._load_runtime_config()` (read into `runtime_cfg`) → consumer components (added in later plans). The UI reads keys from `port_configs` and categorizes them via `PortConfigsSection.tsx` maps. This plan only adds the params and their plumbing — no behavior change yet (no consumer reads them until Phần 2).

**Tech Stack:** Python, pydantic-settings, SQLAlchemy, PostgreSQL/SQLite, React + TypeScript.

---

## New params (from spec Phần 3)

| Key | Default | Role |
|---|---|---|
| `reid_overlap_merge_enabled` | `true` | Enable concurrent overlap merge (Phần 2) |
| `reid_edge_zone_ratio` | `0.15` | Overlap-zone width (fraction of frame width) for merge — separate from `edge_zone_ratio` |
| `reid_embedding_weight` | `0.6` | Embedding weight in fusion score |
| `reid_color_weight` | `0.25` | HSV similarity weight in fusion score |
| `reid_size_weight` | `0.15` | Box-size-ratio weight in fusion score |
| `reid_accept_threshold` | `0.6` | Total soft-score threshold to accept a merge |
| `reid_min_margin` | `0.12` | Required score gap vs candidate #2 (anti A1 mismatch) |

---

## Files

- Modify: `server/app/core/config.py` — add 7 typed settings (after the existing `reid_*` block at lines 34–40).
- Modify: `server/app/db/init_db.py` — add 7 seed rows to the `port_configs` seed SQL (after line 126, the seam/anchor block).
- Modify: `server/app/db/schema_patches.py` — add `_ensure_reid_overlap_merge_port_configs()` and register it in `apply_schema_patches()`.
- Modify: `server/app/services/pipeline_service.py` — load the 7 keys into `runtime_cfg` in `_load_runtime_config()`.
- Modify: `client/src/features/port/components/PortConfigsSection.tsx` — add `KEY_PREFIX_MAP` + `KEY_VI_DESCRIPTION` entries.
- Test: `server/app/tests/test_reid_config_params.py` — verify defaults and runtime-config loading.

---

### Task 1: Add typed settings to `core/config.py`

**Files:**
- Modify: `server/app/core/config.py:34-40` (after the existing `reid_*`/`PRIMARY_ZONE_RATIO`/`EDGE_ZONE_RATIO` block)

- [ ] **Step 1: Add the 7 settings**

Locate the existing block (lines 34–40):

```python
    TRACK_REID_WINDOW_SEC: float = 120.0
    TRACK_REID_MAX_DIST: float = 150.0
    REID_EMBEDDING_MODEL_PATH: str = ""
    REID_VISUAL_THRESHOLD: float = 0.6
    REID_HANDOFF_WINDOW_SEC: float = 30.0
    PRIMARY_ZONE_RATIO: float = 0.8
    EDGE_ZONE_RATIO: float = 0.1
```

Insert immediately after `EDGE_ZONE_RATIO: float = 0.1`:

```python
    # Concurrent overlap merge (cross-camera Re-ID Phần 2)
    REID_OVERLAP_MERGE_ENABLED: bool = True
    REID_EDGE_ZONE_RATIO: float = 0.15
    REID_EMBEDDING_WEIGHT: float = 0.6
    REID_COLOR_WEIGHT: float = 0.25
    REID_SIZE_WEIGHT: float = 0.15
    REID_ACCEPT_THRESHOLD: float = 0.6
    REID_MIN_MARGIN: float = 0.12
```

- [ ] **Step 2: Verify import works**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "from app.core.config import settings; print(settings.REID_ACCEPT_THRESHOLD, settings.REID_OVERLAP_MERGE_ENABLED)"
```

Expected: `0.6 True`

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/core/config.py
git commit -m "feat(reid): add overlap-merge settings to core config"
```

---

### Task 2: Seed keys in `init_db.py`

**Files:**
- Modify: `server/app/db/init_db.py:126` (after the `anchor_color_hsv_tolerance_h` seed row)

- [ ] **Step 1: Add 7 seed rows**

Locate this line (~126):

```python
        ('anchor_color_hsv_tolerance_h',   '15',         'Dung sai Hue (độ) khi so màu re-validate anchor'),
```

Insert immediately after it (before the `sepay_*` rows):

```python
        ('reid_overlap_merge_enabled',     'true',       'Bật merge khi tàu thấy đồng thời trên 2 camera kề (overlap FOV)'),
        ('reid_edge_zone_ratio',           '0.15',       'Bề rộng vùng overlap (tỉ lệ width) để xét merge cross-camera'),
        ('reid_embedding_weight',          '0.6',        'Trọng số embedding trong fusion score merge'),
        ('reid_color_weight',              '0.25',       'Trọng số HSV similarity trong fusion score merge'),
        ('reid_size_weight',               '0.15',       'Trọng số tỉ lệ kích thước box trong fusion score merge'),
        ('reid_accept_threshold',          '0.6',        'Ngưỡng tổng score mềm để chấp nhận merge'),
        ('reid_min_margin',                '0.12',       'Chênh score tối thiểu so với candidate #2 (chống nhầm)'),
```

- [ ] **Step 2: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/db/init_db.py
git commit -m "feat(reid): seed overlap-merge port_configs in init_db"
```

---

### Task 3: Add runtime schema patch for existing databases

**Files:**
- Modify: `server/app/db/schema_patches.py` (add function after `_ensure_visual_stack_port_configs`, register at line ~1931)

- [ ] **Step 1: Add `_ensure_reid_overlap_merge_port_configs()`**

Add this function immediately after the end of `_ensure_visual_stack_port_configs()` (find its closing — it ends with the `try/except` block that runs the INSERT loop, mirror that exact shape):

```python
def _ensure_reid_overlap_merge_port_configs() -> None:
    try:
        inspector = inspect(engine)
        if not inspector.has_table('port_configs'):
            return
    except Exception as err:
        logger.warning('schema_patches: could not inspect port_configs: %s', err)
        return

    defaults = {
        'reid_overlap_merge_enabled': (
            'true',
            'Bật merge khi tàu thấy đồng thời trên 2 camera kề (overlap FOV).',
        ),
        'reid_edge_zone_ratio': (
            '0.15',
            'Bề rộng vùng overlap (tỉ lệ width) để xét merge cross-camera.',
        ),
        'reid_embedding_weight': (
            '0.6',
            'Trọng số embedding trong fusion score merge.',
        ),
        'reid_color_weight': (
            '0.25',
            'Trọng số HSV similarity trong fusion score merge.',
        ),
        'reid_size_weight': (
            '0.15',
            'Trọng số tỉ lệ kích thước box trong fusion score merge.',
        ),
        'reid_accept_threshold': (
            '0.6',
            'Ngưỡng tổng score mềm để chấp nhận merge.',
        ),
        'reid_min_margin': (
            '0.12',
            'Chênh score tối thiểu so với candidate #2 (chống nhầm).',
        ),
    }

    dialect = engine.dialect.name
    if dialect == 'postgresql':
        stmt = text(
            """
            INSERT INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            ON CONFLICT (key) DO NOTHING
            """
        )
    elif dialect == 'sqlite':
        stmt = text(
            """
            INSERT OR IGNORE INTO port_configs (key, value, description)
            VALUES (:key, :value, :description)
            """
        )
    else:
        logger.warning(
            'schema_patches: unknown dialect %s — seed reid overlap merge port_configs manually',
            dialect,
        )
        return

    try:
        with engine.begin() as conn:
            for key, (default_value, description) in defaults.items():
                conn.execute(
                    stmt,
                    {'key': key, 'value': default_value, 'description': description},
                )
        _patch_done('ensured reid overlap merge port_configs keys')
    except Exception as err:
        logger.error('schema_patches: failed to seed reid overlap merge port_configs: %s', err)
        raise
```

- [ ] **Step 2: Register in `apply_schema_patches()`**

Locate (line ~1931):

```python
    _ensure_visual_stack_port_configs()
    _migrate_visual_stack_dinov2_port_configs()
```

Insert between them:

```python
    _ensure_visual_stack_port_configs()
    _ensure_reid_overlap_merge_port_configs()
    _migrate_visual_stack_dinov2_port_configs()
```

- [ ] **Step 3: Verify patch runs without error**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -c "from app.db.schema_patches import _ensure_reid_overlap_merge_port_configs; _ensure_reid_overlap_merge_port_configs(); print('OK')"
```

Expected: `OK` (and on a live DB, the keys are inserted; re-running is idempotent).

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/db/schema_patches.py
git commit -m "feat(reid): runtime schema patch seeds overlap-merge port_configs"
```

---

### Task 4: Load keys into pipeline runtime config (TDD)

**Files:**
- Create: `server/app/tests/test_reid_config_params.py`
- Modify: `server/app/services/pipeline_service.py:357-360` (after the `edge_zone_ratio` entry in `_load_runtime_config`)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for Re-ID overlap-merge runtime config loading (Phần 3)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.pipeline_service import PipelineService


def _cfg_row(key: str, value: str):
    row = MagicMock()
    row.key = key
    row.value = value
    return row


def test_runtime_config_loads_overlap_merge_defaults():
    """When port_configs has no reid_* overlap keys, runtime_cfg uses settings defaults."""
    svc = PipelineService()
    with (
        patch('app.services.pipeline_service.SessionLocal') as mock_session,
        patch('app.services.pipeline_service.port_config_repo') as mock_repo,
    ):
        mock_repo.get_all.return_value = []
        mock_session.return_value = MagicMock()
        cfg = svc._load_runtime_config()

    assert cfg['reid_overlap_merge_enabled'] is True
    assert cfg['reid_edge_zone_ratio'] == 0.15
    assert cfg['reid_embedding_weight'] == 0.6
    assert cfg['reid_color_weight'] == 0.25
    assert cfg['reid_size_weight'] == 0.15
    assert cfg['reid_accept_threshold'] == 0.6
    assert cfg['reid_min_margin'] == 0.12


def test_runtime_config_reads_overlap_merge_overrides():
    """port_configs values override settings defaults."""
    svc = PipelineService()
    rows = [
        _cfg_row('reid_overlap_merge_enabled', 'false'),
        _cfg_row('reid_edge_zone_ratio', '0.2'),
        _cfg_row('reid_embedding_weight', '0.5'),
        _cfg_row('reid_color_weight', '0.3'),
        _cfg_row('reid_size_weight', '0.2'),
        _cfg_row('reid_accept_threshold', '0.7'),
        _cfg_row('reid_min_margin', '0.1'),
    ]
    with (
        patch('app.services.pipeline_service.SessionLocal') as mock_session,
        patch('app.services.pipeline_service.port_config_repo') as mock_repo,
    ):
        mock_repo.get_all.return_value = rows
        mock_session.return_value = MagicMock()
        cfg = svc._load_runtime_config()

    assert cfg['reid_overlap_merge_enabled'] is False
    assert cfg['reid_edge_zone_ratio'] == 0.2
    assert cfg['reid_embedding_weight'] == 0.5
    assert cfg['reid_color_weight'] == 0.3
    assert cfg['reid_size_weight'] == 0.2
    assert cfg['reid_accept_threshold'] == 0.7
    assert cfg['reid_min_margin'] == 0.1
```

- [ ] **Step 2: Run RED**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_reid_config_params.py -v 2>&1 | head -30
```

Expected: FAIL with `KeyError: 'reid_overlap_merge_enabled'`.

- [ ] **Step 3: Add the keys to `_load_runtime_config`**

In `server/app/services/pipeline_service.py`, locate the `edge_zone_ratio` entry in the returned dict (lines 357–360):

```python
            'edge_zone_ratio': self._to_float(
                cfg_map.get('edge_zone_ratio', ''),
                float(settings.EDGE_ZONE_RATIO),
            ),
```

Insert immediately after it:

```python
            'reid_overlap_merge_enabled': self._to_bool(
                cfg_map.get('reid_overlap_merge_enabled', ''),
                bool(settings.REID_OVERLAP_MERGE_ENABLED),
            ),
            'reid_edge_zone_ratio': self._to_float(
                cfg_map.get('reid_edge_zone_ratio', ''),
                float(settings.REID_EDGE_ZONE_RATIO),
            ),
            'reid_embedding_weight': self._to_float(
                cfg_map.get('reid_embedding_weight', ''),
                float(settings.REID_EMBEDDING_WEIGHT),
            ),
            'reid_color_weight': self._to_float(
                cfg_map.get('reid_color_weight', ''),
                float(settings.REID_COLOR_WEIGHT),
            ),
            'reid_size_weight': self._to_float(
                cfg_map.get('reid_size_weight', ''),
                float(settings.REID_SIZE_WEIGHT),
            ),
            'reid_accept_threshold': self._to_float(
                cfg_map.get('reid_accept_threshold', ''),
                float(settings.REID_ACCEPT_THRESHOLD),
            ),
            'reid_min_margin': self._to_float(
                cfg_map.get('reid_min_margin', ''),
                float(settings.REID_MIN_MARGIN),
            ),
```

- [ ] **Step 4: Run GREEN**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
conda run -n demo_core python -m pytest app/tests/test_reid_config_params.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add server/app/services/pipeline_service.py server/app/tests/test_reid_config_params.py
git commit -m "feat(reid): load overlap-merge params into pipeline runtime config"
```

---

### Task 5: Surface params in the port-config UI

**Files:**
- Modify: `client/src/features/port/components/PortConfigsSection.tsx` (`KEY_PREFIX_MAP` ~line 100–139, `KEY_VI_DESCRIPTION` ~line 150–245)

- [ ] **Step 1: Add to `KEY_PREFIX_MAP`**

Find the existing `reid_*` entries in `KEY_PREFIX_MAP` (e.g. `reid_visual_threshold: 'reid'`). Add these alongside them:

```ts
  reid_overlap_merge_enabled: 'reid',
  reid_edge_zone_ratio: 'reid',
  reid_embedding_weight: 'reid',
  reid_color_weight: 'reid',
  reid_size_weight: 'reid',
  reid_accept_threshold: 'reid',
  reid_min_margin: 'reid',
```

- [ ] **Step 2: Add to `KEY_VI_DESCRIPTION`**

Find the existing `reid_handoff_window_sec` description entry. Add these alongside the other `reid_*` descriptions:

```ts
  reid_overlap_merge_enabled: 'Bật merge khi tàu thấy đồng thời trên 2 camera kề (overlap FOV).',
  reid_edge_zone_ratio: 'Bề rộng vùng overlap (tỉ lệ width) để xét merge cross-camera.',
  reid_embedding_weight: 'Trọng số embedding trong fusion score merge.',
  reid_color_weight: 'Trọng số HSV similarity trong fusion score merge.',
  reid_size_weight: 'Trọng số tỉ lệ kích thước box trong fusion score merge.',
  reid_accept_threshold: 'Ngưỡng tổng score mềm để chấp nhận merge.',
  reid_min_margin: 'Chênh score tối thiểu so với candidate #2 (chống nhầm).',
```

- [ ] **Step 3: Type-check the client build**

```bash
cd /home/ubuntu-linh/Documents/dock-manager/client
npm run build
```

Expected: build succeeds (type-check passes).

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu-linh/Documents/dock-manager
git add client/src/features/port/components/PortConfigsSection.tsx
git commit -m "feat(reid): surface overlap-merge params in port-config UI"
```

---

## Self-review

- **Spec coverage:** All 7 keys from the Phần 3 table are added to config, init_db, schema_patches, runtime config, and UI. The spec's reuse note (`reid_visual_threshold`, `reid_handoff_window_sec`, `edge_zone_ratio` stay as-is) is honored — none are renamed.
- **Type consistency:** Key names are identical across `init_db.py`, `schema_patches.py`, `runtime_cfg` dict, and the UI maps. Booleans use `_to_bool`, floats use `_to_float`. Settings names are UPPER_SNAKE, config keys are lower_snake — matches existing convention.
- **No behavior change yet:** No consumer reads these keys in this plan — they are wired in Phần 2. This plan is intentionally inert at runtime so it can land independently.

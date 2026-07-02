# Berth State Persist Through Restart (F2) Implementation Plan

> REQUIRED SUB-SKILL: Execute each task with subagent workflow.

**Goal:** Persist berth_in_ts / berth_out_ts across pipeline restart so mid-track berth states survive process crashes. Currently `CrossCameraReIdManager.GlobalIdentity` and `BoundaryCrossingTracker` keep berth state in-memory — lost on restart.

**Architecture:** Seam anchors already persist `AnchoredIdentity` → `anchored_identities` table. Extended same table with `berth_in_ts` / `berth_out_ts`. On pipeline startup → restore berth state into `reid_manager` + `boundary_tracker`. On anchor flush → persist berth timestamps.

**Flow:**
- `AnchoredIdentity` model: +`berth_in_ts`, `berth_out_ts` columns
- `AnchoredIdentityRepository`: save/load berth fields in upsert/row_to_state
- `Schema patches`: add columns on existing DBs
- `PipelineService._restore_berth_state()`: new method called in `start()` before pipeline init
- `GlobalIdentity`: berth_in_ts/berth_out_ts restored from DB row

## Files

- Modify: `server/app/models/anchored_identity.py` — add `berth_in_ts`, `berth_out_ts` columns
- Modify: `server/app/repositories/anchored_identity_repository.py` — handle berth fields in upsert/row_to_state
- Modify: `server/app/db/schema_patches.py` — add `_ensure_anchored_identities_berth_columns()`
- Modify: `server/app/db/init_db.py` — add berth columns in CREATE TABLE (sync schema)
- Modify: `server/app/services/ai/cross_camera_reid.py` — add `restore_berth_state()` method
- Modify: `server/app/services/pipeline_service.py` — call restore in startup sequence
- Modify: `server/app/services/ai/anchored_identity.py` or seam_anchor_verifier — persist on anchor save
- Test: verify restart preserves berth state

---

### Task 1: Add berth columns to `AnchoredIdentity` model

**File:** `server/app/models/anchored_identity.py`

Insert after `confidence` column:

```python
    berth_in_ts = Column(Float, nullable=True)
    berth_out_ts = Column(Float, nullable=True)
```

Expected: Model compiles, no import changes.

---

### Task 2: Handle berth fields in repository

**File:** `server/app/repositories/anchored_identity_repository.py`

**2a.** In `upsert()` payload dict, after `'confidence'` line:
```python
            'berth_in_ts': state.berth_in_ts,
            'berth_out_ts': state.berth_out_ts,
```

**2b.** In `row_to_state()` return dict, after `'anchored_at'`:
```python
            berth_in_ts=row.berth_in_ts,
            berth_out_ts=row.berth_out_ts,
```

---

### Task 3: Schema patch for existing DBs

**File:** `server/app/db/schema_patches.py`

Add function `_ensure_anchored_identities_berth_columns()`. Pattern identical to existing patch functions.

Register in `apply_schema_patches()`.

---

### Task 4: Init DB sync

**File:** `server/app/db/init_db.py`

In `Base.metadata.create_all()` block — just ensure `create_all` picks up new columns automatically (SQLAlchemy `create_all` adds NEW columns on existing tables? No — that's why patches exist). So init_db just has the updated model, patches handle ALTER.

Update the `CREATE TABLE IF NOT EXISTS` in schema_patches `_ensure_anchored_identities()` to include the new columns (for fresh installs).

---

### Task 5: Save berth state on anchor upsert

**File:** Examine `server/app/services/ai/seam_anchor_verifier.py` — find where `anchored_identity_repo.upsert()` is called. Pass berth_in_ts/berth_out_ts from the identity before persisting.

Location: likely in `_flush_anchor_to_db()` or similar. The state's berth_in_ts/berth_out_ts need to be populated before upsert.

---

### Task 6: Restore berth state on startup in `pipeline_service.py`

**File:** `server/app/services/pipeline_service.py`

New method `_restore_berth_state()` called from `start()` before `_init_ai_components()`.

Steps:
1. Query `anchored_identities` for records with `berth_in_ts IS NOT NULL`.
2. For each record, call `reid_manager.restore_berth_state(global_id, berth_in_ts, berth_out_ts)`

---

### Task 7: `CrossCameraReIdManager.restore_berth_state()`

**File:** `server/app/services/ai/cross_camera_reid.py`

New method:
```python
def restore_berth_state(self, global_id: str, berth_in: float | None, berth_out: float | None) -> None:
    with self._lock:
        identity = self._identities.get(str(global_id))
        if identity is None:
            return
        if berth_in is not None:
            identity.berth_in_ts = berth_in if identity.berth_in_ts is None else min(identity.berth_in_ts, berth_in)
        if berth_out is not None:
            identity.berth_out_ts = berth_out if identity.berth_out_ts is None else max(identity.berth_out_ts, berth_out)
```

---

### Task 8: Test

Manual verification: start pipeline with active seam-anchored identities, crash container, restart — check that berth_in / berth_out still appear on Detection records for tracks that completed after restart.

```bash
cd /home/ubuntu-linh/Documents/dock-manager/server
python -c "
from app.db.session import SessionLocal
from app.models.anchored_identity import AnchoredIdentity
db = SessionLocal()
try:
    cols = [c['name'] for c in db.bind.dialect.get_columns(db.bind, 'anchored_identities')]
    assert 'berth_in_ts' in cols, 'missing berth_in_ts'
    assert 'berth_out_ts' in cols, 'missing berth_out_ts'
    print('✅ Columns exist')
finally:
    db.close()
"
```

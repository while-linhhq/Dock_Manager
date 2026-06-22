# Ship ID Rule Engine — Design Spec

**Date:** 2026-06-22  
**Status:** Approved  
**Scope:** Global rule management for OCR-based vessel ID recognition — regex patterns, blacklist, convert map.

---

## Problem Statement

The current OCR pipeline uses a single hardcoded regex `([A-Z50]{2})[-\s]?(\d{4})` in `server/app/utils/ai/ship_id_recognizer.py`. This creates three operational problems:

1. **Inflexible patterns** — Only 4-digit suffixes are matched (e.g., SG-1234). Vessels with 5-digit IDs (e.g., SG-12345) are silently dropped.
2. **No bad-value rejection** — OCR errors like `SC-9999` (a known impossible prefix) are voted in and persist to the DB.
3. **No correction mapping** — When OCR consistently misreads `SG-4567` as `SC-4567` (G/C visual confusion), there is no way to auto-correct short of modifying source code.

All rules must be manageable from the web UI by operators, apply globally (all cameras, all vessel types), and take effect without restarting the pipeline.

---

## Architecture Overview

```
UI (VesselsPage → tab 3)
    │  CRUD + Reload trigger
    ▼
FastAPI endpoints  /api/v1/ship-id-rules/
    │  read/write
    ▼
PostgreSQL (ship_id_patterns | ship_id_blacklist | ship_id_convert_map)
    │  polled every 30s
    ▼
ShipIdRuleEngine (singleton, in-memory cache)
    │  shared reference
    ▼
ShipIdRecognizer (per-camera instance)
    │  called per OCR frame
    ▼
OcrWorkerThread → BoatTracker (vote + lock)
```

---

## Section 1 — Database Schema

Three new tables added via `server/app/db/schema_patches.py` at startup.

### `ship_id_patterns`

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| name | VARCHAR(100) NOT NULL | Human label, e.g. "Standard 4-digit" |
| pattern | VARCHAR(500) NOT NULL | Raw Python regex string |
| priority | INTEGER NOT NULL DEFAULT 0 | Higher = tried first |
| description | TEXT | Optional operator notes |
| is_active | BOOLEAN NOT NULL DEFAULT TRUE | |
| created_at | TIMESTAMP DEFAULT NOW() | |
| updated_at | TIMESTAMP DEFAULT NOW() | |

### `ship_id_blacklist`

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| value | VARCHAR(100) NOT NULL UNIQUE | Normalized upper-case, e.g. "SC-9999" |
| reason | TEXT | Optional |
| created_at | TIMESTAMP DEFAULT NOW() | |

### `ship_id_convert_map`

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| wrong_value | VARCHAR(100) NOT NULL UNIQUE | Normalized, e.g. "SC-4567" |
| correct_value | VARCHAR(100) NOT NULL | Normalized, e.g. "SG-4567" |
| reason | TEXT | Optional |
| created_at | TIMESTAMP DEFAULT NOW() | |

### Seed data on first migration

Insert the current hardcoded pattern so existing behavior is preserved:

```sql
INSERT INTO ship_id_patterns (name, pattern, priority, description, is_active)
VALUES ('Standard (2 chữ + 4 số)', '([A-Z50]{2})[-\s]?(\d{4})', 100,
        'Pattern mặc định — prefix 2 ký tự, hậu tố 4 chữ số', TRUE)
ON CONFLICT DO NOTHING;
```

---

## Section 2 — Backend Rule Engine

### `ShipIdRuleEngine` — `server/app/services/ai/ship_id_rule_engine.py`

Module-level singleton. All `ShipIdRecognizer` instances share one reference.

**Internal state (in-memory, protected by `threading.RLock`):**
- `_compiled_patterns: list[CompiledPattern]` — sorted by priority desc, pre-compiled `re.Pattern`
- `_blacklist: set[str]` — normalized upper-case values
- `_convert_map: dict[str, str]` — wrong → correct mapping
- `_last_state_hash: str` — MD5 of `MAX(updated_at)` across 3 tables, used to skip no-op reloads

**Key methods:**

```python
def reload(self, db: Session) -> None:
    """Load rules from DB. Skips if state hash unchanged."""

def apply(self, candidate_id: str) -> str | None:
    """
    1. Normalize (strip, upper)
    2. Blacklist check → return None if matched
    3. Convert map lookup → return correct_value if found
    4. Return candidate_id unchanged
    """

def extract_ship_ids(self, text: str) -> list[dict]:
    """
    Try each active pattern in priority order.
    Normalize prefix (5→S, 0→O).
    Apply blacklist + convert_map on each candidate.
    Return list of {id, confidence, raw_text}.
    """
```

**Hot reload — daemon polling thread:**

```python
def start_rule_engine_daemon(engine: ShipIdRuleEngine, interval_s: int = 30) -> None:
    """Background thread: polls DB every interval_s seconds."""
```

Started once in `main.py` lifespan alongside the existing pipeline setup. Uses a dedicated short-lived `SessionLocal()` per poll cycle.

### Modified: `ShipIdRecognizer` — `server/app/utils/ai/ship_id_recognizer.py`

- Constructor gains optional `rule_engine: ShipIdRuleEngine | None = None`
- `extract_ship_id()` delegates to `rule_engine.extract_ship_ids(text)` when engine is present
- Falls back to current hardcoded-pattern behavior when `rule_engine is None` — backward compatible

### Wiring — `server/app/services/ai/per_camera_pipeline.py`

`PerCameraPipeline.__init__` receives the shared `rule_engine` singleton and passes it to `ShipIdRecognizer(rule_engine=rule_engine)`.

### New API layer

**File:** `server/app/api/v1/endpoints/ship_id_rules.py`  
**Router prefix:** `/api/v1/ship-id-rules`  
**Auth:** same `get_current_user` dependency as other admin endpoints

| Method | Path | Description |
|---|---|---|
| GET | /patterns | List all patterns |
| POST | /patterns | Create pattern |
| PUT | /patterns/{id} | Update pattern |
| DELETE | /patterns/{id} | Delete pattern |
| GET | /blacklist | List blacklist |
| POST | /blacklist | Add entry |
| DELETE | /blacklist/{id} | Remove entry |
| GET | /convert-map | List convert map |
| POST | /convert-map | Add entry |
| PUT | /convert-map/{id} | Update entry |
| DELETE | /convert-map/{id} | Remove entry |
| POST | /reload | Force immediate engine reload |

**New schemas:** `server/app/schemas/ship_id_rules.py`  
**New repository:** `server/app/repositories/ship_id_rule_repository.py`  
**Router registration:** `server/app/api/v1/router.py`

---

## Section 3 — Frontend UI

New tab **"Cấu Hình Nhận Diện"** added as the third tab in `VesselsMainTabs.tsx`.

### Layout

Three collapsible cards within `RecognitionConfigSection.tsx`:

1. **Regex Patterns** (`PatternTable.tsx`)
   - Table: Name | Pattern | Priority | Active | Actions (Edit / Delete)
   - Inline live-test input: paste sample text → shows matched IDs highlighted
   - Add/Edit modal: name, pattern (regex syntax validated client-side with `new RegExp()`), priority (integer), description, is_active toggle
   - Rows sorted by priority descending, priority displayed prominently

2. **Blacklist** (`BlacklistSection.tsx`)
   - Table: Value | Reason | Created At | Delete
   - Inline add form (no modal needed): value input + optional reason → POST on submit
   - Warns if value already exists in convert map (conflicting rules)

3. **Convert Map** (`ConvertMapTable.tsx`)
   - Table: Wrong Value → Correct Value | Reason | Actions
   - Add/Edit modal: wrong_value, correct_value, optional reason
   - Validation: `wrong_value !== correct_value`, neither can be empty

**"Reload ngay" button** at the top of the tab — calls `POST /ship-id-rules/reload`, shows toast on success/failure.

**Active-rules badge** on the tab label: e.g. `Cấu Hình Nhận Diện (3)` showing count of active patterns.

### New files

```
client/src/features/vessels/
  components/RecognitionConfigSection.tsx   — tab content container
  components/PatternTable.tsx               — regex pattern CRUD
  components/BlacklistSection.tsx           — blacklist CRUD
  components/ConvertMapTable.tsx            — convert map CRUD
  services/shipIdRulesApi.ts                — typed API calls
  types/ship-id-rules.types.ts              — TS interfaces
  store/shipIdRulesStore.ts                 — Zustand store
```

### Modified files

```
client/src/features/vessels/
  components/VesselsMainTabs.tsx            — add third tab
  views/VesselsView.tsx                     — render RecognitionConfigSection
```

---

## Section 4 — Data Flow (OCR frame processing)

```
OCR frame arrives
    │
    ▼
ShipIdRecognizer.extract_ship_id(ocr_results)
    │   for each OCR line:
    │     1. clean text (upper, strip)
    │     2. try patterns in priority order (via RuleEngine)
    │     3. on match: normalize prefix (5→S, 0→O)
    │     4. apply RuleEngine.apply(candidate):
    │          a. blacklist? → discard
    │          b. convert map? → replace with correct_value
    │          c. pass through unchanged
    │     5. append to found_ids
    ▼
OcrWorkerThread → add_ocr_vote(track_id, ship_id, confidence)
    ▼
BoatTracker.get_voted_ship_id() → confidence-weighted majority
    ▼
pipeline_service.py → persist to DB
```

---

## Section 5 — Error Handling & Edge Cases

- **Invalid regex on save:** Server validates `re.compile(pattern)` before DB insert. Returns 422 with message if invalid.
- **Circular convert map:** Warn (but allow) if `correct_value` is itself a key in `wrong_value` of another entry.
- **Conflicting blacklist + convert map:** If same value appears in both, blacklist wins (reject before convert lookup). UI warns operator.
- **No active patterns:** Engine falls back to the hardcoded default pattern to prevent total OCR blindness.
- **DB unavailable during poll:** Reload silently skips that cycle, logs a warning. Rules stay at last-known-good state.
- **Concurrent rule edits:** `updated_at` is refreshed on every PUT/POST. Poll detects change on next cycle (max 30s lag after save).

---

## Out of Scope

- Per-camera or per-vessel-type rule scoping (can be added later via foreign keys)
- Prefix-based convert rules (e.g., all `SC-*` → `SG-*`)
- Rule versioning / audit log (existing `audit_logs` middleware covers API mutations automatically)
- Automated test generation for patterns

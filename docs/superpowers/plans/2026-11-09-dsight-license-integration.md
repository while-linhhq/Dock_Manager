# DSight License Integration (Keygate) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add license activation/verification + offline grace + camera quota + extendable module-feature gating to DSight (FastAPI + React), talking to the self-hosted Keygate server already configured (`trial` max_cameras=2, `standard` max_cameras=4, 1 activation).

**Architecture:** A single DB-backed `LicenseService` (state row `license_state`) wraps a thin Keygate HTTP client + Ed25519 token verifier. A `FeatureRegistry` normalizes Keygate's features map (bool as boolean, ints as strings) and provides typed accessors. Enforcement is warn-first (`LICENSE_ENFORCEMENT=warn`, DB-overridable at runtime) and gates only *new* behavior (camera create, pipeline start, future module routers) — never login/reads/stop/a running pipeline. Admin UI (React feature folder) shows status, expiry banner, key entry and enforcement toggle.

**Tech Stack:** Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL + `requests` (already pinned) + `cryptography` (transitive via python-jose) + pytest; React 19 + TypeScript + Vite + Zustand + Tailwind.

**Spec:** `docs/superpowers/specs/2026-11-09-dsight-license-keygate-design.md` (read it before starting; §7 is the source-pattern contract, §5 the Keygate model, §13 the resolved decisions).

## Global Constraints

- Keygate v0.1.20 contract is fixed: `POST /api/v1/license/activate|verify|entitlements`, `GET /api/v1/license/pubkey`; admin `POST /admin/licenses`, `.../valid-until|suspend|reinstate|revoke|rotate-key|change-plan`, `DELETE /admin/activations/{id}`, addons attach/detach.
- Effective features: plan entitlements merged with enabled addons (addon replaces same-named feature). `int`/`string`/`quota` features arrive as **strings**; only `bool`/`flag` are JSON booleans. Unknown/missing feature = not granted.
- `max_cameras` counts **all camera rows** (`camera_repo.count_all(db)`), active or not. Plans: `trial` = 2, `standard` = 4, `lifetime` = 4 (all already created in Keygate); per-customer camera addon overrides the value. `lifetime` licenses are created with no `valid_until` (perpetual).
- Verify `404 LICENSE_NOT_FOUND` is a definitive server answer (revoked/suspended/expired-past-grace/unknown key/unactivated device): invalidate immediately. Only timeout/5xx/network keep the cached token until `exp` (clamped to `vun + grc`). Suspend/revoke have **no** grace; only expiry uses `grace_days`. Trial hard-stops (grace 0).
- `LICENSE_ENFORCEMENT` env is only the default; the effective mode lives in `license_state.enforcement_mode` and is changeable at runtime via admin endpoint. Default `warn`.
- Never block: login/refresh, `/health`, reads, `POST /pipeline/stop`, pipeline status/logs/WS, a pipeline already running. Never delete/disable existing cameras on quota violation.
- **Minimal UI (approved):** only a first-run key-entry screen when `status === 'unlicensed'`; **no** license info page, **no** license menu entry, **no** global banner. Inline near-limit warnings on the Port camera page only. Enforcement mode is changed by ops via the admin API/runbook, not the UI.
- No new Python dependencies (use `requests`; `cryptography` already available through `python-jose[cryptography]`). No Alembic: add ORM model **and** a `schema_patches._ensure_license_state()` patch, registered in `apply_schema_patches()`.
- Server code: absolute imports `app.*`; 4-space indent; single quotes; no relative imports. Client: kebab-case files, feature folder exports only via `index.ts`, routes only via `PATHS`, 2-space indent, single quotes, semicolons.
- Tests must never call the real Keygate network. Only Task 14's staging probe may use the network, and only when `LICENSE_PROBE_URL`/`LICENSE_PROBE_KEY` env vars are set.
- License key is secret: never log it, never return plaintext except the one-time create response; store encrypted (`app.utils.crypto`). `server/.env` is baked into the Docker image — do **not** put the customer license key there in docs.
- **"Mã máy" = hardware fingerprint computed at runtime** from host mounts: `/etc/machine-id`, `/sys/class/dmi/id/product_uuid`, `/sys/class/dmi/id/board_serial` (optional) → `sha256("DSIGHT|" + values)` → `DSIGHT-XXXX-XXXX-XXXX` (Crockford/base32 uppercase, groups of 4). `LICENSE_INSTANCE_ID` env is a dev-only override. The identifier sent to Keygate is this code; a changed code invalidates the license (ops must delete the old activation).

## Review Focus

1. **Feature value types:** `"max_cameras":"12"` must parse to 12; `"max_cameras":"abc"` or missing must fall back to the registry default (0 = no cameras), never unlimited. Tests in Task 2 + Task 9.
2. **Verify 404 vs network error:** a 404 must invalidate (banner/block new behavior under enforce) and a timeout/5xx must not; a blip must not lock a paying customer out. Tests in Task 7.
3. **Fresh install / Keygate unreachable at boot:** app must boot, allow login and key entry, and never raise in lifespan. Test in Task 7 + manual check in Task 14.
4. **Running pipeline during expiry/revoke:** only new starts are gated; running pipeline untouched; existing cameras are never auto-disabled/deleted. Tests in Tasks 9–10.
5. **Clock skew / token trust:** expired token or tampered signature must not be trusted; grace must not extend suspended/revoked. Tests in Task 3 + Task 7.
6. **Single-row state under concurrent verify:** background loop + admin refresh must not corrupt state; last write wins is acceptable, partial JSON must not. Test in Task 7.
7. **Camera quota bypass:** creating inactive camera then activating it, or camera groups, must not exceed the row count. Tests in Task 9.
8. **FE resilience:** `/license/status` failure must not break the app shell or logout, and must not trap the user on the activation screen; a 401 follows the existing httpClient flow, a 403 (camera limit) shows the detail message. Test in Task 12 (build/lint) + Task 13.

---

## Task 1: Settings + secret encryption

**Files:**
- Modify: `server/app/core/config.py` (insert a `# Licensing (Keygate)` block after the Zalo block, before `# Logging`)
- Create: `server/app/utils/crypto.py`
- Modify: `server/.env.example` (append documented block)
- Test: `server/app/tests/test_license_config_crypto.py`

**Interfaces:**
- Produces settings: `LICENSE_SERVER_URL: str = 'https://license.dtgsoft.vn'`, `LICENSE_KEY: str = ''`, `LICENSE_INSTANCE_ID: str = ''`, `LICENSE_ENFORCEMENT: Literal['off','warn','enforce'] = 'warn'`, `LICENSE_CHECKIN_HOURS: int = 6`, `LICENSE_HTTP_TIMEOUT_SEC: float = 5.0`.
- Produces: `app.utils.crypto.encrypt_secret(value: str) -> str`; `decrypt_secret(token: str) -> str | None` (returns `None` for invalid/rotated-key ciphertext; never raises).

- [ ] **Step 1: Write the failing test**

```python
# server/app/tests/test_license_config_crypto.py
from app.core.config import settings
from app.utils.crypto import decrypt_secret, encrypt_secret

def test_license_settings_defaults():
    assert settings.LICENSE_SERVER_URL == 'https://license.dtgsoft.vn'
    assert settings.LICENSE_ENFORCEMENT == 'warn'
    assert settings.LICENSE_CHECKIN_HOURS == 6

def test_secret_roundtrip():
    token = encrypt_secret('DSIGHT-ABCD-1234')
    assert token != 'DSIGHT-ABCD-1234'
    assert decrypt_secret(token) == 'DSIGHT-ABCD-1234'

def test_decrypt_invalid_returns_none():
    assert decrypt_secret('not-a-fernet-token') is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_config_crypto.py -v`
Expected: FAIL — `ImportError: cannot import name 'encrypt_secret'` (or AttributeError for settings).

- [ ] **Step 3: Implement**

Add the settings block (exact names above; Vietnamese comments like neighbours). `crypto.py`: derive a Fernet key as `base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest())`, cache it with `functools.lru_cache(maxsize=1)`; `encrypt_secret` returns `fernet.encrypt(value.encode()).decode()`; `decrypt_secret` catches `InvalidToken`/`Exception` and returns `None`. `.env.example`: add `LICENSE_SERVER_URL`, `LICENSE_INSTANCE_ID`, `LICENSE_ENFORCEMENT=warn`, `LICENSE_CHECKIN_HOURS=6` (comment: do NOT put `LICENSE_KEY` here; enter it in the admin UI).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_config_crypto.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/core/config.py server/app/utils/crypto.py server/.env.example server/app/tests/test_license_config_crypto.py
git commit -m "feat(license): add Keygate settings and license-key encryption helper"
```

---

## Task 2: Feature registry + normalization

**Files:**
- Create: `server/app/core/license/__init__.py` (empty)
- Create: `server/app/core/license/features.py`
- Test: `server/app/tests/test_license_features.py`

**Interfaces:**
- Produces: `FeatureSpec` frozen dataclass `(type: Literal['bool','int','string','quota'], default: bool | int | str, label: str = '')`.
- Produces: `FEATURES: dict[str, FeatureSpec]` containing at least `'max_cameras': FeatureSpec('int', 0, 'Số camera tối đa')`.
- Produces: `normalize_features(raw: Mapping[str, Any]) -> dict[str, Any]` — bool/flag → bool; int/quota → int when parseable, else registry default (or raw when no spec); string → str; unknown keys kept as-is; registry defaults are **not** injected into the returned dict.
- Produces: `feature_bool(features, key) -> bool` (missing/invalid → spec default, default False), `feature_int(features, key) -> int` (missing/invalid → spec default), `max_cameras(features) -> int` (shorthand for `feature_int(features, 'max_cameras')`).

- [ ] **Step 1: Write the failing test**

```python
# server/app/tests/test_license_features.py
from app.core.license.features import feature_bool, feature_int, max_cameras, normalize_features

def test_int_feature_string_is_parsed():
    assert normalize_features({'max_cameras': '12'}) == {'max_cameras': 12}

def test_missing_int_feature_falls_back_to_zero():
    assert max_cameras({}) == 0
    assert feature_int({'max_cameras': 'abc'}, 'max_cameras') == 0

def test_bool_feature_stays_bool():
    assert feature_bool({'module_ai_lab': True}, 'module_ai_lab') is True
    assert feature_bool({'module_ai_lab': 'true'}, 'module_ai_lab') is True
    assert feature_bool({}, 'module_ai_lab') is False

def test_unknown_feature_is_preserved_but_not_coerced():
    out = normalize_features({'custom_flag': 'yes'})
    assert out['custom_flag'] == 'yes'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_features.py -v`
Expected: FAIL — module/import not found.

- [ ] **Step 3: Implement `features.py`**

Write the registry + helpers per the Interfaces block. `normalize_features` iterates `raw.items()`, looks up `FEATURES.get(key)`, coerces by `spec.type` (`bool`/`flag`: `value is True or str(value).lower() == 'true'`; `int`/`quota`: `int(value)` in try/except → spec.default; `string`: `str(value)`), and passes unknown keys through unchanged. `feature_int`/`feature_bool` read the already-normalized dict and fall back to `FEATURES[key].default` when absent or the wrong type.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_features.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/core/license/__init__.py server/app/core/license/features.py server/app/tests/test_license_features.py
git commit -m "feat(license): add feature registry and Keygate feature normalization"
```

---

## Task 3: Offline Ed25519 token verification

**Files:**
- Create: `server/app/core/license/token.py`
- Test: `server/app/tests/test_license_token.py`

**Interfaces:**
- Produces: `class LicenseTokenError(Exception)`.
- Produces: `@dataclass(frozen=True) LicenseTokenClaims` with fields `lid: str`, `pid: str`, `pln: str`, `sts: str`, `did: str`, `ftr: dict[str, Any]`, `iat: int`, `exp: int`, `vun: int | None`, `upd: int | None`, `grc: int`, `nce: str`, `fpr: str`.
- Produces: `verify_license_token(token: str, public_key_hex: str, *, expected_identifier: str, now: datetime | None = None) -> LicenseTokenClaims` — verifies `base64url(payload).base64url(signature)` with Ed25519 over the **base64url payload string**, requires `did == expected_identifier`, `now < exp`; raises `LicenseTokenError` otherwise.

- [ ] **Step 1: Write the failing test** (use `cryptography.hazmat.primitives.asymmetric.ed25519` to mint a keypair and sign a payload in the test helper)

```python
# server/app/tests/test_license_token.py
import base64, json, time
from datetime import datetime, timezone
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from app.core.license.token import LicenseTokenError, verify_license_token

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()

def _sign(payload: dict, key: Ed25519PrivateKey) -> str:
    p = _b64(json.dumps(payload).encode())
    return f'{p}.{_b64(key.sign(p.encode()))}'

def _keypair():
    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return priv, pub_hex

def _claims(**over):
    base = {'lid': 'l1', 'pid': 'p1', 'pln': 'Standard', 'sts': 'active', 'did': 'inst-1',
            'ftr': {'max_cameras': '12'}, 'iat': int(time.time()), 'exp': int(time.time()) + 3600,
            'grc': 15, 'nce': 'n1', 'fpr': 'f' * 16}
    base.update(over)
    return base

def test_valid_token():
    priv, pub = _keypair()
    claims = verify_license_token(_sign(_claims(), priv), pub, expected_identifier='inst-1')
    assert claims.ftr == {'max_cameras': '12'}
    assert claims.grc == 15

def test_tampered_payload_fails():
    priv, pub = _keypair()
    token = _sign(_claims(), priv)
    payload, sig = token.split('.')
    with pytest.raises(LicenseTokenError):
        verify_license_token(f'{payload[:-2]}AA.{sig}', pub, expected_identifier='inst-1')

def test_wrong_identifier_fails():
    priv, pub = _keypair()
    with pytest.raises(LicenseTokenError):
        verify_license_token(_sign(_claims(), priv), pub, expected_identifier='other')

def test_expired_token_fails():
    priv, pub = _keypair()
    with pytest.raises(LicenseTokenError):
        verify_license_token(_sign(_claims(exp=int(time.time()) - 1), priv), pub, expected_identifier='inst-1')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_token.py -v`
Expected: FAIL — import not found.

- [ ] **Step 3: Implement `token.py`**

Use `Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))`; split with `rsplit('.', 1)`; base64url-decode with padding restored; `public_key.verify(sig, payload_b64.encode())`; `json.loads` payload; validate required keys; compare `did`; compare `exp` against `int(now.timestamp())` (`now` defaults to `datetime.now(timezone.utc)`). Wrap every failure in `LicenseTokenError` with a short reason (no secret material).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_token.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/core/license/token.py server/app/tests/test_license_token.py
git commit -m "feat(license): verify Keygate Ed25519 license tokens offline"
```

---

## Task 4: Keygate HTTP client

**Files:**
- Create: `server/app/core/license/keygate_client.py`
- Test: `server/app/tests/test_license_keygate_client.py`

**Interfaces:**
- Produces: `class KeygateError(Exception)` with attributes `status: int | None`, `code: str | None`, `details: dict | None`; `class KeygateNetworkError(KeygateError)` (status `None`).
- Produces: `class KeygateClient`:
  - `__init__(self, base_url: str, timeout: float = 5.0)`
  - `activate(self, license_key: str, identifier: str, label: str = '') -> dict` → POST `/api/v1/license/activate`
  - `verify(self, license_key: str, identifier: str) -> dict` → POST `/api/v1/license/verify`
  - `entitlements(self, license_key: str) -> dict` → POST `/api/v1/license/entitlements`
  - `public_key(self) -> str` → GET `/api/v1/license/pubkey` → hex `public_key`
  - Each returns the unwrapped `data` object; raises `KeygateNetworkError` on `requests.RequestException`, `KeygateError` on non-2xx with `error.code`/`error.details` parsed.

- [ ] **Step 1: Write the failing test** (monkeypatch `requests.request`, no real network)

```python
# server/app/tests/test_license_keygate_client.py
import pytest, requests
from app.core.license.keygate_client import KeygateClient, KeygateError, KeygateNetworkError

class _Resp:
    def __init__(self, status, payload): self.status_code, self._payload = status, payload
    def json(self): return self._payload

def test_activate_unwraps_data(monkeypatch):
    calls = {}
    def fake_request(method, url, json=None, timeout=None, headers=None):
        calls.update(method=method, url=url, json=json)
        return _Resp(200, {'success': True, 'data': {'status': 'activated', 'token': 't'}})
    monkeypatch.setattr(requests, 'request', fake_request)
    out = KeygateClient('https://kg.test').activate('K', 'inst-1', 'port-a')
    assert out['status'] == 'activated'
    assert calls['url'] == 'https://kg.test/api/v1/license/activate'
    assert calls['json'] == {'license_key': 'K', 'identifier': 'inst-1', 'label': 'port-a'}

def test_404_maps_to_license_not_found(monkeypatch):
    monkeypatch.setattr(requests, 'request', lambda *a, **k: _Resp(404, {'success': False, 'error': {'code': 'LICENSE_NOT_FOUND', 'message': 'x'}}))
    with pytest.raises(KeygateError) as ei:
        KeygateClient('https://kg.test').verify('K', 'inst-1')
    assert ei.value.status == 404 and ei.value.code == 'LICENSE_NOT_FOUND'

def test_network_error_wrapped(monkeypatch):
    def boom(*a, **k): raise requests.ConnectionError('down')
    monkeypatch.setattr(requests, 'request', boom)
    with pytest.raises(KeygateNetworkError):
        KeygateClient('https://kg.test').verify('K', 'inst-1')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_keygate_client.py -v`
Expected: FAIL — import not found.

- [ ] **Step 3: Implement `keygate_client.py`**

Use a private `_post(path, payload)`/`_get(path)` with `requests.request(method, f'{self.base_url.rstrip("/")}{path}', json=payload, timeout=self.timeout, headers={'Accept': 'application/json'})`. Non-2xx: parse `error` object into `KeygateError(status=resp.status_code, code=..., details=...)`; if body isn't JSON use `code=None`. `public_key` returns `data['public_key']`. No retries here (the service decides).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_keygate_client.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/core/license/keygate_client.py server/app/tests/test_license_keygate_client.py
git commit -m "feat(license): add Keygate HTTP client"
```

---

## Task 5: `license_state` model, repository, schema patch

**Files:**
- Create: `server/app/models/license_state.py`
- Create: `server/app/repositories/license_state_repository.py`
- Modify: `server/app/models/__init__.py` (import + `__all__`)
- Modify: `server/app/db/schema_patches.py` (add `_ensure_license_state()` and register it in `apply_schema_patches()`)
- Test: `server/app/tests/test_license_state_repository.py`

**Interfaces:**
- Produces ORM `LicenseState` (`__tablename__ = 'license_state'`, single row `id=1`) with columns: `id Integer PK`, `instance_id String(64) NOT NULL`, `license_key_enc Text NULL`, `license_id String(64) NULL`, `plan_name String(120) NULL`, `status String(32) NOT NULL default 'unlicensed'`, `valid_until DateTime(timezone=True) NULL`, `grace_days Integer NOT NULL default 0`, `features JSONB NOT NULL default dict`, `token Text NULL`, `token_exp DateTime(timezone=True) NULL`, `pubkey Text NULL`, `last_verified_at DateTime(timezone=True) NULL`, `last_error Text NULL`, `enforcement_mode String(16) NOT NULL default 'warn'`, `updated_at DateTime(timezone=True) server_default=func.now(), onupdate=func.now()`.
- Produces `LicenseStateRepository` with `get(self, db) -> LicenseState | None`, `ensure(self, db, instance_id: str) -> LicenseState` (creates `id=1` if missing, keeps existing `instance_id`), `update(self, db, **fields) -> LicenseState`; module singleton `license_state_repo`.
- Produces `_ensure_license_state()` in `schema_patches.py` (idempotent; Postgres-only; `CREATE TABLE IF NOT EXISTS` with `CHECK (id = 1)`; no-op if table exists).

- [ ] **Step 1: Write the failing test**

```python
# server/app/tests/test_license_state_repository.py
from sqlalchemy import inspect
from app.db.session import SessionLocal, engine
from app.repositories.license_state_repository import LicenseStateRepository

def test_ensure_is_idempotent():
    db = SessionLocal()
    try:
        repo = LicenseStateRepository()
        row = repo.ensure(db, 'inst-test-1')
        assert row.id == 1
        again = repo.ensure(db, 'ignored')
        assert again.instance_id == row.instance_id  # existing row wins
        repo.update(db, status='valid', features={'max_cameras': 12})
        db.refresh(again)
        assert again.status == 'valid' and again.features == {'max_cameras': 12}
    finally:
        db.rollback(); db.close()

def test_schema_patch_creates_table():
    from app.db.schema_patches import _ensure_license_state
    _ensure_license_state()
    _ensure_license_state()
    assert inspect(engine).has_table('license_state')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_state_repository.py -v`
Expected: FAIL — import/table not found.

- [ ] **Step 3: Implement model, repository, schema patch**

Model imports `JSONB` from `sqlalchemy.dialects.postgresql`, `func` from sqlalchemy. Repository mirrors `camera_repository` class style; `ensure` does `db.get(LicenseState, 1)` then insert/flush (no commit — callers commit). `update` sets attributes from `**fields`, `db.flush()`, returns row. Schema patch mirrors `_ensure_camera_groups()` shape (inspect → has_table early return → Postgres dialect gate → `CREATE TABLE IF NOT EXISTS` + `CHECK (id = 1)` → `_patch_done('ensured license_state table')`); register `_ensure_license_state()` in `apply_schema_patches()` near the other `_ensure_*` calls.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_state_repository.py -v`
Expected: PASS (2 passed). Table exists in the dev DB afterwards (idempotent, harmless).

- [ ] **Step 5: Commit**

```bash
git add server/app/models/license_state.py server/app/models/__init__.py server/app/repositories/license_state_repository.py server/app/db/schema_patches.py server/app/tests/test_license_state_repository.py
git commit -m "feat(license): add license_state model, repository and schema patch"
```

---

## Task 6: Machine fingerprint + LicenseService state machine (local, no network)

**Files:**
- Create: `server/app/core/license/machine.py`
- Create: `server/app/core/license/service.py`
- Test: `server/app/tests/test_license_machine.py`
- Test: `server/app/tests/test_license_service_state.py`

**Interfaces:**
- Produces `machine.py`:
  - `MACHINE_CODE_PREFIX = 'DSIGHT'`
  - `def compute_machine_code(sources: Mapping[str, str]) -> str` — deterministic; joins sorted non-empty `key=value` pairs with `|`, SHA-256, base32-encodes the first 10 bytes without padding, groups in 4 (`DSIGHT-7K2M-9QX4-AB12` style). Empty sources → raises `ValueError`.
  - `def read_host_identity() -> dict[str, str]` — reads `/host/etc/machine-id`, `/host/sys/class/dmi/id/product_uuid`, `/host/sys/class/dmi/id/board_serial`; missing/unreadable files are skipped (never raises).
  - `def resolve_machine_code() -> str` — `settings.LICENSE_INSTANCE_ID` when set (dev override); else `compute_machine_code(read_host_identity())`; if no host identity is readable, logs a warning and falls back to a UUID persisted by the caller (see service).
- Produces pure function `compute_effective_status(*, has_key: bool, stored_status: str, valid_until: datetime | None, grace_days: int, now: datetime | None = None) -> str` → one of `unlicensed | valid | grace | expired | suspended | revoked | invalid`. Rules: no key → `unlicensed`; stored `suspended`/`revoked` win; no `valid_until` → `valid`; `now <= valid_until` → `valid`; `now <= valid_until + grace_days` → `grace`; else `expired`; unknown stored status → `invalid`.
- Produces `@dataclass(frozen=True) LicenseSnapshot` (fields mirror the row: `instance_id, license_id, plan_name, status, valid_until, grace_days, features, token, token_exp, pubkey, last_verified_at, last_error, enforcement_mode`; property `effective_status: str` computed at snapshot time).
- Produces `class LicenseService` (module singleton `license_service`) with:
  - `initialize(self) -> None` — load row (`SessionLocal`), ensure instance id (`settings.LICENSE_INSTANCE_ID` or row value or new `uuid4().hex`), commit; no network.
  - `snapshot(self) -> LicenseSnapshot` — cached in-memory; `refresh_snapshot()` re-reads DB.
  - `status(self) -> str`, `is_usable(self) -> bool` (`status in {'valid','grace'}`), `features(self) -> dict[str, Any]`, `max_cameras(self) -> int` (`features.max_cameras`), `enforcement_mode(self) -> str`, `set_enforcement_mode(self, mode: str) -> None` (persist to DB; validate `off|warn|enforce`), `days_left(self) -> int | None`, `license_key_hint(self) -> str | None` (decrypt the stored key and return `'****' + key[-4:]`; `None` when unlicensed).
- Enforcement semantics helpers: `should_block_new_behavior(self) -> bool` = `enforcement_mode == 'enforce' and not is_usable()`.

- [ ] **Step 1: Write the failing test** (pure function + service with a temp DB row; no Keygate calls)

```python
# server/app/tests/test_license_machine.py
from app.core.license.machine import compute_machine_code, read_host_identity, resolve_machine_code

def test_machine_code_is_deterministic_and_formatted():
    a = compute_machine_code({'machine_id': 'abc', 'product_uuid': 'def'})
    b = compute_machine_code({'product_uuid': 'def', 'machine_id': 'abc'})
    assert a == b and a.startswith('DSIGHT-') and len(a.split('-')) == 5

def test_machine_code_changes_with_hardware():
    assert compute_machine_code({'machine_id': 'abc'}) != compute_machine_code({'machine_id': 'xyz'})

def test_read_host_identity_never_raises():
    assert isinstance(read_host_identity(), dict)

def test_dev_override(monkeypatch):
    from app.core.license import machine
    monkeypatch.setattr(machine.settings, 'LICENSE_INSTANCE_ID', 'DEV-CODE', raising=False)
    assert resolve_machine_code() == 'DEV-CODE'
```

```python
# server/app/tests/test_license_service_state.py
from datetime import datetime, timedelta, timezone
from app.core.license.service import compute_effective_status

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)

def test_status_rules():
    assert compute_effective_status(has_key=False, stored_status='active', valid_until=None, grace_days=0, now=NOW) == 'unlicensed'
    assert compute_effective_status(has_key=True, stored_status='active', valid_until=NOW + timedelta(days=1), grace_days=15, now=NOW) == 'valid'
    assert compute_effective_status(has_key=True, stored_status='active', valid_until=NOW - timedelta(days=1), grace_days=15, now=NOW) == 'grace'
    assert compute_effective_status(has_key=True, stored_status='active', valid_until=NOW - timedelta(days=16), grace_days=15, now=NOW) == 'expired'
    assert compute_effective_status(has_key=True, stored_status='suspended', valid_until=NOW + timedelta(days=1), grace_days=15, now=NOW) == 'suspended'
    assert compute_effective_status(has_key=True, stored_status='revoked', valid_until=None, grace_days=0, now=NOW) == 'revoked'
    assert compute_effective_status(has_key=True, stored_status='weird', valid_until=None, grace_days=0, now=NOW) == 'invalid'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_service_state.py -v`
Expected: FAIL — import not found.

- [ ] **Step 3: Implement `service.py` (state part only; activation/verify in Task 7)**

Implement `machine.py` first (pure hashing + file readers + env override). Then `compute_effective_status` (pure, no DB imports). Then the service class: lazy `_snapshot`, `initialize()` opens `SessionLocal`, computes `resolve_machine_code()` (fallback: DB `uuid4().hex` when no host identity and no override, warn), calls `license_state_repo.ensure(db, machine_code)`, and if the stored `instance_id` differs from the computed code sets `status='invalid'` + `last_error='machine changed'` (does not auto-overwrite the old id until re-activation). Commits, sets snapshot; `snapshot()` raises `RuntimeError('LicenseService not initialized')` if not initialized. `set_enforcement_mode` validates and persists. Expose `machine_code() -> str`. No HTTP imports yet.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_service_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/app/core/license/service.py server/app/tests/test_license_service_state.py
git commit -m "feat(license): add license state machine and snapshot service"
```

---

## Task 7: Activation, verify, 404 classification, background loop, lifespan wiring

**Files:**
- Modify: `server/app/core/license/service.py` (activation/verify methods)
- Create: `server/app/core/license/background.py`
- Modify: `server/app/main.py` (lifespan: initialize + start/stop background)
- Test: `server/app/tests/test_license_service_sync.py`

**Interfaces:**
- `LicenseService.activate(self, license_key: str, *, label: str = '') -> dict` — calls `client.activate(key, self.machine_code(), label)`, persists `encrypt_secret(key)` + `instance_id = machine_code()`, then `verify_now()`; returns a dict `{'status': ..., 'features': ...}`.
- `LicenseService.verify_now(self) -> dict` — decrypt key (missing → `{'status': 'unlicensed'}`); `client.verify(key, self.machine_code())`:
  - 200: `_apply_verify_data(data)` (persist `license_id`, `plan_name`, `valid_until`, `grace_days`, `features=normalize_features(data['features'])`, `token`, decode token via `verify_license_token` to get `exp` + verify signature, fetch/cache `pubkey` via `client.public_key()` when missing, `last_verified_at=now`, `last_error=None`, status `active|trialing|past_due` → stored `'active'`).
  - `KeygateError(status=404)`: call `client.activate(key, instance_id)`; if it raises `KeygateError(403, code)`, map code → stored status (`LICENSE_SUSPENDED`→`suspended`, `LICENSE_REVOKED`→`revoked`, `LICENSE_EXPIRED`/`LICENSE_CANCELED`→`expired`, else `invalid`); if it raises 404/network, stored status `invalid`; if it succeeds (already_activated), keep previous state and set `last_error='verify 404 but activate ok'`. Persist, return.
  - `KeygateNetworkError` / other `KeygateError(5xx)`: keep cached snapshot/features, set `last_error`, do **not** change stored status.
  - A verify 200 without a `token` field (or an unverifiable token) must still persist `features`/`valid_until`; set `last_error` and keep the previous token.
- `LicenseService.client` injectable: `__init__(self, client: KeygateClient | None = None)`; default `KeygateClient(settings.LICENSE_SERVER_URL, settings.LICENSE_HTTP_TIMEOUT_SEC)`.
- `background.start_license_background()` / `async background.stop_license_background()` mirroring `sepay_background.py`: loop calls `license_service.verify_now()` in `asyncio.to_thread`; interval `settings.LICENSE_CHECKIN_HOURS * 3600`; on exception sleep `min(300, interval)`.
- Lifespan in `main.py`: after `run_startup_checks()`, call `license_service.initialize()` (inside try/except log; **never raise**) and `start_license_background()`; on shutdown `await stop_license_background()` before pipeline stop.

- [ ] **Step 1: Write the failing test** (fake client object, monkeypatched settings)

```python
# server/app/tests/test_license_service_sync.py
from datetime import datetime, timedelta, timezone
from app.core.license.keygate_client import KeygateError, KeygateNetworkError
from app.core.license.service import LicenseService

class FakeClient:
    def __init__(self): self.verify_calls = 0; self.activate_calls = 0; self.fail = None
    def public_key(self): return '00' * 32
    def activate(self, key, identifier, label=''):
        self.activate_calls += 1
        if self.fail: raise self.fail
        return {'status': 'already_activated'}
    def verify(self, key, identifier):
        self.verify_calls += 1
        if self.fail: raise self.fail
        return {'status': 'active', 'plan_name': 'Standard', 'features': {'max_cameras': '12'},
                'valid_until': (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(), 'grace_days': 15}

def test_verify_200_persists_features(tmp_path, monkeypatch):
    svc = LicenseService(client=FakeClient())
    svc.initialize()
    svc._persist_key('DSIGHT-TEST-KEY')       # test helper: encrypts + commits
    out = svc.verify_now()
    assert out['status'] in {'valid', 'grace'}
    assert svc.max_cameras() == 12

def test_network_error_keeps_cached_state():
    fake = FakeClient(); svc = LicenseService(client=fake); svc.initialize()
    svc._persist_key('DSIGHT-TEST-KEY'); svc.verify_now()
    fake.fail = KeygateNetworkError('down')
    out = svc.verify_now()
    assert out['status'] in {'valid', 'grace'} and svc.max_cameras() == 12

def test_second_verify_overwrites_features():
    fake = FakeClient(); svc = LicenseService(client=fake); svc.initialize()
    svc._persist_key('DSIGHT-TEST-KEY'); svc.verify_now()
    fake.verify = lambda key, identifier: {'status': 'active', 'plan_name': 'Standard',
        'features': {'max_cameras': '20'}, 'valid_until': None, 'grace_days': 15}
    svc.verify_now()
    assert svc.max_cameras() == 20  # last write wins, no partial state

def test_verify_404_suspended():
    fake = FakeClient(); svc = LicenseService(client=fake); svc.initialize()
    svc._persist_key('DSIGHT-TEST-KEY'); svc.verify_now()
    fake.fail = KeygateError(404, 'LICENSE_NOT_FOUND')
    # activate classifies as suspended
    svc.client.activate = lambda *a, **k: (_ for _ in ()).throw(KeygateError(403, 'LICENSE_SUSPENDED'))
    out = svc.verify_now()
    assert out['status'] == 'suspended'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_service_sync.py -v`
Expected: FAIL — methods missing.

- [ ] **Step 3: Implement activation/verify/background + lifespan wiring**

Implement `_persist_key` as a private helper used by `activate` (encrypt with `encrypt_secret`) and by tests. `_apply_verify_data` parses `valid_until` with `datetime.fromisoformat` (handle trailing `Z`), stores token and `token_exp` from `verify_license_token` (use `client.public_key()`; if pubkey missing/invalid, store token but set `last_error` and keep features). `verify_now` catches `KeygateError`/`KeygateNetworkError` exactly as the Interfaces block says; always `db.commit()` in a `try/finally` with rollback on error. `background.py` mirrors SEPay naming (`_task`, start guard, cancel+await). `main.py` lifespan additions inside the existing `lifespan` after SEPay start, and shutdown before pipeline stop.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_service_sync.py -v`
Expected: PASS (4 + 4 passed). Then `cd server && python -c "import app.main"` (import smoke; must not raise).

- [ ] **Step 5: Commit**

```bash
git add server/app/core/license/service.py server/app/core/license/background.py server/app/main.py server/app/tests/test_license_service_sync.py
git commit -m "feat(license): activate/verify Keygate license with offline cache and background check-in"
```

---

## Task 8: License API endpoints + admin guard + schemas

**Files:**
- Create: `server/app/schemas/license.py`
- Create: `server/app/api/v1/endpoints/license.py`
- Modify: `server/app/api/v1/router.py` (include `/license`)
- Modify: `server/app/api/deps.py` (add `require_admin`)
- Test: `server/app/tests/test_license_endpoints.py`

**Interfaces:**
- Produces `require_admin(current_user=Depends(get_current_user))` in `deps.py`: uses `app.utils.rbac.is_admin_user`; non-admin → `HTTPException(403, detail='Chỉ admin được thao tác license')`.
- Produces schemas: `LicenseStatusRead` (`status: str`, `plan_name: str | None`, `valid_until: datetime | None`, `days_left: int | None`, `grace_days: int`, `features: dict[str, Any]`, `enforcement_mode: Literal['off','warn','enforce']`, `instance_id: str`, `machine_code: str`, `license_key_hint: str | None`, `last_verified_at: datetime | None`, `last_error: str | None`), `LicenseActivateRequest` (`license_key: str`, `label: str = ''`), `LicenseEnforcementUpdate` (`mode: Literal['off','warn','enforce']`). `machine_code` = `license_service.machine_code()`.
- Produces endpoints on router `/license`: `GET /status` (auth via `get_current_user`), `GET /` (admin), `POST /activate` (admin; calls `license_service.activate`; Keygate errors → 400 with code/detail), `POST /refresh` (admin; `verify_now`), `PUT /enforcement` (admin; `set_enforcement_mode`, returns mode).
- `license_key_hint`: use `license_service.license_key_hint()` (last 4 chars masked, `'****' + key[-4:]`) — never the full key.

- [ ] **Step 1: Write the failing test** (TestClient + dependency overrides, fake service state)

```python
# server/app/tests/test_license_endpoints.py
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.api.deps import get_current_user
from app.main import app
from app.core.license import service as service_module

client = TestClient(app)

def _user(admin=False):
    return SimpleNamespace(id=1, username='admin' if admin else 'op', is_active=True,
                           role=SimpleNamespace(role_name='admin' if admin else 'operator', permissions={'all': True} if admin else {}))

def test_status_requires_auth():
    assert client.get('/api/v1/license/status').status_code == 401

def test_status_returns_snapshot(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user()
    monkeypatch.setattr(service_module.license_service, 'snapshot', lambda: SimpleNamespace(
        instance_id='inst-1', status='valid', plan_name='Standard', valid_until=None, grace_days=15,
        features={'max_cameras': 12}, enforcement_mode='warn', last_verified_at=None, last_error=None))
    monkeypatch.setattr(service_module.license_service, 'days_left', lambda: 365)
    monkeypatch.setattr(service_module.license_service, 'license_key_hint', lambda: '****1234', raising=False)
    body = client.get('/api/v1/license/status').json()
    assert body['status'] == 'valid' and body['features'] == {'max_cameras': 12}
    app.dependency_overrides.clear()

def test_activate_forbidden_for_non_admin(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: _user(admin=False)
    r = client.post('/api/v1/license/activate', json={'license_key': 'K'})
    assert r.status_code == 403
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_endpoints.py -v`
Expected: FAIL — 404 route not found / import errors.

- [ ] **Step 3: Implement schemas, endpoints, router include, `require_admin`**

Endpoint functions are thin: read `license_service`, build response models; catch `KeygateError` → `HTTPException(400, detail=f'{code}: {message}')`, `KeygateNetworkError` → `HTTPException(503, detail='Không kết nối được license server')`. `POST /refresh` returns status payload. `PUT /enforcement` returns `{'mode': mode}`. Add `license.router` to `router.py` with `prefix='/license', tags=['license']`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_endpoints.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/schemas/license.py server/app/api/v1/endpoints/license.py server/app/api/v1/router.py server/app/api/deps.py server/app/tests/test_license_endpoints.py
git commit -m "feat(license): add license status/activate/refresh/enforcement API"
```

---

## Task 9: Camera quota enforcement

**Files:**
- Create: `server/app/core/license/enforcement.py`
- Modify: `server/app/api/v1/endpoints/cameras.py` (`create_camera` only)
- Test: `server/app/tests/test_license_camera_quota.py`

**Interfaces:**
- Produces `enforcement.py`: `class CameraLimitExceeded(Exception)` with `limit: int`, `current: int`; `def check_camera_quota(db: Session) -> None` — reads `license_service.max_cameras()` and `license_service.enforcement_mode()`; `current = camera_repo.count_all(db)`; if `current < limit` return; if mode `enforce` → raise `CameraLimitExceeded(limit, current)`; if mode `warn` → `logger.warning('license camera quota exceeded: %s/%s (warn mode)', current, limit)` and return; mode `off` → return. Also `def camera_quota_snapshot(db) -> tuple[int, int]` returning `(current, limit)` for the UI.
- `create_camera` calls `check_camera_quota(db)` before constructing the model; catches `CameraLimitExceeded` → `HTTPException(403, detail=f'Đã đạt giới hạn {limit} camera của license (hiện có {current}). Liên hệ DTG để nâng giới hạn.')`.

- [ ] **Step 1: Write the failing test**

```python
# server/app/tests/test_license_camera_quota.py
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.api.deps import get_current_user
from app.main import app
from app.core.license import service as service_module

client = TestClient(app)

def _override(monkeypatch, limit=1, mode='enforce', current=1):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, username='admin', is_active=True, role=SimpleNamespace(role_name='admin', permissions={'all': True}))
    monkeypatch.setattr(service_module.license_service, 'max_cameras', lambda: limit)
    monkeypatch.setattr(service_module.license_service, 'enforcement_mode', lambda: mode)
    from app.core.license import enforcement
    monkeypatch.setattr(enforcement.camera_repo, 'count_all', lambda db: current)

def test_create_camera_blocked_at_limit(monkeypatch):
    _override(monkeypatch, limit=1, mode='enforce')
    r = client.post('/api/v1/cameras/', json={'camera_name': 'quota-test', 'rtsp_url': 'rtsp://quota-test/1', 'is_active': False})
    assert r.status_code == 403 and 'giới hạn' in r.json()['detail']
    app.dependency_overrides.clear()

def test_create_camera_allowed_in_warn(monkeypatch):
    _override(monkeypatch, limit=0, mode='warn')
    r = client.post('/api/v1/cameras/', json={'camera_name': 'quota-warn', 'rtsp_url': 'rtsp://quota-warn/1', 'is_active': False})
    assert r.status_code == 201
    client.delete(f"/api/v1/cameras/{r.json()['id']}")
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_camera_quota.py -v`
Expected: FAIL — 201 instead of 403 (or import errors).

- [ ] **Step 3: Implement enforcement + endpoint hook**

`enforcement.py` imports `camera_repo`, `license_service`, `logging`. `create_camera` catches `CameraLimitExceeded` and raises the HTTPException **before** `db.add`. Do not touch `update_camera`/`delete_camera` (row count semantics; deleting frees a slot).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_camera_quota.py -v`
Expected: PASS (2 passed). Clean up any leftover test camera rows (the warn test deletes its row; the blocked test creates none).

- [ ] **Step 5: Commit**

```bash
git add server/app/core/license/enforcement.py server/app/api/v1/endpoints/cameras.py server/app/tests/test_license_camera_quota.py
git commit -m "feat(license): enforce max_cameras quota on camera creation"
```

---

## Task 10: License/module dependencies + pipeline start gate

**Files:**
- Modify: `server/app/core/license/enforcement.py` (add `enforce_pipeline_start`)
- Modify: `server/app/api/deps.py` (add `require_license`, `require_module`)
- Modify: `server/app/api/v1/endpoints/pipeline.py` (`start_pipeline` only)
- Test: `server/app/tests/test_license_pipeline_gate.py`

**Interfaces:**
- `enforcement.py`: `def enforce_pipeline_start() -> None` — if `license_service.should_block_new_behavior()` → `HTTPException(403, detail='License không hợp lệ hoặc đã hết hạn. Không thể bắt đầu pipeline mới; pipeline đang chạy vẫn tiếp tục.')`.
- `deps.py`: `def require_license_state()` (no auth dependency) — same check as above (403 detail 'License không hợp lệ...'); `def require_module(module_key: str)` factory returning a dependency that raises `HTTPException(403, detail=f'Module {module_key} chưa được cấp trong license')` when `feature_bool(license_service.features(), module_key)` is False. (Not wired to any router yet — the extension point for future packages.)
- `pipeline.py`: `start_pipeline` calls `enforce_pipeline_start()` after the `is_running` early-return and before `start_group`; no other pipeline endpoints change.

- [ ] **Step 1: Write the failing test**

```python
# server/app/tests/test_license_pipeline_gate.py
import pytest
from fastapi import HTTPException
from app.core.license import enforcement
from app.core.license import service as service_module

def test_pipeline_blocked_when_enforced_and_invalid(monkeypatch):
    monkeypatch.setattr(service_module.license_service, 'should_block_new_behavior', lambda: True)
    with pytest.raises(HTTPException) as ei:
        enforcement.enforce_pipeline_start()
    assert ei.value.status_code == 403

def test_pipeline_allowed_when_usable(monkeypatch):
    monkeypatch.setattr(service_module.license_service, 'should_block_new_behavior', lambda: False)
    enforcement.enforce_pipeline_start()  # must not raise

def test_require_module_blocks_missing_feature(monkeypatch):
    from app.api.deps import require_module
    monkeypatch.setattr(service_module.license_service, 'features', lambda: {})
    dep = require_module('module_ai_lab')
    with pytest.raises(HTTPException) as ei:
        dep()
    assert ei.value.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && python -m pytest app/tests/test_license_pipeline_gate.py -v`
Expected: FAIL — functions missing.

- [ ] **Step 3: Implement**

Add the functions per Interfaces; import `feature_bool` from `features.py` in `deps.py`. Wire the pipeline call. Keep `stop`, status, logs, WS untouched.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && python -m pytest app/tests/test_license_pipeline_gate.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add server/app/core/license/enforcement.py server/app/api/deps.py server/app/api/v1/endpoints/pipeline.py server/app/tests/test_license_pipeline_gate.py
git commit -m "feat(license): add license/module dependencies and pipeline start gate"
```

---

## Task 11: Frontend license types, API client, store

**Files:**
- Create: `client/src/features/license/types/index.ts`
- Create: `client/src/features/license/services/licenseApi.ts`
- Create: `client/src/features/license/store/licenseStore.ts`
- Create: `client/src/features/license/index.ts`
- Verification: `cd client && npm run build` and `npm run lint`

**Interfaces:**
- Types: `LicenseEnforcementMode = 'off' | 'warn' | 'enforce'`; `LicenseStatusRead` (mirrors `LicenseStatusRead` schema: `status`, `plan_name`, `valid_until`, `days_left`, `grace_days`, `features: Record<string, unknown>`, `enforcement_mode`, `instance_id`, `machine_code`, `license_key_hint`, `last_verified_at`, `last_error`); `LicenseActivateRequest`.
- API: `licenseApi.getStatus(): Promise<LicenseStatusRead>` (`GET /license/status`), `activate(data): Promise<LicenseStatusRead>` (`POST /license/activate`), `refresh(): Promise<LicenseStatusRead>` (`POST /license/refresh`). (Enforcement is not a FE action — ops uses the admin API.)
- Store (Zustand): `{ status: LicenseStatusRead | null, isLoading: boolean, error: string | null, fetchStatus: () => Promise<void>, activate: (key: string) => Promise<void>, refresh: () => Promise<void> }`; `fetchStatus` swallows errors into `error` (never throws), so the app shell cannot crash; `activate` throws on failure so the activation screen can show the message.

- [ ] **Step 1: Write the types/api/store** (no client test runner exists; the verification is type-check + lint)

- [ ] **Step 2: Verify build fails or passes**

Run: `cd client && npm run build`
Expected: PASS (type-check included). If it fails on missing imports, fix them in this task.

- [ ] **Step 3: Run lint**

Run: `cd client && npm run lint`
Expected: PASS with no new errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/features/license
git commit -m "feat(license): add frontend license API client and store"
```

---

## Task 12: First-run activation screen (only license UI)

**Files:**
- Create: `client/src/features/license/views/LicenseActivationView.tsx`
- Modify: `client/src/features/license/index.ts` (export the view)
- Modify: `client/src/layouts/MainLayout.tsx` (fetch status on mount; render the activation view instead of `<Outlet />` when `unlicensed`)
- Verification: `cd client && npm run build && npm run lint`

**Interfaces:**
- `MainLayout`: on mount call `useLicenseStore.getState().fetchStatus()` once; read `status`, `isLoading` from the store. When `status?.status === 'unlicensed'`: render `<LicenseActivationView />` in place of the routed content (`<Outlet />`) while keeping the shell/header. When status is `null` or the fetch failed, render the app normally (warn mode — never trap the user).
- `LicenseActivationView`: centered card (app style) with title "Kích hoạt DSight", explanation that the key is issued by DTG, machine code (`status.machine_code`) shown with a copy button, a key input (`type="password"`-like masked text is fine), and a "Kích hoạt" button. `isAdminUser(user)` from `auth/rbac` decides: admin sees the form; non-admin sees "Chưa kích hoạt license — liên hệ quản trị viên" and no form. On submit call `activate(key)`; on success the store status becomes non-unlicensed and the app renders; on failure show `error` under the input. No license info page, no menu entry, no banner.

- [ ] **Step 1: Implement activation view + MainLayout bootstrap**

- [ ] **Step 2: Verify build**

Run: `cd client && npm run build`
Expected: PASS.

- [ ] **Step 3: Verify lint**

Run: `cd client && npm run lint`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add client/src/features/license client/src/layouts/MainLayout.tsx
git commit -m "feat(license): add first-run activation screen"
```

---

## Task 13: Camera quota UX + near-limit warnings

**Files:**
- Modify: `client/src/features/port/components/PortCamerasSection.tsx`
- Modify: `client/src/features/port/views/PortView.tsx`
- Verification: `cd client && npm run build && npm run lint`

**Interfaces:**
- `PortCamerasSection` gains props `licenseLimit: number`, `licenseEnforced: boolean`, `cameraError: string | null`. Render a **yellow inline warning** above the camera grid when `licenseLimit > 0 && licenseLimit - cameras.length <= 2` (e.g. "Sắp đạt giới hạn camera: 10/12 — còn 2 slot. Liên hệ DTG để nâng giới hạn."). The "Thêm Camera" button gets `disabled={licenseEnforced && cameras.length >= licenseLimit}` with a `title` explaining the limit; render `cameraError` as a red inline banner above the grid.
- `PortView` computes `licenseLimit` (`Number(useLicenseStore(s => s.status?.features?.max_cameras ?? 0))`) and `licenseEnforced` (`status?.enforcement_mode === 'enforce'`), keeps `cameraError` state, sets it in `onCameraSubmit` catch (`err.message`), clears it on success/modal close, and passes the props down. Warn mode never disables the button (server logs only) but still shows the near-limit warning.

- [ ] **Step 1: Implement props + warning + state**

- [ ] **Step 2: Verify build**

Run: `cd client && npm run build`
Expected: PASS.

- [ ] **Step 3: Verify lint**

Run: `cd client && npm run lint`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add client/src/features/port/components/PortCamerasSection.tsx client/src/features/port/views/PortView.tsx
git commit -m "feat(license): warn near camera quota and show limit errors"
```

---

## Task 14: Ops runbook, env docs, staging end-to-end verification

**Files:**
- Create: `docs/license-keygate-runbook.md`
- Create: `server/scripts/license_probe.py`
- Create: `scripts/install_license_identity.sh`
- Modify: `server/docker-compose.yml` (app service: add read-only host mounts for the fingerprint)
- Modify: `server/.env.example` (only if Task 1 didn't fully document the vars)
- Verification: run probe against staging (network) + full new-test suite + client build/lint

**Interfaces:**
- `server/scripts/license_probe.py` (dev/ops tool, not imported by the app): reads env `LICENSE_PROBE_URL`, `LICENSE_PROBE_KEY`, `LICENSE_PROBE_IDENTIFIER` (default `probe-<uuid>`); constructs `KeygateClient` + calls `activate`, `verify`, `entitlements`; prints status/plan/valid_until/features and verifies the token with `verify_license_token` + `client.public_key()`; exits non-zero on failure. Never prints the key.
- Runbook sections: prereqs (outbound HTTPS to `license.dtgsoft.vn`, no offline activation), issue **trial / standard / lifetime** license (curl with `product_id`/`plan_id` per environment, `valid_until` for trial/standard, **omit `valid_until` for lifetime**, `external_customer_id`, notes), attach per-customer camera addon (`camera-<code>`, `max_cameras=N`, attach/detach), renew standard (`valid-until`), change camera count (PUT addon value), trial→paid conversion (`change-plan` + `valid-until`), reinstall/hardware replacement (machine code changes → `DELETE /admin/activations/{id}` then re-enter key on the first-run screen), suspend/reinstate/revoke, rotate key, **enforcement mode switch via `PUT /api/v1/license/enforcement` (no UI)**, troubleshooting (verify 404 meanings, network errors, clock), security (admin key storage, no key in logs/env).

- [ ] **Step 1: Write runbook + probe script + installer + compose mounts**

`server/docker-compose.yml` app service volumes add:
```yaml
      - /etc/machine-id:/host/etc/machine-id:ro
      - /sys/class/dmi/id:/host/sys/class/dmi/id:ro
```
`scripts/install_license_identity.sh` (run on the customer host, not in the container): reads the same sources, prints the computed machine code (same algorithm as `machine.py`), checks the compose mounts exist, and warns if `product_uuid`/`board_serial` are unreadable (falls back to machine-id only). It does not write secrets. Runbook documents: reinstall on same host = same code; hardware replacement = new code → ops deletes old activation.

- [ ] **Step 2: Run the new backend test suite**

Run: `cd server && python -m pytest app/tests/test_license_config_crypto.py app/tests/test_license_features.py app/tests/test_license_token.py app/tests/test_license_keygate_client.py app/tests/test_license_state_repository.py app/tests/test_license_service_state.py app/tests/test_license_service_sync.py app/tests/test_license_endpoints.py app/tests/test_license_camera_quota.py app/tests/test_license_pipeline_gate.py -v`
Expected: all PASS.

- [ ] **Step 3: Run existing suite for regressions**

Run: `cd server && python -m pytest app/tests -q`
Expected: PASS (same as before; if pre-existing failures, note them and prove they are unrelated).

- [ ] **Step 4: Staging end-to-end probe** (only when `LICENSE_PROBE_URL`/`LICENSE_PROBE_KEY` are provided; otherwise skip and record "not run")

```bash
# 1) create a temp trial license on staging (admin key from env; do not commit keys)
#    POST https://stg-license.dtgsoft.vn/api/v1/admin/licenses {product_id, plan_id(trial), email, notes:"probe"}
# 2) run:
cd server && LICENSE_PROBE_URL=https://stg-license.dtgsoft.vn LICENSE_PROBE_KEY=<key> \
  python scripts/license_probe.py
# expected: status active/trialing, features {"max_cameras":"2"}, token verifies
# 3) cleanup: DELETE the probe activation (if any) / revoke the probe license via admin API
```

- [ ] **Step 5: Client verification**

Run: `cd client && npm run build && npm run lint`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/license-keygate-runbook.md server/scripts/license_probe.py server/.env.example
git commit -m "docs(license): add Keygate ops runbook and staging license probe"
```

---

## Execution notes (for the implementing session)

- Create an isolated worktree via `superpowers:using-git-worktrees` before Task 1. The main working tree has unrelated uncommitted changes (`server/requirements.txt`, `server/.dockerignore`, `server/docker-compose.yml`) — do not carry them into the feature branch. Copy these untracked files into the worktree: `docs/superpowers/specs/2026-11-09-dsight-license-keygate-design.md`, this plan, and `server/.env` (gitignored; needed for DB tests). `server/models/` (weights) is not needed for the license tests.
- Python env for tests: conda env `bason-dock` (`~/miniconda3/envs/bason-dock/bin/python -m pytest ...`). PostgreSQL is already running (`server-db-1`, healthy) and tests use the real dev DB with transaction rollback patterns.
- After backend changes, restart the app container so lifespan loads the new modules: `cd server && docker compose restart app` (or `docker compose up -d app`); verify `curl -s http://127.0.0.1:8080/health` and `curl -s http://127.0.0.1:8080/api/v1/license/status` (401 without auth is expected).
- The hardware-fingerprint mounts (`/etc/machine-id`, `/sys/class/dmi/id`) only exist in the compose file after Task 14; until then `resolve_machine_code()` falls back to the DB UUID (dev behavior, warning logged). On the dev machine verify `python -c "from app.core.license.machine import resolve_machine_code; print(resolve_machine_code())"` prints `DSIGHT-…` once the mounts exist.
- Keygate staging admin key is provided out-of-band; never commit it. Production changes are out of scope for this plan (Phase 1 already done; `lifetime` plan already created on both environments).
- The only new UI is the first-run activation screen + inline quota warnings; do **not** add a license page, menu entry or global banner.
- Keep commits small and conventional (`feat(license): ...`), one per task.

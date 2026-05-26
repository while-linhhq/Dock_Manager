# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick start

```bash
# 1) Start dependencies (PostgreSQL + MinIO)
cd server
docker compose up -d db minio minio-init

# 2) Run server
python run_dev.py                    # http://127.0.0.1:8000, Swagger at /docs

# 3) Run client
cd client
npm install && npm run dev           # typically http://localhost:5173
```

Full Docker: `cd server && docker compose --profile docker-app up --build` (app at `:8080`).

## Tech stack

- **Client**: React 19 + TypeScript + Vite, React Router, TanStack Query, Zustand, Tailwind CSS 4, shadcn/ui patterns
- **Server**: Python + FastAPI + Uvicorn, SQLAlchemy (no ORM migrations — uses `init_db.py` + `schema_patches.py`), MinIO client
- **Infra (Docker)**: PostgreSQL 16, MinIO (S3-compatible)
- **AI/CV**: Ultralytics YOLO, PaddleOCR, ONNX Runtime, OpenCV
- **Auth**: JWT (python-jose) — access/refresh tokens, auto-refresh in client

## Server architecture (`server/app/`)

Layered FastAPI app. Data flow: **endpoint → service → repository → DB**.

```
app/
├── api/v1/
│   ├── router.py          # All route registration
│   └── endpoints/         # Thin handlers — validate input, call service, return response
├── services/              # Business logic, orchestration (pipeline_service.py is the AI core)
├── repositories/          # Data access — SQLAlchemy queries ONLY here
├── models/                # SQLAlchemy ORM models
├── schemas/               # Pydantic request/response schemas
├── core/config.py         # All settings via pydantic-settings, loaded from server/.env
├── db/
│   ├── session.py         # Engine, SessionLocal, get_db dependency, Base
│   ├── init_db.py         # Initial schema creation (not Alembic — this is the migration path)
│   └── schema_patches.py  # Runtime schema patches applied at startup via lifespan
├── middlewares/           # Custom middleware
└── main.py                # App factory, lifespan, CORS, audit middleware
```

### Key conventions
- **Absolute imports** from `app.*` always (never relative)
- Endpoints return raw dicts/list — FastAPI serializes via response_model schemas
- `app.core.config.settings` is the global config singleton
- DB sessions: use `SessionLocal()` directly in middleware/background tasks; use `get_db()` dependency in endpoints
- Audit middleware in `main.py` intercepts all mutating `/api/v1/*` calls and writes to `audit_logs`
- Schema patches (`apply_schema_patches()`) run at startup via lifespan — adds missing columns/tables without full migrations

### API routes (`/api/v1/`)
Auth, users, roles, vessels, vessel-types, detections, orders, fee-configs, invoices, cameras, camera-groups, port-configs, port-logs, dashboard, exports, audit-logs, pipeline, sepay.

### AI pipeline (`services/pipeline_service.py`)
Core detection pipeline: reads RTSP camera streams, runs YOLO detection + PaddleOCR, tracks ships (IoU + state machine), records video, uploads to MinIO. Managed as a singleton with `start()/stop()`. Re-ID and seam-anchor identity locking for cross-camera tracking.

### Key services
- `pipeline_service.py` — Main AI detection pipeline (largest file, ~69K)
- `sepay_*.py` — Bank transfer QR payment sync (background task in lifespan)
- `berth_limit_service.py` — Per-ship berth capacity limits
- `dashboard_summary_service.py` — Aggregated dashboard stats
- `detection_invoice_service.py` — Auto-generate invoices from detections

## Client architecture (`client/src/`)

Feature-based SPA. Each feature in `src/features/<name>/` must export only via `index.ts`.

```
src/
├── features/<name>/
│   ├── components/    # Feature-specific UI
│   ├── hooks/         # Feature-specific hooks
│   ├── services/      # API calls (e.g., authApi.ts)
│   ├── store/         # Zustand slices
│   ├── types/         # Feature-specific types
│   ├── views/         # Screen-level compositions
│   └── index.ts       # Public API
├── components/        # Shared UI components
├── layouts/           # MainLayout, AuthLayout
├── pages/             # Route-level assemblers (page → feature view)
├── router/            # paths.ts + index.tsx (createBrowserRouter)
├── services/          # httpClient.ts, authStorage.ts, jwt.ts
├── store/             # Global Zustand stores
├── hooks/             # Shared hooks
└── utils/             # cn(), rbac.ts, etc.
```

### Key conventions
- **Routes**: All paths in `router/paths.ts` (PATHS constant) — never hard-code URLs
- **Auth**: `ProtectedRoute` + `RequireMenuAccess` wrappers in router. JWT auto-refresh in `httpClient.ts` (proactive refresh 2min before expiry, retry on 401)
- **RBAC**: `hasMenuAccess(user, menu)` in `utils/rbac.ts` controls sidebar + route visibility
- **Zustand** for state, **TanStack Query** for server state
- Name files/dirs: `kebab-case`, components: `PascalCase`, hooks: `useCamelCase`
- 2-space indent, single quotes, semicolons

### Features
auth, backup, camera-fusion, dashboard, orders, port, revenue, seam-anchor, statistics, users, vessels

## Environment variables

All in `server/.env` (loaded by pydantic-settings + docker-compose). Key groups:
- **PostgreSQL**: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT, DATABASE_URL
- **Auth**: SECRET_KEY, ALGORITHM (HS256), ACCESS_TOKEN_EXPIRE_MINUTES
- **MinIO**: MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET, MINIO_SECURE, MINIO_MEDIA_PREFIX
- **Model/pipeline**: MODEL_PATH, DEVICE, CONF, RESIZE_SCALE, OCR_INTERVAL_FRAMES, RECORD_*, TRACK_*, SEAM_*, ANCHOR_*
- **SEPay**: SEPAY_API_TOKEN, SEPAY_SYNC_ENABLED
- **Logging**: LOG_LEVEL

## Commands

```bash
# Client
cd client
npm run dev          # Start Vite dev server
npm run build        # Type-check + production build
npm run lint         # ESLint

# Server
cd server
python run_dev.py           # Dev server (Uvicorn, reload off by default)
python run_prod.py          # Production server
UVICORN_RELOAD=1 python run_dev.py  # Hot-reload (may conflict with GPU pipeline)
```

## Git workflow

Conventional Commits: `feat(scope):`, `fix(scope):`, `chore:`, `docs:`, etc. Branch naming: `feature/*`, `fix/*`, `hotfix/*`. No direct commits to `main`.

## Important notes

- **No Alembic migrations**: Schema managed via `db/init_db.py` (initial) + `db/schema_patches.py` (runtime patches). Manual SQL in `db/sqlCommand/` and `db/add_invoice_deleted_at.sql`.
- **GPU pipeline**: Hot-reload (`UVICORN_RELOAD=1`) + YOLO/Paddle often freezes — leave reload off when testing AI features.
- **Conda env**: The cursor rules reference `demo_core` conda environment for the backend.
- **MinIO ports**: API on `:9100`, Console UI on `:9101`.
- **Tests**: Server tests in `server/app/tests/` (pytest). No client tests currently configured.

# Refactor Mã Tàu + Cấu Hình Giá — Phân Loại Cứng (Spot / Monthly / Unclassified)

> **For Hermes:** thực thi task-by-task. Backend env `bason-dock`. Client `pnpm run dev`. Backend dev = foreground `python run_dev.py` (user tự restart sau khi sửa code).

**Goal:** Phân loại cứng mọi mã tàu thành 1 trong 3 nhóm — `spot` (tàu lẻ), `monthly` (tàu tháng), `unclassified` (từ nhận diện, chưa cấu hình). Tách luồng tính phí theo nhóm: tàu lẻ = phí per-tàu, tàu tháng = phí per-loại-tàu.

**Architecture:**
- Thêm cột cứng `vessels.classification` thay cho việc suy diễn từ `vessel_type.type_name`.
- `vessel_type_id` giờ CHỈ có nghĩa cho tàu tháng (nhóm định giá). Tàu lẻ không dùng loại.
- Một hàm resolve phí trung tâm `resolve_billable_fees(db, vessel)` thay 3 chỗ gọi `get_by_vessel` rải rác.
- UI Vessels: 5 tab (Tàu Lẻ / Tàu Tháng / Chưa Phân Loại / Loại Tàu / Nhận Diện). UI Revenue Cấu Hình Phí: gắn theo `vessel_type_id` (tàu tháng).

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL (schema_patches, no Alembic); React 19 + TS + Vite + Zustand + TanStack Query + RHF/zod.

---

## Hiện trạng đã xác minh (production data)

| Nhóm | Số liệu |
|---|---|
| Tổng vessels | 70 |
| type 343 `Tàu lẻ` | 15 |
| type 344 `Tàu tháng` | 13 |
| type 380 `Les Rives` | 1 (SG-5893) |
| type NULL | 41 |
| fee_configs | 2 — **cả 2 gắn `vessel_type_id`, 0 gắn `vessel_id`** |
| fee 25 | `Tàu vãn lai - Tàu lẻ`, type 343, 1.000.000 ₫/giờ, active |
| fee 26 | `Tàu tháng chung`, type 344, 50.000.000 ₫/tháng, active |
| detections có vessel_id | 628 · AI invoices (chưa xóa): 270 |

**Hệ quả:** `detection_invoice_service` gọi `fee_config_repo.get_by_vessel()` → luôn `[]` → auto-invoice không resolve phí nào từ khi migrate dở sang per-vessel. Refactor này sửa gốc.

---

## Ánh xạ migration (theo nghiệp vụ cũ user xác nhận)

Suy `classification` từ `vessel_type.type_name` hiện có (normalize lower, bỏ dấu cách):
- chứa `tàu lẻ` (type 343) → **spot**
- chứa `tàu tháng` (type 344) → **monthly**
- type khác không rỗng (vd `Les Rives` 380) → **monthly** (loại tàu = nhóm định giá tàu tháng theo model mới)
- type NULL (41 tàu) → **unclassified**

**Xử lý phí theo model mới:**
- **spot (15 tàu, type 343):** model mới = phí per-tàu. Cần backfill: copy fee 25 (1.000.000 ₫/giờ) thành 1 fee per-vessel cho từng tàu trong 15 tàu spot → giữ liên tục billing. Sau đó clear `vessel_type_id` của tàu spot (spot không dùng loại). Fee 25 (type-based) set `is_active=False` (giữ rollback).
- **monthly (14 tàu: 13 type 344 + 1 type 380):** giữ nguyên `vessel_type_id`. fee 26 giữ cho type 344. Type 380 `Les Rives` chưa có fee → user tự cấu hình sau qua UI (tàu monthly không phí → unclassified-billing = 0, không lỗi).
- **unclassified (41 tàu):** không phí, không auto-invoice.

**OPEN DECISION cần chốt trước Task 20 (migration):**
1. Les Rives (SG-5893) → `monthly` hay `unclassified`? (plan mặc định: monthly)
2. Backfill fee 25 → per-vessel cho 15 tàu spot: làm hay để user tự nhập lại? (plan mặc định: backfill tự động)

---

## PHASE 0 — Schema

### Task 1: Thêm cột `classification` vào model Vessel

**Files:**
- Modify: `server/app/models/vessel.py`

**Code** — thêm sau `vessel_type_id`:
```python
    # Phân loại cứng: 'spot' (tàu lẻ) | 'monthly' (tàu tháng) | 'unclassified' (nhận diện, chưa cấu hình)
    classification = Column(String(20), nullable=False, server_default='unclassified', index=True)
```

### Task 2: Schema patch runtime cho cột mới

**Files:**
- Modify: `server/app/db/schema_patches.py`

Thêm patch idempotent (theo pattern file này — kiểm tra cột tồn tại chưa rồi `ALTER TABLE`):
```python
def _patch_vessels_classification(conn):
    conn.execute(text("""
        ALTER TABLE vessels
        ADD COLUMN IF NOT EXISTS classification VARCHAR(20) NOT NULL DEFAULT 'unclassified'
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vessels_classification ON vessels (classification)"))
```
Đăng ký patch vào `apply_schema_patches()`. **Đọc file trước** để khớp đúng cách nó mở connection/transaction.

**Verify:** restart backend, `\d vessels` thấy cột + index.

---

## PHASE 1 — Backend model / schema / repo

### Task 3: Pydantic schema Vessel — thêm classification

**Files:**
- Modify: `server/app/schemas/vessel.py`

- `VesselBase`: thêm `classification: Literal['spot','monthly','unclassified'] = 'unclassified'`
- `VesselCreate`: nhận `classification` (bắt buộc khi tạo từ tab — mặc định unclassified nếu thiếu).
- `VesselUpdate`: thêm `classification: Optional[Literal[...]] = None`.
- `VesselRead`: đã kế thừa từ base → tự có.

### Task 4: FeeConfig schema — validate theo scope

**Files:**
- Modify: `server/app/schemas/fee.py`

- `FeeConfigCreate`: thêm model_validator — chính xác MỘT trong `vessel_id` / `vessel_type_id` được set (không cả hai, không rỗng cả hai). `vessel_id` = phí tàu lẻ; `vessel_type_id` = phí tàu tháng.
- `FeeConfigUpdate`: cho phép đổi `vessel_type_id` (hiện chỉ có `vessel_id`).

### Task 5: fee_config_repo — bỏ deprecated note, giữ cả 2 getter

**Files:**
- Modify: `server/app/repositories/fee_config_repository.py`

`get_by_vessel_type` bỏ trạng thái deprecated (giờ là đường chính cho monthly). Thêm `get_by_vessel_type(active_only=True)` param cho nhất quán. `create/update` đã generic — OK.

---

## PHASE 2 — Fee resolution trung tâm

### Task 6: Hàm `resolve_billable_fees`

**Files:**
- Create: `server/app/services/fee_resolution_service.py`
- Test: `server/app/tests/test_fee_resolution.py`

**Step 1 — test (RED):**
```python
def test_spot_uses_per_vessel(db, ...):
    # vessel.classification='spot' → get_by_vessel
def test_monthly_uses_per_type(db, ...):
    # vessel.classification='monthly' → get_by_vessel_type(vessel.vessel_type_id)
def test_unclassified_returns_empty(db, ...):
    # → []
def test_monthly_without_type_returns_empty(db, ...):
```

**Step 2 — impl:**
```python
from sqlalchemy.orm import Session
from app.repositories.fee_config_repository import fee_config_repo

def resolve_billable_fees(db: Session, vessel) -> list:
    """Trả fee active theo phân loại tàu. Nguồn phí duy nhất cho tính hóa đơn."""
    c = getattr(vessel, 'classification', 'unclassified')
    if c == 'spot':
        return fee_config_repo.get_by_vessel(db, vessel.id, active_only=True)
    if c == 'monthly':
        if not vessel.vessel_type_id:
            return []
        return fee_config_repo.get_by_vessel_type(db, vessel.vessel_type_id)
    return []
```

**Step 3:** `pytest server/app/tests/test_fee_resolution.py -v` → PASS.

### Task 7: Thay 3 call site sang hàm trung tâm

**Files:**
- Modify: `server/app/services/detection_invoice_service.py` (dòng 238 `ensure_`, dòng 329 `recompute_`)
- Modify: `server/app/services/ship_invoice_backfill_service.py` (`vessel_has_billable_fees` dòng 30-32)
- Modify: `server/app/services/vessel_read_service.py` (dòng 18)

Thay `fee_config_repo.get_by_vessel(db, vessel.id)` → `resolve_billable_fees(db, vessel)`. Ở `vessel_read_service` cần vessel object (đã có).

**Verify:** `pytest server/app/tests -v`.

### Task 8: backfill service — cập nhật `vessel_type_has_billable_fees` cho monthly

**Files:**
- Modify: `server/app/services/ship_invoice_backfill_service.py`

`vessel_ready_for_ai_invoice` giờ dùng `resolve_billable_fees`. `run_vessel_type_backfill_task` giữ cho monthly (đổi type-fee → backfill mọi tàu monthly của type đó). Endpoint fee update: khi sửa fee gắn `vessel_type_id`, trigger backfill tất cả tàu monthly thuộc type.

---

## PHASE 3 — Backend endpoints

### Task 9: vessels endpoint — set classification khi create

**Files:**
- Modify: `server/app/api/v1/endpoints/vessels.py`

- `create_vessel`: nhận `classification` từ payload (tab quyết định). Nếu `spot` → ép `vessel_type_id=None`. Nếu `monthly` → cho phép `vessel_type_id`.
- `update_vessel`: cho đổi classification. Đổi sang spot → clear type; sang monthly → giữ/nhận type. Đổi classification hoặc type → trigger backfill.
- Thêm query filter `GET /vessels/?classification=spot|monthly|unclassified` (repo hỗ trợ).

### Task 10: vessel_repo — filter theo classification

**Files:**
- Modify: `server/app/repositories/vessel_repository.py`

`get_all(..., classification: Optional[str] = None)` → thêm `.filter(Vessel.classification == classification)` khi set.

### Task 11: fee_configs endpoint — list theo type

**Files:**
- Modify: `server/app/api/v1/endpoints/fee_configs.py`

`list_fee_configs` đã hỗ trợ `vessel_type_id`. Đảm bảo create/update với `vessel_type_id` trigger backfill mọi tàu monthly của type (dùng `run_vessel_type_backfill_task`).

---

## PHASE 4 — Client types + API

### Task 12: api.types.ts + vesselsApi

**Files:**
- Modify: `client/src/types/api.types.ts` — `VesselRead` thêm `classification: 'spot'|'monthly'|'unclassified'`.
- Modify: `client/src/features/vessels/services/vesselsApi.ts` — `VesselCreate` thêm `classification`; `getVessels(classification?)`.

### Task 13: revenueApi fee type

**Files:**
- Modify: `client/src/features/revenue/services/revenueApi.ts`
- `getFeeConfigsByVesselType(vesselTypeId)` mới. `FeeConfigCreate` giữ cả `vessel_id` + `vessel_type_id`.

---

## PHASE 5 — Client Vessels tabs

### Task 14: VesselsMainTabs — 5 tab

**Files:**
- Modify: `client/src/features/vessels/components/VesselsMainTabs.tsx`
- `VesselsMainTab = 'spot' | 'monthly' | 'unclassified' | 'types' | 'recognition'`
- Nhãn VI: `Tàu Lẻ` / `Tàu Tháng` / `Chưa Phân Loại` / `Loại Tàu` / `Cấu Hình Nhận Diện`.

### Task 15: VesselsView — routing tab + filter classification + auto-set khi tạo

**Files:**
- Modify: `client/src/features/vessels/views/VesselsView.tsx`
- `parseVesselsTab` cập nhật ids. Fetch vessels filter theo tab (`spot`/`monthly`/`unclassified`).
- Nút "Thêm tàu" trong tab spot/monthly → set `classification` tương ứng vào form mặc định.
- Tab spot: mỗi row có action mở phí per-tàu (`VesselFeeConfigsPanel` — đã có, dùng lại). Tab monthly: form gán `vessel_type_id`, KHÔNG hiện panel phí per-tàu (phí ở Revenue).

### Task 16: VesselsListSection — nhận `classification` prop để render đúng cột/action

**Files:**
- Modify: `client/src/features/vessels/components/VesselsListSection.tsx`
- spot: cột "Cấu hình giá" → nút mở panel phí per-tàu.
- monthly: cột "Loại tàu" (bắt buộc chọn), link tới Revenue Cấu Hình Phí của type.
- unclassified: nút "Phân loại" (chuyển spot/monthly).

### Task 17: vessel form schema

**Files:**
- Modify: `client/src/features/vessels/vessels-schemas.ts`
- `vessel_type_id` giờ optional; bắt buộc CHỈ khi classification=monthly (superRefine).

---

## PHASE 6 — Client Revenue Cấu Hình Phí theo loại tàu

### Task 18: RevenueView + RevenueFeesSection — gắn theo vessel_type

**Files:**
- Modify: `client/src/features/revenue/views/RevenueView.tsx`
- Modify: `client/src/features/revenue/components/RevenueFeesSection.tsx`
- Modify: `client/src/features/revenue/components/RevenueModals.tsx`
- Form fee: field chọn **Loại tàu** (`vessel_type_id`) thay vì Mã tàu. Filter theo loại tàu. Nhãn: "Cấu hình giá cho tàu tháng theo loại".
- `feeConfigVesselLabel` → `feeConfigVesselTypeLabel` (đã có helper).

### Task 19: revenue store + schema

**Files:**
- Modify: `client/src/features/revenue/store/revenueStore.ts`
- Modify: `client/src/features/revenue/revenue-schemas.ts`
- `feeSchema`: `vessel_type_id` (số) thay `vessel_id` cho luồng monthly. giữ `vessel_id` cho panel spot.

---

## PHASE 7 — Data migration + verify (PRODUCTION — chốt OPEN DECISION trước)

### Task 20: Script migration idempotent

**Files:**
- Create: `server/app/db/sqlCommand/migrate_vessel_classification.py`

Chạy trong env `bason-dock` qua terminal python (không execute_code — sandbox thiếu psycopg2). Nội dung:
1. `UPDATE vessels SET classification='spot' WHERE vessel_type_id=343;`
2. `UPDATE vessels SET classification='monthly' WHERE vessel_type_id IN (344,380);`
3. `UPDATE vessels SET classification='unclassified' WHERE vessel_type_id IS NULL;`
4. (nếu chốt backfill spot) với mỗi vessel spot: INSERT fee_config copy từ fee 25 (base 1.000.000, unit per_hour, vessel_id=<id>, is_active=True).
5. `UPDATE fee_configs SET is_active=False WHERE id=25;` (retire type-based spot fee).
6. `UPDATE vessels SET vessel_type_id=NULL WHERE classification='spot';`
7. fee 26 giữ nguyên (type 344 monthly).

In BEFORE/AFTER counts từng bước. Bọc transaction, rollback nếu lệch.

### Task 21: Verify end-to-end (BẮT BUỘC — user demand)

- Đếm vessels theo classification khớp kỳ vọng (15/14/41).
- Mỗi tàu spot có đúng 1 fee active per-vessel.
- Gọi `resolve_billable_fees` cho 1 tàu mỗi nhóm → đúng nguồn.
- Chạy `backfill_ai_invoices_for_vessel` cho 1 tàu spot có detection → tạo được invoice có tiền thật (>0), verify subtotal = giờ neo × 1.000.000.
- Chạy backfill 1 tàu monthly type 344 → invoice có dòng tham chiếu per_month.
- `pytest server/app/tests -v` all pass.
- Client `pnpm run build` (type-check) pass.

---

## Files sẽ đụng (tổng hợp)

**Backend:** `models/vessel.py`, `db/schema_patches.py`, `schemas/vessel.py`, `schemas/fee.py`, `repositories/fee_config_repository.py`, `repositories/vessel_repository.py`, `services/fee_resolution_service.py`(new), `services/detection_invoice_service.py`, `services/ship_invoice_backfill_service.py`, `services/vessel_read_service.py`, `api/v1/endpoints/vessels.py`, `api/v1/endpoints/fee_configs.py`, `db/sqlCommand/migrate_vessel_classification.py`(new), tests(new).

**Client:** `types/api.types.ts`, `features/vessels/{services/vesselsApi.ts, vessels-schemas.ts, views/VesselsView.tsx, components/VesselsMainTabs.tsx, VesselsListSection.tsx}`, `features/revenue/{services/revenueApi.ts, views/RevenueView.tsx, revenue-schemas.ts, store/revenueStore.ts, components/RevenueFeesSection.tsx, RevenueModals.tsx}`.

## Rủi ro
- **Migration production billing:** chạy trên DB thật. Backup/transaction bắt buộc. Chốt 2 OPEN DECISION trước.
- **AI invoice hồi tố:** 270 AI invoice cũ tính bằng fee rỗng (0đ thật). Không đụng invoice cũ (financial lock PAID). Chỉ ảnh hưởng invoice mới.
- **vessel_type "Tàu lẻ" (343):** sau migration bị bỏ trống (spot không dùng type). Giữ row để rollback, ẩn khỏi UI chọn loại (chỉ hiện type dùng cho monthly).
- **Đổi classification runtime:** spot→monthly phải xử lý fee cũ per-vessel (giữ hay vô hiệu?). Cần policy — đề xuất giữ nhưng resolve bỏ qua khi monthly.

## Open questions (chốt trước khi execute)
1. Les Rives (SG-5893) → monthly hay unclassified?
2. Backfill fee 25 → per-vessel cho 15 tàu spot: auto hay để user nhập tay?
3. Khi user đổi 1 tàu unclassified→spot/monthly ở UI, có auto-backfill invoice cho detection cũ của tàu đó không? (đề xuất: có, đã có sẵn `run_vessel_backfill_task`)

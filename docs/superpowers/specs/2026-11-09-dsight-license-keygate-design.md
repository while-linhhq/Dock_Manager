# DSight × Keygate — Thiết kế quản lý license (v1)

> Ngày: 2026-11-09 · Trạng thái: **đã duyệt** (Hướng A, baseline Trial 2 / Standard 4). Phase 1 đã thực thi trên staging + production ngày 2026-11-09; Phase 2 (source) đang ở bước lập kế hoạch.
> Bối cảnh: DTG-Corp dùng Keygate self-host (`stg-license.dtgsoft.vn`, `license.dtgsoft.vn`) để cấp license cho sản phẩm DSight (dock-manager). Tài liệu này chốt mô hình dữ liệu Keygate, quy trình vận hành, danh sách dọn dẹp, và pattern tích hợp trong source DSight.

---

## 1. Mục tiêu & lý do

DTG bán DSight theo từng khách hàng (mỗi cảng/công ty một bộ cài on-prem). Cần:

- **1 license = 1 máy duy nhất** (mỗi khách cài 1 bộ; cài thêm máy phải có hợp đồng mới).
- **Số camera custom theo từng khách** (khách 6 cam, 12 cam, 20 cam… tuỳ hợp đồng).
- **Hạn dùng + gia hạn** (hợp đồng năm), tạm ngưng/thu hồi khi chưa thanh toán.
- **Tạm thời đơn giản**, nhưng **pattern trong source sẵn sàng mở rộng** thành giới hạn theo từng module chức năng / gói (Basic/Pro/Enterprise…) mà không phải refactor.
- Offline/ân hạn: mất mạng tạm thời hoặc license server down **không được làm dừng vận hành cảng**.

## 2. Hiện trạng (đo ngày 2026-11-09, read-only)

| Hạng mục | Staging | Production |
|---|---|---|
| Keygate | v0.1.20 (commit 7b8a29e) | v0.1.20 (commit 7b8a29e) |
| Product | `DSight` (desktop, prefix `DSIGHT`) | `DSight` (desktop, prefix `DSIGHT`) |
| Plans | Trial(30d), Community(perpetual), Pro(subscription/month), Enterprise(subscription/year) | giống staging |
| Plan entitlements | **không có** (license test@ trả `features={}`; license ops@ chỉ có feature từ addon) | **không có** |
| `max_activations` | Trial 1, Community 1, Pro 1, Enterprise 1 | Trial 3, Pro 5, Enterprise 50 |
| Addons | **9** (3 camera tier cố định + 6 module); **2 addon đang gắn license test `ops@dtgsoft.vn`** (`cams-16` → `max_cameras=16`, `camera-fusion` → bool), 7 addon chưa gắn | **0** |
| Licenses | 2 test (`test@`, `ops@`), 0 activation | 2 test (`ops@`), 1 activation `server-dockmon-prod` |
| Khách thật | chưa có | chưa có |

Kết luận: chưa có giới hạn nào được thực thi; dữ liệu hiện tại đều là test/cấu hình dở → dọn an toàn.

## 3. Ràng buộc từ Keygate v0.1.20 (đã đọc source + OpenAPI + docs)

- **Entitlement chỉ gắn ở plan** (dùng chung cho mọi license trên plan). Không có "custom limit theo license" ngoài **addon gắn theo license**.
- **Addon thay thế** entitlement cùng tên của plan (không cộng dồn); `value` cố định trên addon; không có quantity.
- Sửa `value` addon → đổi cho **mọi license** đang gắn addon đó; xoá addon → mất feature ở mọi license (FK cascade); `active:false` **không** thu hồi feature.
- License chỉ có: `max_activations` (số máy), `valid_until` (hạn), `grace_days` (ân hạn sau hạn), `token_ttl_days` (nhịp check-in offline), plan, email, `external_customer_id`, `notes`.
- **Không xoá được license** (chỉ revoke/suspend); plan bị chặn xoá khi còn license tham chiếu.
- `/license/verify` trả `features`: bool là boolean; `int/string/quota` là **string** (vd `"max_cameras": "12"`). Feature không có = không được cấp.
- Verify 404 gộp mọi lý do (key sai, hết hạn, chưa activate máy này) để chống dò key.
- Offline: token Ed25519 ký, có `exp` (clamp theo `valid_until + grace_days`), `vun`, `grc`; client verify offline bằng pubkey (`GET /license/pubkey`, 2 môi trường **khác key**).
- API admin cho products/plans/entitlements/addons **không có trong OpenAPI** (chỉ có trong source) → tự động hoá bằng source routes.
- AGPL: giữ "Powered by Keygate" trong admin UI nội bộ; không white-label; không sửa code Keygate giai đoạn này.

## 4. Phương án đã cân nhắc

| # | Phương án | Ưu | Nhược | Kết luận |
|---|---|---|---|---|
| A | **Plan = gói dùng chung; Addon = tuỳ biến theo license** (camera limit = 1 addon `max_cameras` riêng từng khách) | Giữ khái niệm gói; custom N không giới hạn; mở rộng module theo gói tự nhiên; addon tái dùng/đổi dễ | Mỗi khách có 1 addon (danh sách addon ≈ danh sách khách) | **Chọn** |
| B | Mỗi khách 1 plan riêng (plan chứa max_cameras + module flags) | 1 nơi chứa toàn bộ hợp đồng khách | Plan list = danh sách khách; mất gói dùng chung; khi có gói chuẩn vẫn phải quay lại addon; plan không xoá được khi còn license | Loại |
| C | Giữ addon tier cố định (8/16/32 như hiện tại) | Ít addon | Không đáp ứng "custom N"; đổi số cam phải tạo tier mới | Loại |

**Quyết định:** Hướng A.

## 5. Mô hình Keygate đích

### 5.1 Plans (2 plan, dùng chung cả 2 môi trường)

| Thuộc tính | `trial` | `standard` | `lifetime` |
|---|---|---|---|
| license_type | trial | subscription | **perpetual** |
| billing_interval | – | year (hợp đồng năm; không dùng Stripe) | – |
| trial_days | 30 | – | – |
| max_activations | **1** | **1** | **1** |
| grace_days | 0 (trial không có grace — xem §7.6) | **15** | **15** |
| token_ttl_days | 7 | **7** | **7** |
| max_seats | 0 | 0 | 0 |
| license_model | standard | standard | standard |
| Entitlement `max_cameras` | int `2` | int `4` (baseline; addon override) | int `4` (baseline; addon override) |

Ghi chú:
- Trial `max_cameras=2` khớp với 2 camera seed sẵn của bản cài mới → PoC chạy được ngay.
- Standard/Lifetime baseline 4 camera là mức "bao gồm trong gói"; khách mua N camera → addon `max_cameras=N` override (N có thể < hoặc > 4).
- `standard`/`trial`: `valid_until` **luôn đặt tay khi cấp license** (hạn hợp đồng). `lifetime`: **không đặt `valid_until`** (license perpetual, không hết hạn) — vẫn giữ 1 máy + addon camera.
- Không dùng Stripe/self-signup/portal khách ở giai đoạn này.

### 5.2 Addons (chỉ tạo khi có khách thật)

- Mỗi khách trả phí có **đúng 1 addon camera riêng**:
  - `name`: `Camera limit — <MÃ_KH>`; `slug`: `camera-<ma-kh>` (vd `camera-dtg-bason-001`)
  - `feature`: `max_cameras`; `value_type`: `int`; `value`: `"<N>"` (string theo API)
- Addon **chỉ gắn cho đúng 1 license** (1 khách = 1 license = 1 addon). Vì vậy `PUT` value khi khách đổi số camera là an toàn; nếu muốn tuyệt đối an toàn: tạo addon mới + attach + detach addon cũ.
- **Không** gắn 1 addon cho 2 license. **Không** xoá addon khi license còn dùng (cascade mất feature).
- Giai đoạn này **không tạo addon module**. Khi có gói module: thêm entitlement bool vào plan; khách lẻ cần mở thêm → addon bool riêng.
- Không dùng addon camera tier cố định nữa (đã xoá ở Phase 1).

### 5.3 Quy ước feature (để mở rộng sau này)

| Feature | Type | Ý nghĩa | Giai đoạn |
|---|---|---|---|
| `max_cameras` | int | Tổng số camera được cấu hình (rows) | **Bây giờ** |
| `module_<ten>` | bool | Mở module chức năng (vd `module_ai_lab`) | Khi có gói module |
| `limit_<ten>` | int | Giới hạn số lượng của module (vd `limit_vessels`) | Khi có gói module |

Quy tắc: feature không có trong license = **không được cấp** (source dùng default an toàn). Thêm feature mới sau này = thêm 1 dòng registry ở source + entitlement/addon bên Keygate, **không sửa kiến trúc**.

### 5.4 Quy trình vận hành license

1. **Cấp license mới**: `POST /admin/licenses` với `product_id`, `plan_id` (standard), `email` (email khách/đại diện), `valid_until` = ngày hết hợp đồng, `external_customer_id` = `DTG-<MÃ_KH>`, `notes` = số HĐ/ghi chú. Key trả về 1 lần + email best-effort → gửi khách qua kênh an toàn.
2. **Gắn giới hạn camera**: tạo addon `camera-<ma-kh>` value N → `POST /admin/licenses/{id}/addons {addon_id}`.
3. **Gia hạn**: `POST /admin/licenses/{id}/valid-until {valid_until}` (RFC3339 tương lai). Khách không cần thao tác; lần check-in sau tự nhận hạn mới.
4. **Đổi số camera**: `PUT /admin/addons/{id} {value:"M"}` (addon chỉ gắn 1 license) → lần verify sau khách nhận giá trị mới.
5. **Tạm ngưng**: `POST /admin/licenses/{id}/suspend` (giữ activation) → `reinstate` khi thanh toán.
6. **Thu hồi**: `POST /admin/licenses/{id}/revoke` (terminal, xoá activation). Không xoá license.
7. **Khách đổi máy/cài lại**: `DELETE /admin/activations/{id}` (giải phóng slot) → khách activate lại. **Không** nâng `max_activations` lên 2.
8. **Lộ key**: `POST /admin/licenses/{id}/rotate-key` (key cũ chết ngay, activation cũ bị xoá).
9. **Đối soát**: `GET /admin/licenses/export` hàng tháng; lưu hồ sơ.
10. **Không** sửa `value` addon dùng chung (giai đoạn này mỗi addon 1 license nên OK, nhưng vẫn giữ quy tắc).
11. **Trial / PoC**: mỗi bản cài demo/PoC được cấp **1 license trial riêng** tại lúc bàn giao (ops mint key, `valid_until` = ngày kết thúc PoC; nếu demo kéo dài, ops đặt `valid_until` tay khi tạo). Trial **hard-stop** đúng ngày hết hạn (không grace, không tự chuyển gói).
13. **Lifetime**: tạo license trên plan `lifetime`, **không truyền `valid_until`** → license không hết hạn; vẫn 1 máy + addon camera N. Không cần renew; vẫn có thể suspend/revoke khi vi phạm hợp đồng.
12. **Chuyển trial → trả phí**: `POST /admin/licenses/{id}/change-plan {plan_id: standard}` + `POST /admin/licenses/{id}/valid-until {valid_until}` → **giữ nguyên key + activation**, khách không phải cài lại/nhập lại key.

Người được phép: 1–2 người ops giữ API key `admin` (không chia sẻ). Mọi thay đổi có audit log của Keygate.

## 6. Phase 1 — Dọn dẹp & chuẩn hoá Keygate (chờ duyệt trước khi chạy)

### 6.0 Nguyên tắc an toàn
- Chạy **staging trước**, verify, rồi mới production.
- Trước khi sửa: `GET /admin/licenses/export?format=json`, `GET /admin/plans`, `GET /admin/addons`, `GET /admin/licenses` lưu JSON ra file để rollback/đối chiếu.
- Không xoá license, không đụng activation test (trừ khi được yêu cầu).
- Mọi lệnh dùng API key admin; không log key.

### 6.1 Staging (`stg-license.dtgsoft.vn`)
1. **Detach 2 addon khỏi license test `ops@dtgsoft.vn`** (`435f6d7f-ce8e-4b1a-960d-8fc146706ced`): `DELETE /admin/licenses/435f6d7f-ce8e-4b1a-960d-8fc146706ced/addons/bc53a6af-7e79-4fc5-aaeb-983530cecbdb` (`cams-16`) và `.../addons/c7bd05a3-83fd-41e2-abd5-7f3c8e09df2a` (`camera-fusion`). Đây là license test, không phải khách thật.
2. **Xoá 9 addon** (sau khi detach; 7 addon còn lại vốn chưa gắn):
   | slug | id |
   |---|---|
   | cams-8 | `dd78cc82-8fa2-4606-bc6e-ddc0d413d2f9` |
   | cams-16 | `bc53a6af-7e79-4fc5-aaeb-983530cecbdb` |
   | cams-32 | `97d43342-73d6-49fb-b594-0ab544c171e2` |
   | camera-fusion | `c7bd05a3-83fd-41e2-abd5-7f3c8e09df2a` |
   | seam-anchor | `7b99228b-e775-4585-b445-a2a6b5de973c` |
   | ai-lab | `4aefc784-c7d9-4d7e-8f44-11fb0400186e` |
   | revenue-management | `d59a51fc-6331-47d7-b678-fbbef585fe3a` |
   | discount-approval | `b441c0cd-6975-4401-8e95-55714add4998` |
   | automated-backup | `3086fcda-3050-4312-a03c-5ba7d2546785` |
3. **Xoá plan** `Community` (`c94553f5-4c5c-426d-a2e0-10e789e635c9`) và `Enterprise` (`67bd4334-1e94-40cd-b633-da665b562d05`) — không có license.
4. **Chuẩn hoá plan `Pro` → `Standard`**: `PUT /admin/plans/ddbffea4-dea0-47d0-89be-f20c25cbd7fb`
   `{name:"Standard", slug:"standard", billing_interval:"year", max_activations:1, grace_days:15, token_ttl_days:7}`
5. **Chuẩn hoá `Trial`**: `PUT /admin/plans/7c96ca3a-a4dc-4d00-8e32-ee7f8cbaa545`
   `{max_activations:1, trial_days:30, grace_days:3, token_ttl_days:7}`
6. **Thêm entitlement**:
   - `POST /admin/entitlements` `{plan_id:"<trial>", feature:"max_cameras", value_type:"int", value:"2"}`
   - `POST /admin/entitlements` `{plan_id:"<standard>", feature:"max_cameras", value_type:"int", value:"4"}`
7. **Verify**: plans list có đúng entitlements; addons total = 0; `/license/entitlements` của license test trả `features.max_cameras == "4"`.

### 6.2 Production (`license.dtgsoft.vn`)
1. Addons: hiện 0 → không xoá.
2. Xoá plan `Community` (`24ff3783-aba0-4d4c-97e4-a0609bca1570`) và `Enterprise` (`15738b1e-cb15-4ac4-9cdc-810ead5b421c`).
3. Chuẩn hoá `Pro` (`841af476-1046-49c5-8f6d-b6230a06d3c2`) → `Standard` (cùng payload, `max_activations:1` từ 5).
4. Chuẩn hoá `Trial` (`09ef641b-74ac-40a0-a92c-06535ea2a96b`) → `max_activations:1` (từ 3), `grace_days:3`, `token_ttl_days:7`.
5. Thêm entitlement `max_cameras` (trial 2, standard 4).
6. Verify như staging. Giữ nguyên 2 license test và activation `server-dockmon-prod`.

### 6.3 Rollback
- Addon đã xoá: tạo lại từ JSON đã lưu (nếu cần).
- Plan đã xoá: tạo lại từ JSON (Community/Enterprise không có license nên không ảnh hưởng khách).
- Plan update: `PUT` lại giá trị cũ từ JSON snapshot.
- License/activation: không thay đổi.

## 7. Phase 2 — Pattern tích hợp trong source DSight

### 7.1 Nguyên tắc
- **Một registry feature duy nhất**; mọi nơi đọc license đều đi qua `LicenseService` (không rải `if` khắp code).
- **Fail-safe**: license server down/mất mạng → dùng cache token + grace; **không dừng pipeline đang chạy**, không chặn login/đọc dữ liệu/health.
- **warn → enforce**: ship `LICENSE_ENFORCEMENT=warn` trước (chỉ banner + log), pilot 1 cảng, sau đó bật `enforce`.
- **Không DRM quá đà**: giá trị thật là hợp đồng + audit + gia hạn.

### 7.2 File layout (server)
```
server/app/core/license/
  __init__.py
  features.py          # FeatureRegistry + chuẩn hoá string→bool/int
  machine.py           # hardware fingerprint ("mã máy") + resolve từ host mounts
  keygate_client.py    # HTTP client: activate/verify/entitlements/pubkey
  token.py             # verify Ed25519 token offline
  service.py           # LicenseService singleton: state, check-in loop, enforcement helpers
  deps.py              # require_license, require_module(key)
scripts/install_license_identity.sh   # chạy trên HOST: kiểm tra mounts + in mã máy để đối chiếu
server/app/models/license_state.py
server/app/repositories/license_state_repository.py
server/app/api/v1/endpoints/license.py   # GET/POST /license (admin)
server/app/schemas/license.py
server/app/utils/crypto.py               # mã hoá license key at-rest (Fernet từ SECRET_KEY)
```

### 7.3 Config mới (`core/config.py`)
```python
# Licensing (Keygate)
LICENSE_SERVER_URL: str = "https://license.dtgsoft.vn"
LICENSE_KEY: str = ""                 # optional; nếu rỗng thì nhập qua UI admin
LICENSE_INSTANCE_ID: str = ""         # CHỈ để override khi dev; production dùng hardware fingerprint
LICENSE_ENFORCEMENT: Literal["off","warn","enforce"] = "warn"   # chỉ là default lúc chưa có cấu hình DB
LICENSE_CHECKIN_HOURS: int = 6
```
- `LICENSE_KEY` nếu đặt trong `.env` sẽ bị bake vào image (Dockerfile `COPY . .`) → khuyến nghị **không** đặt key trong `.env`; nhập qua UI admin (lưu DB mã hoá). Chỉ `LICENSE_INSTANCE_ID` + `LICENSE_SERVER_URL` trong `.env`.
- **Chế độ enforce chuyển runtime được**: `LICENSE_ENFORCEMENT` trong env chỉ là default; giá trị hiệu lực lưu ở `license_state.enforcement_mode` và admin đổi được qua trang License (không cần sửa `.env`/restart), có audit.

### 7.4 DB `license_state` (1 row, id=1)
```
instance_id TEXT, license_key_enc TEXT, license_id TEXT, plan_name TEXT,
status TEXT, valid_until TIMESTAMPTZ, grace_days INT, features JSONB,
token TEXT, token_exp TIMESTAMPTZ, pubkey TEXT, last_verified_at TIMESTAMPTZ,
last_error TEXT, updated_at TIMESTAMPTZ
```
- Thêm ORM model (cho `init_db` create_all) **và** schema patch `_ensure_license_state()` (cho môi trường chạy trực tiếp/upgrade) theo pattern hiện có.
- **`instance_id` = "mã máy" (hardware fingerprint)** — chống copy bộ cài:
  - App đọc **runtime** từ host (bind mount read-only trong docker-compose): `/etc/machine-id`, `/sys/class/dmi/id/product_uuid`, `/sys/class/dmi/id/board_serial` (nếu đọc được) → `sha256("DSIGHT|" + các giá trị)` → format ngắn `DSIGHT-XXXX-XXXX-XXXX` (base32). Gửi mã này làm `identifier` khi activate/verify (kèm `label` = tên cảng).
  - `LICENSE_INSTANCE_ID` env **chỉ để override khi dev**; production luôn tính từ phần cứng. Nếu không đọc được host mounts → fallback UUID lưu DB + log warning (chỉ nên xảy ra ở dev).
  - App lưu mã máy vào `license_state.instance_id`; nếu lần khởi động sau mã máy **khác** mã đã lưu → coi như license invalid (yêu cầu ops xoá activation cũ + kích hoạt lại), không tự đổi.
  - Cài lại trên **cùng máy** → cùng mã → activate lại = `already_activated`, không tốn slot. Đổi phần cứng/ổ đĩa → mã đổi → ops xoá activation cũ (`DELETE /admin/activations/{id}`) rồi khách nhập lại key.
  - Hạn chế đã biết: VM clone giữ nguyên `product_uuid` + `machine-id` có thể trùng mã; giảm thiểu bằng `board_serial` (nếu đọc được) và đối soát IP khi check-in. Patch code Python không chặn tuyệt đối (xem §10).

### 7.5 FeatureRegistry (`features.py`)
```python
@dataclass(frozen=True)
class FeatureSpec:
    type: Literal["bool","int","string","quota"]
    default: bool | int | str
    label: str

FEATURES: dict[str, FeatureSpec] = {
    "max_cameras": FeatureSpec("int", 0, "Số camera tối đa"),
    # Thêm sau (ví dụ):
    # "module_ai_lab": FeatureSpec("bool", False, "Module AI Lab"),
    # "limit_vessels": FeatureSpec("int", 0, "Số tàu tối đa"),
}
```
- `LicenseService.features()`: map thô từ Keygate (bool/string) → chuẩn hoá theo spec; feature lạ giữ nguyên; feature thiếu → default.
- Helper: `get_bool(key)`, `get_int(key)`, `is_granted(key)`.
- **Thêm giới hạn module mới sau này** = 3 bước, không sửa kiến trúc:
  1. Thêm 1 dòng `FEATURES[...]` ở registry.
  2. Thêm entitlement (plan) hoặc addon (license) bên Keygate.
  3. Gắn `Depends(require_module("module_x"))` vào router/endpoint tương ứng (+ map menu FE nếu cần ẩn menu).

### 7.6 LicenseService
- Khởi động trong lifespan **sau** `run_startup_checks()` (DB + schema sẵn sàng), chạy `asyncio.create_task` giống SEPay; không block boot.
- Luồng: load state từ DB → nếu có key và chưa có token/features → activate; sau đó verify định kỳ `LICENSE_CHECKIN_HOURS` (mặc định 6h) → lưu token/features/valid_until.
- Verify offline: chữ ký Ed25519 (`cryptography`), `did == instance_id`, `now < exp`; nếu `vun` + `grc` → còn trong grace. Pubkey cache trong DB, refresh khi verify.
- **Phân loại lỗi verify**:
  - `404 LICENSE_NOT_FOUND` = **server trả lời dứt khoát** license không dùng được (revoked/suspended/hết hạn quá grace/key sai/chưa activate máy này) → đánh dấu invalid **ngay**, hiện banner; **không** coi là lỗi mạng. Để có thông điệp đúng, gọi thêm `POST /license/activate` với key đã lưu: 403 trả `LICENSE_SUSPENDED|LICENSE_REVOKED|LICENSE_EXPIRED|LICENSE_CANCELED`; 404 = key sai/không tồn tại.
  - Timeout/5xx/mất mạng = lỗi tạm thời → **giữ cache**, chỉ invalid khi token hết hạn **và** quá `vun + grc`.
- **Suspend/revoke có hiệu lực ngay** (không grace); **chỉ expiry** (`valid_until`) mới có `grace_days`. Trial hard-stop (grace 0).
- Trạng thái hiệu lực: `valid`, `grace`, `expired`, `unlicensed`, `suspended`, `revoked`. `warn`: chỉ banner/log; `enforce`: chặn hành vi mới (không chặn đọc/login/pipeline đang chạy/stop).
- Audit local mọi lần activate/verify fail (không log key).

### 7.7 Điểm gate
| Điểm | Hành vi |
|---|---|
| `POST /cameras/` (create) | Đếm tổng camera rows; nếu `count >= max_cameras` → 403 `CAMERA_LIMIT` (enforce) / log+banner (warn). Đây là choke point duy nhất tạo camera. |
| `PUT /cameras/{id}` | Không tăng số row → không cần check quota (quota tính tổng row). |
| `POST /pipeline/start` | License không hợp lệ (invalid/suspended/revoked/quá grace) → 403 (enforce). Không gate `stop/status/WS`; pipeline đang chạy giữ nguyên. Endpoint này unauthenticated; gate dùng license state, không cần user. (Docker entrypoint `run_prod.py` **không** autostart pipeline — chỉ `run_dev.py` autostart khi dev; nên không có rủi ro chặn autostart production.) |
| Router module (sau này) | `APIRouter(dependencies=[Depends(require_module("module_x"))])`. |
| `GET /license/status` | (auth) FE gọi khi mount layout: nếu `unlicensed` → hiện màn hình nhập key lần đầu; dùng `features.max_cameras` cho cảnh báo/disable camera. **Không sửa** `/users/me`. |
| `/health` | Giữ nguyên 200 (readiness probe); license status là endpoint riêng `/api/v1/license/status` (auth) hoặc field trong `/users/me`. |

### 7.8 API cho FE
- `GET /api/v1/license/status` (auth): status, plan_name, valid_until, days_left, grace_days, features, enforcement_mode, machine_code (FE dùng cho màn hình nhập key + cảnh báo quota).
- `POST /api/v1/license/activate` (admin): nhập key → activate + verify ngay.
- `POST /api/v1/license/refresh` (admin): verify ngay.
- `GET /api/v1/license` (admin): chi tiết state + last_error.
- `PUT /api/v1/license/enforcement` (admin): đổi warn/enforce/off runtime (dùng qua curl/runbook, không cần UI).

### 7.9 Frontend (tối giản — đã chốt)
- **Chỉ một màn hình nhập key lần đầu**: sau khi đăng nhập, nếu `license.status === 'unlicensed'` → `MainLayout` render `LicenseActivationView` (full nội dung) thay cho app: ô nhập key + nút "Kích hoạt" + hiển thị **mã máy** để gửi DTG; admin mới nhập được, user thường thấy "Chưa kích hoạt license — liên hệ quản trị viên". Kích hoạt xong → tự vào app bình thường.
- **Không** có trang thông tin license riêng, **không** menu license, **không** banner toàn cục.
- **Cảnh báo sắp hết tài nguyên** (inline, không banner): trang Quản Lý Cảng hiện cảnh báo vàng khi số camera sắp chạm `max_cameras` (còn ≤ 2 slot hoặc ≥ 90%); khi `enforce` và đã đạt giới hạn thì disable nút "Thêm Camera" + hiện lỗi 403 từ API. Tương tự có thể thêm cảnh báo cho giới hạn module sau này.
- Admin/ops xem trạng thái, đổi enforcement mode qua API/runbook (không cần UI); backend vẫn là nơi enforce thật.
- Lưu ý: FE chỉ là UX; backend là nơi enforce thật.

### 7.10 Điều kiện triển khai & first-run
- **Bắt buộc**: máy khách có outbound HTTPS tới `license.dtgsoft.vn` (các cảng hiện đã có internet cho SEPay/Zalo/cloudflared). Keygate v0.1.20 **không có offline activation** → lần kích hoạt đầu tiên cần online.
- Bản cài chưa có key vẫn boot bình thường (chế độ `unlicensed`): cho login admin, trang License để nhập key; **không** tạo camera/không start pipeline mới khi `enforce`.
- Kỹ thuật viên DTG cài đặt → đăng nhập admin → nhập key (hoặc ops set `LICENSE_KEY` trước khi bàn giao nếu muốn tự động) → activate.
- Trang License hiển thị `instance_id` để ops đối chiếu/giải phóng activation khi cần.

### 7.10b Rollout
1. Ship code với `LICENSE_ENFORCEMENT=warn`; cấp license thật cho Bason; theo dõi 1–2 tuần (không false-positive).
2. Bật `enforce` cho pilot; đo số lần chặn nhầm/support ticket.
3. Rollout các cảng tiếp theo; runbook cấp phát/renew.

## 8. Test matrix (Phase 2)

| # | Case | Kỳ vọng |
|---|---|---|
| T1 | Activate key đúng + instance mới | 200, có token/features |
| T2 | Activate lại cùng identifier | 200 `already_activated`, không tốn slot |
| T3 | Máy thứ 2 (identifier mới) với max_activations=1 | 409 `ACTIVATION_LIMIT` |
| T4 | Verify định kỳ | status/features/valid_until đúng |
| T5 | Key sai | 404 (không leak) |
| T6 | Suspend | Verify 404 **ngay**; phân loại qua activate → banner "tạm ngưng"; pipeline đang chạy không dừng |
| T7 | Revoke | Verify 404 ngay; activate 403 `LICENSE_REVOKED` |
| T8 | Hết hạn `valid_until` (Standard) | Vào grace đúng `grace_days`, sau đó fail |
| T9 | Gia hạn valid-until | Tự hoạt động lại sau check-in |
| T10 | Rotate key | Key cũ chết; key mới activate được |
| T11 | Keygate down/mất mạng | Dùng token cache tới `vun+grc`; không crash |
| T12 | Vượt `max_cameras` | 403 + không tạo camera (enforce) / log (warn) |
| T13 | Reinstall (mất DB) | Ops xoá activation cũ → activate lại OK |
| T13b | Trial hết hạn | Hard-stop đúng ngày, không grace |
| T14 | Verify chữ ký token offline | Pass; sửa 1 byte → fail |
| T15 | Thêm module gate (tương lai) | 403 + FE ẩn menu |
| T16 | Upgrade Keygate staging | Migration OK, license cũ verify được |

## 9. Những gì để builder quyết (không chờ user)
- Copy UI cụ thể của trang License/banner; vị trí chính xác trong MainLayout.
- Tên hàm/class, chia file nhỏ hơn nếu cần; chi tiết retry/backoff HTTP.
- Cách hiển thị `days_left` (làm tròn), format ngày.
- Có dùng `requests` (đang có sẵn) thay vì httpx cho client Keygate (khuyến nghị: `requests` theo pattern SEPay; hoặc httpx nếu muốn async).
- Chi tiết schema patch SQL (theo pattern `_ensure_*` hiện có).
- Có thêm webhook Keygate → Telegram không (ngoài phạm vi Phase 2; có thể làm sau).

## 10. Rủi ro & biện pháp

| Rủi ro | Biện pháp |
|---|---|
| Keygate v0.1.x, bus factor 1 | Pin image `v0.1.20`; backup PostgreSQL license server; abstraction `LicenseService` để đổi provider sau |
| Mất token cache / DB license_state | Backup DB; grace 15 ngày; không block pipeline đang chạy |
| Đồng hồ máy khách lệch | Yêu cầu NTP; token exp là mốc tuyệt đối; cảnh báo nếu lệch nhiều |
| Clone bản cài (copy DB + env) → cùng instance_id | Mã máy tính runtime từ phần cứng host → máy mới ra mã khác, Keygate từ chối (1 activation). VM clone giữ nguyên product_uuid vẫn có thể trùng → đối soát IP/activation; nếu cần chặt hơn: dongle/TPM (ngoài scope) |
| `.env` bake vào image | Không đặt license key trong `.env`; nhập qua UI, lưu DB mã hoá |
| Quota camera đếm tổng rows, seed sẵn 2 camera | Trial=2 khớp seed; Standard=4; khách mua ít hơn 2 → ops xoá bớt camera seed khi bàn giao |
| Sửa plan ảnh hưởng mọi license trên plan | Plan chỉ dùng chung 2 gói; thay đổi limit khách làm qua addon, không sửa plan |
| AGPL | Giữ attribution; không sửa code Keygate; nếu cần white-label/portal → mua commercial license |

## 11. Việc chưa làm (non-goals)
- Stripe/thanh toán tự động, portal tự phục vụ cho khách, self-signup.
- Release feed/updater ký (product `require_signing` giữ nguyên, không dùng).
- Đa tenant, seats, usage metering.
- White-label Keygate.
- Chống crack tuyệt đối (code Python nằm máy khách; mọi check đều vá được).

## 12. Phê duyệt cần có trước khi thực thi
- [x] Duyệt mô hình Keygate mục 5 (2 plan, addon camera riêng từng khách).
- [x] Duyệt danh sách dọn dẹp Phase 1 mục 6 (xoá 9 addon staging + 2 plan/env, đổi Pro→Standard, sửa max_activations). **Đã thực thi 2026-11-09.**
- [x] Duyệt pattern source mục 7 (đủ để viết plan triển khai Phase 2).


## 13. Quyết định từ vòng review độc lập (2026-11-09)

1. **Verify 404**: coi là server trả lời dứt khoát → invalid ngay (không chờ token cache); phân biệt suspended/revoked/expired bằng `POST /license/activate` (403) khi cần hiển thị thông điệp. Chỉ lỗi mạng/5xx mới dùng cache tới `exp`/`vun+grc`. Pipeline đang chạy không bị dừng.
2. **Online activation là prerequisite**: mọi bản cài cần outbound HTTPS tới license server ở lần kích hoạt đầu; bản cài chưa key vẫn boot và cho nhập key qua UI.
3. **Trial hard-stop** đúng ngày (Keygate hard-code grace 0 cho trial không Stripe/không fallback); **không** đặt `trial_fallback_plan_id` (tránh tự chuyển thành license perpetual miễn phí). Trial plan đặt `grace_days=0`.
4. **Trial issuance/conversion**: ops mint trial key tại bàn giao; chuyển trả phí bằng `change-plan` + `valid-until`, giữ key/activation.
5. **Enforcement mode** đổi runtime qua DB/UI (không cần sửa `.env`/restart); env chỉ là default.
6. Phase 1 không gặp `TRIAL_FALLBACK_IN_USE` (đã verify xoá plan thành công); trial hiện không trỏ fallback.
7. **"Mã máy" = hardware fingerprint tính runtime** (machine-id + DMI product_uuid + board_serial, host mounts read-only) — chống copy bộ cài; `LICENSE_INSTANCE_ID` chỉ override dev; mã đổi → license invalid, ops xoá activation cũ. Đã chốt 2026-11-09.
8. **UI tối giản**: chỉ màn hình nhập key lần đầu khi `unlicensed`; **bỏ** trang thông tin license + banner toàn cục; thêm cảnh báo inline khi sắp hết giới hạn camera. Đã chốt 2026-11-09.
9. **Thêm gói `lifetime`** (perpetual, không `valid_until`, 1 máy, max_cameras baseline 4, addon override) — đã tạo trên cả staging + production 2026-11-09.

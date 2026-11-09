# Runbook vận hành license DSight × Keygate

> Ngày: 2026-11-09 · Áp dụng cho **Keygate v0.1.20** (commit `7b8a29e`) và DSight bản có tích hợp license (Task 1–14).
> Liên quan: `docs/superpowers/specs/2026-11-09-dsight-license-keygate-design.md` · `docs/superpowers/plans/2026-11-09-dsight-license-integration.md`
> Đối tượng: 1–2 người ops DTG giữ Keygate admin API key. Mọi thao tác admin đều được Keygate ghi audit.

> ⚠️ **Quy tắc bất biến**
> 1. **1 license = 1 máy.** Không nâng `max_activations` lên 2 để "cho tiện"; đổi máy thì xoá activation cũ.
> 2. **Không commit license key / admin API key / `.env`** vào git, chat, ticket hay log.
> 3. **Không xoá license** trên Keygate — chỉ `suspend` / `revoke` để giữ audit (Keygate không cho xoá license).
> 4. **Không đặt `LICENSE_KEY` trong `server/.env`** — key bị bake vào image và nằm trong file; nhập qua màn hình first-run, app lưu DB đã mã hoá.
> 5. `SECRET_KEY` của app **phải khác giá trị mặc định `secret`** vì nó dẫn xuất khoá mã hoá license key at-rest.

---

## Mục lục

0. [Điều kiện tiên quyết](#0-điều-kiện-tiên-quyết)
1. [Môi trường & ID cố định](#1-môi-trường--id-cố-định)
2. [Chuẩn bị shell & xác thực](#2-chuẩn-bị-shell--xác-thực)
3. [Mã máy (hardware fingerprint)](#3-mã-máy-hardware-fingerprint)
4. [Cấp license trial](#4-cấp-license-trial)
5. [Cấp license standard](#5-cấp-license-standard)
6. [Cấp license lifetime](#6-cấp-license-lifetime)
7. [Addon số camera theo từng khách](#7-addon-số-camera-theo-từng-khách)
8. [Gia hạn standard](#8-gia-hạn-standard)
9. [Chuyển trial → trả phí](#9-chuyển-trial--trả-phí)
10. [Cài lại / đổi máy / thay phần cứng](#10-cài-lại--đổi-máy--thay-phần-cứng)
11. [Suspend / reinstate / revoke](#11-suspend--reinstate--revoke)
12. [Rotate key khi lộ key](#12-rotate-key-khi-lộ-key)
13. [Đổi enforcement mode qua API (không có UI)](#13-đổi-enforcement-mode-qua-api-không-có-ui)
14. [Kiểm tra phía khách hàng & probe staging](#14-kiểm-tra-phía-khách-hàng--probe-staging)
15. [Troubleshooting](#15-troubleshooting)
16. [Bảo mật](#16-bảo-mật)
17. [Phụ lục: bản đồ API & mẫu bảng khách hàng](#17-phụ-lục-bản-đồ-api--mẫu-bảng-khách-hàng)

---

## 0. Điều kiện tiên quyết

### 0.1 Phía máy khách (bản cài on-prem của cảng)

- **Có outbound HTTPS tới license server** (`license.dtgsoft.vn` production, `stg-license.dtgsoft.vn` staging), port 443. Keygate v0.1.20 **không có offline activation** — lần kích hoạt đầu tiên bắt buộc online.
- **Đồng hồ đúng giờ (NTP).** Token Ed25519 có `exp` là mốc tuyệt đối; máy lệch giờ nhiều sẽ báo token hết hạn/debug khó. Kiểm tra `timedatectl` hoặc `date -u`.
- Bản cài chưa có key **vẫn boot bình thường** ở trạng thái `unlicensed`: cho đăng nhập admin, hiện màn hình nhập key first-run, `/health` vẫn 200.
- App chạy trong Docker cần 2 bind mount read-only (đã có trong `server/docker-compose.yml`, Task 14):
  ```yaml
  - /etc/machine-id:/host/etc/machine-id:ro
  - /sys/class/dmi/id:/host/sys/class/dmi/id:ro
  ```
  Thiếu mount → app không đọc được host identity, fallback UUID lưu DB + log warning (chỉ chấp nhận ở dev).
- **`SECRET_KEY`** trong `server/.env` phải là giá trị ngẫu nhiên mạnh, **không phải `secret`** (mặc định trong code). `app/utils/crypto.py` dẫn xuất khoá Fernet từ `SECRET_KEY` để mã hoá license key trước khi lưu DB; ai biết `SECRET_KEY` mặc định có thể giải mã key đã lưu. Đổi `SECRET_KEY` làm ciphertext cũ không giải mã được → khách phải nhập lại license key (không mất dữ liệu khác).
- Không cần mở port inbound nào cho license; chỉ outbound 443.

### 0.2 Phía ops

- Keygate admin API key (scope `admin`) lấy từ secret manager nội bộ; 1–2 người giữ. Keygate còn hỗ trợ key scope `licenses:write` cho automation (đủ cho license lifecycle + addons gắn license, **không** đủ tạo addon/entitlement).
- `curl` + `jq` trên máy ops.
- Bảng mã khách hàng nội bộ: `external_customer_id = DTG-<MÃ_KH>` (ví dụ `DTG-BASON-001`), ghi kèm số hợp đồng/ngày hết hạn trong `notes` của license.

### 0.3 Mô hình license (tóm tắt)

| | `trial` | `standard` | `lifetime` |
|---|---|---|---|
| license_type | trial | subscription (HĐ năm, không Stripe) | perpetual |
| `valid_until` | đặt tay khi cấp (ngày kết thúc PoC) | đặt tay khi cấp (ngày hết HĐ) | **không truyền** — vô hạn |
| `max_activations` | 1 | 1 | 1 |
| `max_cameras` baseline | 2 | 4 | 4 |
| gia hạn | không (hard-stop; chuyển standard nếu tiếp tục) | `valid-until` | không cần |
| addon camera | có (override baseline) | có | có |

- `max_cameras` đếm **tất cả camera rows** (kể cả inactive). Addon `max_cameras=N` thay thế baseline của plan, N có thể nhỏ hơn hoặc lớn hơn 4.
- Trial hard-stop đúng ngày hết hạn (không grace dài như standard). Trước khi hết trial, chuyển `change-plan` sang standard nếu khách tiếp tục.

---

## 1. Môi trường & ID cố định

Keygate trả mọi response thành công dạng `{"success": true, "data": ...}`; lỗi dạng `{"success": false, "error": {"code": "...", "message": "..."}}`.

| | **Staging** | **Production** |
|---|---|---|
| Base URL | `https://stg-license.dtgsoft.vn` | `https://license.dtgsoft.vn` |
| Product | `DSight` (desktop, prefix `DSIGHT`) | `DSight` (desktop, prefix `DSIGHT`) |
| Product ID | `9815c7dd-75be-4a67-9e93-c778574b4659` | chưa ghi trong design doc → đọc từ plan standard (lệnh §2.3) |
| Plan **trial** | `7c96ca3a-a4dc-4d00-8e32-ee7f8cbaa545` | `09ef641b-74ac-40a0-a92c-06535ea2a96b` |
| Plan **standard** | `ddbffea4-dea0-47d0-89be-f20c25cbd7fb` | `841af476-1046-49c5-8f6d-b6230a06d3c2` |
| Plan **lifetime** | đọc theo `slug=lifetime` (lệnh §2.3) | đọc theo `slug=lifetime` (lệnh §2.3) |

> Product ID staging lấy từ snapshot `plan_*.json` của Phase 1; Production và plan lifetime không được ghi ID trong design doc, nên runbook dùng lệnh đọc read-only để điền biến. **Ghi lại ID đọc được vào bảng này** sau lần chạy đầu để các lần sau dùng trực tiếp.

**Không bao giờ** trỏ khách production vào staging (pubkey và dữ liệu license khác nhau).

---

## 2. Chuẩn bị shell & xác thực

### 2.1 Chọn môi trường + nhập admin key (không hiện màn hình)

```bash
# ===== STAGING =====
export KG=https://stg-license.dtgsoft.vn

# ===== PRODUCTION =====
# export KG=https://license.dtgsoft.vn

read -rsp 'Keygate admin API key: ' KG_ADMIN_KEY; echo
export KG_ADMIN_KEY

# Preflight: Keygate sống + đúng version
curl -sS "$KG/health"
curl -sS "$KG/api/v1/version" | jq .
```

Kỳ vọng version `0.1.20`. Nếu `/health` fail → dừng, không cấp license.

### 2.2 Khai báo plan ID

```bash
# Staging
export TRIAL_PLAN_ID=7c96ca3a-a4dc-4d00-8e32-ee7f8cbaa545
export STANDARD_PLAN_ID=ddbffea4-dea0-47d0-89be-f20c25cbd7fb

# Production
# export TRIAL_PLAN_ID=09ef641b-74ac-40a0-a92c-06535ea2a96b
# export STANDARD_PLAN_ID=841af476-1046-49c5-8f6d-b6230a06d3c2
```

### 2.3 Điền Product ID + Lifetime plan ID (read-only)

```bash
# Product ID suy ra từ plan standard (mọi plan đều có product_id)
export PRODUCT_ID=$(curl -sS "$KG/api/v1/admin/plans/$STANDARD_PLAN_ID" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" | jq -r '.data.product_id')

# Lifetime plan ID theo slug (design doc không ghi ID)
export LIFETIME_PLAN_ID=$(curl -sS "$KG/api/v1/admin/plans?limit=200" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  | jq -r '.data.plans[] | select(.slug == "lifetime") | .id')

printf 'PRODUCT_ID=%s\nLIFETIME_PLAN_ID=%s\n' "$PRODUCT_ID" "$LIFETIME_PLAN_ID"
```

Nếu một biến rỗng → plan/product chưa tồn tại hoặc admin key sai; **không** tự tạo plan mới, liên hệ người quản trị Keygate.

### 2.4 Xác nhận plan đúng cấu hình

```bash
for id in "$TRIAL_PLAN_ID" "$STANDARD_PLAN_ID" "$LIFETIME_PLAN_ID"; do
  curl -sS "$KG/api/v1/admin/plans/$id" \
    -H "Authorization: Bearer $KG_ADMIN_KEY" \
    | jq '{id:.data.id, name:.data.name, slug:.data.slug, type:.data.license_type,
           max_activations:.data.max_activations, grace_days:.data.grace_days,
           token_ttl_days:.data.token_ttl_days}'
done
```

Kỳ vọng: trial/standard/lifetime `max_activations=1`; standard & lifetime `token_ttl_days=7`, `grace_days=15`. Entitlement `max_cameras` (2/4/4) kiểm tra gián tiếp qua `POST /api/v1/license/entitlements` với một license test, hoặc qua `/status` của bản cài.

---

## 3. Mã máy (hardware fingerprint)

### 3.1 Mã máy là gì

DSight gửi **mã máy** làm `identifier` khi activate/verify Keygate. Mã được tính **runtime** từ phần cứng host, không lưu cấu hình:

- Nguồn (đọc qua bind mount `/host/...` trong container):
  - `machine_id` ← `/etc/machine-id`
  - `product_uuid` ← `/sys/class/dmi/id/product_uuid`
  - `board_serial` ← `/sys/class/dmi/id/board_serial` (không phải máy nào cũng có)
- Thuật toán (`server/app/core/license/machine.py`):
  1. Chỉ lấy cặp `key=value` có value khác rỗng (sau `strip()`).
  2. Sắp xếp các chuỗi `key=value`, nối bằng `|`.
  3. SHA-256 → lấy **10 byte đầu** → base32 (bỏ padding) → IN HOA → nhóm 4 ký tự.
  4. Kết quả: `DSIGHT-XXXX-XXXX-XXXX-XXXX` (4 nhóm × 4 ký tự).
- Script `scripts/install_license_identity.sh` (Task 14) chạy **trên host** và tính đúng thuật toán trên để ops đối chiếu; script cũng kiểm tra compose có đủ 2 mount.
- `LICENSE_INSTANCE_ID` trong `.env` **chỉ là override dev**; production để trống. Nếu đặt, giá trị này thắng mã máy và sẽ không còn là hardware fingerprint.

### 3.2 Lấy mã máy trên host khách hàng

```bash
# Chạy trong thư mục checkout/deploy có scripts/ và server/docker-compose.yml
sudo scripts/install_license_identity.sh
```

Kỳ vọng:

```text
=== DSight machine code (mã máy) ===
Nguồn đã dùng: machine_id product_uuid board_serial
OK: /.../server/docker-compose.yml có đủ 2 bind mount read-only cho fingerprint

MÃ MÁY: DSIGHT-7K2M-9QX4-AB12-3C4D
```

- Chạy **không có sudo** thường không đọc được `product_uuid` (quyền `0400 root`) → script cảnh báo và mã máy có thể **khác** mã container tính (container chạy root). Luôn chạy `sudo` để đối chiếu.
- `board_serial` thiếu là bình thường (VM/nhiều mainboard không có) — mã vẫn tính từ machine-id (+ product_uuid nếu có).
- Nếu script báo compose thiếu mount: cập nhật `server/docker-compose.yml` đúng 2 dòng ở §0.1 rồi `docker compose up -d app` (thao tác trên môi trường khách, ngoài phạm vi CI).
- So sánh với trong container (khi đã có mount):
  ```bash
  cd server && docker compose exec app \
    python -c "from app.core.license.machine import resolve_machine_code; print(resolve_machine_code())"
  ```
  Hai kết quả **phải giống nhau**. Nếu khác: kiểm tra script có chạy sudo không, mount có đúng không, và không đặt `LICENSE_INSTANCE_ID`.

### 3.3 Khi nào mã máy đổi

| Tình huống | Mã máy | Việc ops phải làm |
|---|---|---|
| Cài lại app / xoá DB trên **cùng máy**, cùng OS | **Không đổi** | Không cần gì; nhập lại key → `already_activated`, không tốn slot |
| Cài lại OS, systemd sinh `/etc/machine-id` mới | **Đổi** | Xoá activation cũ (§10) rồi activate lại |
| Thay mainboard / DMI `product_uuid`, `board_serial` | **Đổi** | Xoá activation cũ (§10) rồi activate lại |
| Thay ổ cứng nhưng giữ nguyên mainboard/machine-id | Thường **không đổi** | Thử activate; nếu 409 xem §10 |
| Clone VM giữ nguyên `machine-id` + DMI | **Có thể trùng** (giới hạn đã biết) | Đối soát IP/activation khi check-in; nếu cần chặt hơn phải dùng TPM/dongle (ngoài scope) |
| Đặt/đổi `LICENSE_INSTANCE_ID` trong `.env` | **Đổi theo env** | Chỉ dev; production tuyệt đối để trống |

Mã máy đã lưu trong DB khác mã máy tính lại → backend đánh dấu `invalid` + `last_error='machine changed'`, **không** tự đổi identifier. Phải xoá activation cũ trên Keygate rồi activate lại (§10).

---

## 4. Cấp license trial

**Dùng khi:** PoC/demo 30 ngày, chưa ký hợp đồng. Trial có `max_cameras=2` (khớp 2 camera seed của bản cài mới), 1 máy, hard-stop đúng `valid_until`.

```bash
# TODO thay thông tin khách + ngày kết thúc PoC
CUSTOMER_CODE='DTG-BASON-001'
CONTACT_EMAIL='ops@bason.example'
TRIAL_UNTIL='2026-12-09T23:59:59+07:00'   # RFC3339, phải ở tương lai

resp=$(curl -sS -X POST "$KG/api/v1/admin/licenses" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{
    \"product_id\": \"$PRODUCT_ID\",
    \"plan_id\": \"$TRIAL_PLAN_ID\",
    \"email\": \"$CONTACT_EMAIL\",
    \"valid_until\": \"$TRIAL_UNTIL\",
    \"external_customer_id\": \"$CUSTOMER_CODE\",
    \"notes\": \"PoC 30 ngày — hợp đồng/ngày kết thúc; ops=<tên>\"
  }")

printf '%s\n' "$resp" | jq '{id:.data.id, status:.data.status, email:.data.email,
  plan_id:.data.plan_id, valid_until:.data.valid_until, license_key:.data.license_key}'
LICENSE_ID=$(printf '%s' "$resp" | jq -r '.data.id')
LICENSE_KEY=$(printf '%s' "$resp" | jq -r '.data.license_key')
```

- `license_key` **chỉ trả về ở response này** (và ở rotate-key). Chuyển khách qua kênh an toàn (email tới địa chỉ trên license là best-effort của Keygate; nếu chưa chắc, gửi tay qua kênh bảo mật). Không dán key vào chat nhóm/ticket.
- Ghi `LICENSE_ID` vào hồ sơ khách; **không** ghi key vào file/repo.
- Gắn addon camera nếu PoC cần >2 camera: §7.
- Khách nhập key ở màn hình first-run sau khi đăng nhập admin (màn hình hiện `machine_code` để đối chiếu).
- Trial không có luồng gia hạn thương mại; muốn kéo dài PoC thì dời `valid_until` bằng `valid-until`, còn khách tiếp tục trả phí thì chuyển standard/lifetime (§9).

---

## 5. Cấp license standard

**Dùng khi:** khách ký hợp đồng năm. Standard baseline `max_cameras=4`, 1 máy, `valid_until` = ngày hết hợp đồng (đặt tay), `grace_days=15`, token TTL 7 ngày.

```bash
CUSTOMER_CODE='DTG-BASON-001'
CONTACT_EMAIL='ops@bason.example'
CONTRACT_UNTIL='2027-12-31T23:59:59+07:00'   # ngày hết HĐ, RFC3339 tương lai

resp=$(curl -sS -X POST "$KG/api/v1/admin/licenses" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{
    \"product_id\": \"$PRODUCT_ID\",
    \"plan_id\": \"$STANDARD_PLAN_ID\",
    \"email\": \"$CONTACT_EMAIL\",
    \"valid_until\": \"$CONTRACT_UNTIL\",
    \"external_customer_id\": \"$CUSTOMER_CODE\",
    \"notes\": \"HĐ <số HĐ> — hết hạn <ngày>; camera=<N>\"
  }")

printf '%s\n' "$resp" | jq '{id:.data.id, status:.data.status, email:.data.email,
  plan_id:.data.plan_id, valid_until:.data.valid_until, license_key:.data.license_key}'
LICENSE_ID=$(printf '%s' "$resp" | jq -r '.data.id')
LICENSE_KEY=$(printf '%s' "$resp" | jq -r '.data.license_key')
```

Sau khi cấp: gắn addon camera đúng số khách mua (§7) — baseline 4 chỉ là mức bao gồm trong gói; khách mua 6/12/20 camera phải có addon `max_cameras=N`.

---

## 6. Cấp license lifetime

**Dùng khi:** khách mua vĩnh viễn. Plan `lifetime` là `perpetual`; **không truyền `valid_until`** trong request (không gửi `null`, không gửi chuỗi rỗng — bỏ hẳn field). Vẫn 1 máy + addon camera; vẫn suspend/revoke được khi vi phạm hợp đồng.

```bash
CUSTOMER_CODE='DTG-BASON-001'
CONTACT_EMAIL='ops@bason.example'

resp=$(curl -sS -X POST "$KG/api/v1/admin/licenses" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{
    \"product_id\": \"$PRODUCT_ID\",
    \"plan_id\": \"$LIFETIME_PLAN_ID\",
    \"email\": \"$CONTACT_EMAIL\",
    \"external_customer_id\": \"$CUSTOMER_CODE\",
    \"notes\": \"Lifetime — HĐ <số HĐ>; camera=<N>\"
  }")

printf '%s\n' "$resp" | jq '{id:.data.id, status:.data.status, plan_id:.data.plan_id,
  valid_until:.data.valid_until, license_key:.data.license_key}'
LICENSE_ID=$(printf '%s' "$resp" | jq -r '.data.id')
LICENSE_KEY=$(printf '%s' "$resp" | jq -r '.data.license_key')
```

Kỳ vọng `valid_until: null` (perpetual). Nếu vô tình truyền `valid_until`, license sẽ hết hạn theo ngày đó — phải sửa bằng `valid-until` rỗng (`{"valid_until":""}`) hoặc tạo lại license (không xoá license cũ; revoke nếu cần).

---

## 7. Addon số camera theo từng khách

Quy ước (design §5.2):

- Mỗi khách trả phí có **đúng 1 addon camera riêng**:
  - `name`: `Camera limit — <MÃ_KH>`
  - `slug`: `camera-<ma-kh>` (chữ thường, ví dụ `camera-dtg-bason-001`)
  - `feature`: `max_cameras`
  - `value_type`: `int`
  - `value`: `"<N>"` — **string** theo API
- Addon **chỉ gắn cho đúng 1 license** (1 khách = 1 license = 1 addon). Không dùng chung addon giữa 2 khách.
- Addon thay thế entitlement cùng tên của plan (không cộng dồn).

### 7.1 Tạo addon (một lần cho mỗi khách)

```bash
CUSTOMER_CODE='DTG-BASON-001'
CUSTOMER_SLUG='dtg-bason-001'   # lowercase
CAMERA_COUNT='12'               # số camera khách mua

addon_resp=$(curl -sS -X POST "$KG/api/v1/admin/addons" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{
    \"product_id\": \"$PRODUCT_ID\",
    \"name\": \"Camera limit — $CUSTOMER_CODE\",
    \"slug\": \"camera-$CUSTOMER_SLUG\",
    \"description\": \"Giới hạn camera theo hợp đồng $CUSTOMER_CODE\",
    \"feature\": \"max_cameras\",
    \"value_type\": \"int\",
    \"value\": \"$CAMERA_COUNT\"
  }")

printf '%s\n' "$addon_resp" | jq '{id:.data.id, name:.data.name, slug:.data.slug,
  feature:.data.feature, value_type:.data.value_type, value:.data.value}'
ADDON_ID=$(printf '%s' "$addon_resp" | jq -r '.data.id')
```

### 7.2 Gắn addon vào license

```bash
curl -sS -X POST "$KG/api/v1/admin/licenses/$LICENSE_ID/addons" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"addon_id\": \"$ADDON_ID\"}" | jq .
```

### 7.3 Kiểm tra addon đang gắn

```bash
curl -sS "$KG/api/v1/admin/licenses/$LICENSE_ID/addons?limit=200" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" | jq '.data.addons'
```

### 7.4 Đổi số camera của khách

Vì mỗi addon chỉ gắn 1 license, sửa `value` là an toàn:

```bash
NEW_CAMERA_COUNT='16'

curl -sS -X PUT "$KG/api/v1/admin/addons/$ADDON_ID" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"value\": \"$NEW_CAMERA_COUNT\"}" | jq '{id:.data.id, value:.data.value}'
```

Khách không cần thao tác: lần verify kế tiếp (mặc định mỗi 6 giờ) nhận giá trị mới; muốn ngay thì admin bấm refresh qua API §14.1 (`POST /api/v1/license/refresh`). Nếu cần tuyệt đối an toàn (addon lỡ gắn nhiều license), tạo addon mới + attach + detach addon cũ theo đúng thứ tự.

### 7.5 Tháo addon

```bash
curl -sS -X DELETE "$KG/api/v1/admin/licenses/$LICENSE_ID/addons/$ADDON_ID" \
  -H "Authorization: Bearer $KG_ADMIN_KEY"
```

Sau khi tháo, quyền `max_cameras` quay về baseline của plan (2 trial / 4 standard & lifetime), **không** về 0. Không xoá addon (`DELETE /admin/addons/{id}`) khi còn license dùng — FK cascade làm mất feature.

---

## 8. Gia hạn standard

**Dùng khi:** khách thanh toán/gia hạn hợp đồng năm. Standard tự nhận hạn mới ở lần check-in sau; **khách không cần cài lại hay nhập lại key**.

```bash
NEW_UNTIL='2028-12-31T23:59:59+07:00'   # RFC3339, bắt buộc ở tương lai

curl -sS -X POST "$KG/api/v1/admin/licenses/$LICENSE_ID/valid-until" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"valid_until\": \"$NEW_UNTIL\"}" | jq .
```

- `valid_until` phải ở **tương lai**; Keygate từ chối ngày quá khứ (muốn dừng ngay thì dùng `suspend`/`revoke`, không backdate).
- License đã quá hạn nhưng còn trong grace, hoặc đã `expired` quá grace: sau khi set hạn mới, lần verify kế tiếp đưa về `active` (test T9).
- Không dùng cho license còn gắn Stripe subscription (Keygate trả `409 STRIPE_MANAGED`) — DSight không dùng Stripe, nên bình thường không gặp.
- Kiểm tra sau gia hạn: `GET /api/v1/license/status` phía khách thấy `valid_until` mới và `days_left` tăng.

---

## 9. Chuyển trial → trả phí

Chuyển **giữ nguyên license key + activation**, khách không phải cài lại hay nhập lại key.

```bash
# 1) Đổi plan trước
curl -sS -X POST "$KG/api/v1/admin/licenses/$LICENSE_ID/change-plan" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"plan_id\": \"$STANDARD_PLAN_ID\"}" | jq .

# 2) Đặt hạn hợp đồng
CONTRACT_UNTIL='2027-12-31T23:59:59+07:00'
curl -sS -X POST "$KG/api/v1/admin/licenses/$LICENSE_ID/valid-until" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"valid_until\": \"$CONTRACT_UNTIL\"}" | jq .

# 3) Gắn/đổi addon camera nếu số camera khác baseline standard (4) — §7
```

- Làm **trước** khi trial hết hạn để không bị hard-stop ngoài giờ.
- `change-plan` chỉ chấp nhận plan cùng product; nếu chuyển sang `lifetime` thì bỏ bước `valid-until` (perpetual).
- Kiểm tra Keygate: `GET /api/v1/admin/licenses/$LICENSE_ID` → `plan_id`, `valid_until`, `status`; phía khách: `POST /api/v1/license/refresh` rồi `GET /status`.

---

## 10. Cài lại / đổi máy / thay phần cứng

### 10.1 Nguyên tắc

- **Cùng máy + cùng định danh phần cứng → cùng mã máy.** Cài lại app/xoá DB không đổi mã; nhập lại đúng key sẽ trả `already_activated`, **không tốn slot**, không cần ops làm gì.
- **Mã máy đổi** (OS mới sinh machine-id, thay mainboard/DMI, đổi `LICENSE_INSTANCE_ID`, clone khác cấu hình) → activation cũ vẫn gắn với mã cũ; verify trả **404** (chưa activate máy này) và backend đánh dấu `invalid`.
- **Không nâng `max_activations` lên 2.** Luôn giải phóng activation cũ bằng `DELETE /admin/activations/{id}`.
- Keygate **không xoá license**; xoá activation không ảnh hưởng license/hạn dùng.

### 10.2 Quy trình chuẩn (máy mới/đổi phần cứng)

```bash
# 1) Trên host khách: lấy mã máy mới (chạy sudo)
#    sudo scripts/install_license_identity.sh   → DSIGHT-...

# 2) Tìm license theo mã khách
curl -sS "$KG/api/v1/admin/licenses?external_customer_id=DTG-BASON-001&limit=200" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  | jq '.data.licenses[] | {id, status, plan:.plan_id, valid_until, external_customer_id}'
LICENSE_ID='<id ở trên>'

# 3) Xem activation cũ (identifier chính là mã máy)
curl -sS "$KG/api/v1/admin/licenses/$LICENSE_ID" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  | jq '.data.activations[] | {id, identifier, label, ip_address, created_at, last_verified}'
ACTIVATION_ID='<id của activation cũ cần xoá>'

# 4) Giải phóng slot (KHÔNG xoá license)
curl -sS -X DELETE "$KG/api/v1/admin/activations/$ACTIVATION_ID" \
  -H "Authorization: Bearer $KG_ADMIN_KEY"

# 5) Xác nhận không còn activation cũ
curl -sS "$KG/api/v1/admin/licenses/$LICENSE_ID" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" | jq '.data.activations'
```

### 10.3 Nhập lại key sau khi giải phóng slot

- **Cài mới hoàn toàn / DB mới:** trạng thái `unlicensed` → màn hình nhập key first-run hiện ra; đăng nhập admin, nhập key, bấm Kích hoạt. Activation mới mang mã máy mới.
- **Giữ DB cũ (thay phần cứng):** backend đã đánh dấu `invalid`; UI tối giản hiện tại **chỉ** hiện màn hình first-run khi `unlicensed`, nên dùng API admin để nhập lại key:
  ```bash
  # Đăng nhập DSight lấy access token (không đưa password vào history: dùng read -rs)
  DSIGHT='https://dock.khach-hang.example'
  read -rsp 'DSight admin username: ' DS_USER; echo
  read -rsp 'DSight admin password: ' DS_PASS; echo
  TOKEN=$(curl -sS -X POST "$DSIGHT/api/v1/auth/login" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode "username=$DS_USER" --data-urlencode "password=$DS_PASS" \
    | jq -r '.access_token')

  curl -sS -X POST "$DSIGHT/api/v1/license/activate" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"license_key":"<KEY>","label":"Thay phần cứng"}' | jq .
  ```
  Kỳ vọng `status: valid`, `machine_code` = mã mới. Nếu key cũ bị lộ/hết hạn thì rotate trước (§12) rồi dùng key mới.
- Cách khác cho reinstall sạch: xoá luôn volume DB → app tạo DB mới → `unlicensed` → first-run screen (chỉ làm khi chấp nhận mất dữ liệu; không phải quy trình chuẩn).

### 10.4 Lỗi thường gặp

| Lỗi | Nguyên nhân | Xử lý |
|---|---|---|
| `409 ACTIVATION_LIMIT` | Slot còn activation cũ (chưa xoá đúng), hoặc license đã activate máy khác | Liệt kê `.data.activations`, xoá đúng activation cũ; không tăng `max_activations` |
| Verify `404` | Máy chưa activate / activation cũ chưa xoá / key sai | Đối chiếu `identifier` với mã máy script; xoá activation cũ rồi activate |
| `status: invalid`, `last_error: machine changed` | Mã máy khác `instance_id` đã lưu | Xoá activation cũ + activate lại (§10.2–10.3) |
| Mã máy script khác container | Script chạy non-root không đọc được DMI, hoặc thiếu mount | Chạy `sudo`; kiểm tra 2 mount; không đặt `LICENSE_INSTANCE_ID` |

---

## 11. Suspend / reinstate / revoke

### 11.1 Tạm ngưng (chưa thanh toán) — `suspend`

Giữ activation, chặn license **ngay** (không grace). Pipeline **đang chạy không bị dừng**; chế độ `enforce` chỉ chặn start mới + tạo camera vượt quota.

```bash
curl -sS -X POST "$KG/api/v1/admin/licenses/$LICENSE_ID/suspend" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" | jq .
```

Khách nhận hiệu lực ở lần check-in kế tiếp (≤6h) hoặc refresh ngay (§14.1). Verify trả 404; DSight phân loại qua `activate` → banner "tạm ngưng".

### 11.2 Mở lại — `reinstate`

```bash
curl -sS -X POST "$KG/api/v1/admin/licenses/$LICENSE_ID/reinstate" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" | jq .
```

License tự hoạt động lại sau check-in; muốn ngay thì refresh phía khách. Nếu license đã hết hạn trong lúc suspend, có thể cần gia hạn `valid-until` trước/sau reinstate.

### 11.3 Thu hồi — `revoke` (terminal)

```bash
curl -sS -X POST "$KG/api/v1/admin/licenses/$LICENSE_ID/revoke" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" | jq .
```

- Revoke **không thể hoàn tác**, activation bị xoá, key chết. Muốn phục vụ lại phải cấp license mới.
- Chỉ dùng khi chấm dứt hợp đồng/vi phạm; trước đó lưu `GET /admin/licenses/export` để đối soát.
- Keygate không xoá license — dữ liệu/audit vẫn còn.

---

## 12. Rotate key khi lộ key

```bash
curl -sS -X POST "$KG/api/v1/admin/licenses/$LICENSE_ID/rotate-key" \
  -H "Authorization: Bearer $KG_ADMIN_KEY" \
  | jq '{license_key:.data.license_key, devices_removed:.data.devices_removed}'
```

- Key cũ **chết ngay**, toàn bộ activation cũ bị xoá (`devices_removed`), slot được giải phóng.
- Key mới chỉ trả về trong response này; gửi khách qua kênh an toàn.
- Khách nhập key mới: màn hình first-run nếu DB mới/unlicensed; nếu DB cũ đang `invalid`, dùng `POST /api/v1/license/activate` như §10.3.
- Sau rotate, kiểm tra license `status` vẫn `active`/`trialing` và chưa có activation cũ.

---

## 13. Đổi enforcement mode qua API (không có UI)

DSight có 3 mode:

| Mode | Hành vi |
|---|---|
| `off` | Không kiểm tra/không chặn (vẫn verify nền để cập nhật trạng thái) |
| `warn` (mặc định khi tạo DB lần đầu) | Chỉ log/cảnh báo; không chặn tạo camera/pipeline |
| `enforce` | Chặn **hành vi mới**: tạo camera vượt `max_cameras` → 403 `CAMERA_LIMIT`; start pipeline khi license không dùng được → 403. **Không** chặn login/đọc dữ liệu/stop/WS/pipeline đang chạy |

`LICENSE_ENFORCEMENT` trong `.env` **chỉ là default lúc tạo row `license_state` lần đầu**; giá trị hiệu lực lưu DB và đổi runtime bằng API (không cần sửa `.env`/restart). Mọi thay đổi đi qua audit middleware của DSight.

```bash
DSIGHT='https://dock.khach-hang.example'
read -rsp 'DSight admin username: ' DS_USER; echo
read -rsp 'DSight admin password: ' DS_PASS; echo

TOKEN=$(curl -sS -X POST "$DSIGHT/api/v1/auth/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "username=$DS_USER" --data-urlencode "password=$DS_PASS" \
  | jq -r '.access_token')

# Xem mode hiện tại
curl -sS "$DSIGHT/api/v1/license/status" \
  -H "Authorization: Bearer $TOKEN" | jq '{status, plan_name, valid_until, days_left,
  features, enforcement_mode, machine_code, last_error}'

# Đổi mode (admin)
curl -sS -X PUT "$DSIGHT/api/v1/license/enforcement" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"enforce"}' | jq .
# → {"mode":"enforce"}

# Rollback nhanh
curl -sS -X PUT "$DSIGHT/api/v1/license/enforcement" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"warn"}' | jq .
```

Rollout khuyến nghị: ship `warn` → theo dõi 1–2 tuần không false-positive → `enforce` cho pilot → rollout. Endpoint cần role admin; 401 = token hết hạn/thiếu, 403 = không phải admin.

---

## 14. Kiểm tra phía khách hàng & probe staging

### 14.1 API DSight (cần access token admin)

```bash
# Trạng thái đầy đủ (auth thường cũng xem được /status)
curl -sS "$DSIGHT/api/v1/license/status" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Verify lại ngay với Keygate (admin) — hữu ích sau renew/đổi addon/reinstate
curl -sS -X POST "$DSIGHT/api/v1/license/refresh" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Chi tiết state + last_error (admin)
curl -sS "$DSIGHT/api/v1/license/" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

`/status` trả: `status`, `plan_name`, `valid_until`, `days_left`, `grace_days`, `features`, `enforcement_mode`, `instance_id`, `machine_code`, `license_key_hint` (4 ký tự cuối), `last_verified_at`, `last_error`.

Trạng thái hiệu lực: `unlicensed | valid | grace | expired | suspended | revoked | invalid`.

### 14.2 Probe Keygate (dev/ops)

Script `server/scripts/license_probe.py` gọi thẳng Keygate (không qua DSight) để kiểm tra một key + identifier:

```bash
cd server

# Probe trên staging với license tạm (KHÔNG dùng key khách thật)
LICENSE_PROBE_URL=https://stg-license.dtgsoft.vn \
LICENSE_PROBE_KEY='<key>' \
python scripts/license_probe.py
```

- Env tuỳ chọn `LICENSE_PROBE_IDENTIFIER`; mặc định `probe-<uuid4>` (mỗi lần chạy là "máy" mới — license 1 activation sẽ báo `409 ACTIVATION_LIMIT` nếu chạy lại; đặt identifier cố định hoặc dùng license throwaway).
- Kỳ vọng trial: `status: active`/`trialing`, `features: {"max_cameras": "2"}`, `token: OK (...)`, `PROBE OK`, exit 0.
- Script **không in license key**; mọi lỗi được redact. Exit 2 = thiếu env; exit 1 = API/token lỗi.
- Dọn dẹp sau probe: revoke license tạm (`POST /admin/licenses/{id}/revoke`) hoặc xoá activation probe (`DELETE /admin/activations/{id}`). Không để license probe/activation rác.
- **Không chạy probe bằng license thật của khách** (nó tạo activation mới, có thể chiếm slot 1 máy).

### 14.3 Khi mất mạng/Keygate down

- DSight dùng token cache đã lưu; license giữ trạng thái tới khi token hết hạn (`exp`, bị clamp theo `valid_until + grace_days`).
- Timeout/5xx/mất mạng = lỗi tạm thời: giữ cache, ghi `last_error`, **không** đánh invalid ngay.
- Verify **404** mới là câu trả lời dứt khoát của server → invalid ngay.
- App vẫn boot/login/đọc dữ liệu; `enforce` chỉ chặn hành vi mới nếu license không dùng được.

---

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `POST /license/activate` trả **404** | Key sai/không tồn tại | Kiểm tra đúng key/product; key chỉ có ở response create/rotate. `GET /admin/licenses/{id}/key` để reveal (có audit, hạn chế dùng) |
| Verify **404** nhưng key đúng | Máy chưa activate; mã máy đổi; activation cũ chưa xoá; license suspended/revoked/hết hạn quá grace | `POST /license/activate` với key đã lưu: 403 `LICENSE_SUSPENDED/REVOKED/EXPIRED/CANCELED` cho biết lý do; 404 = key không dùng được/chưa activate máy này. Đối chiếu identifier + xoá activation cũ nếu cần |
| `409 ACTIVATION_LIMIT` | Đã activate máy khác; activation cũ chưa xoá | `GET /admin/licenses/{id}` → xoá `DELETE /admin/activations/{id}`; **không** tăng max_activations |
| `403 CAMERA_LIMIT` (enforce) | Tổng camera rows ≥ `max_cameras` (kể cả inactive) | Xoá bớt camera hoặc tăng addon `value` (khách mua thêm); refresh license |
| Timeout / connection error | Không có outbound 443, DNS, proxy, TLS | `curl -v "$KG/health"` từ chính host/container; kiểm tra firewall/proxy; license vẫn chạy bằng cache |
| Keygate trả 5xx | Keygate quá tải/lỗi | Thử lại sau; app giữ cache; theo dõi `/health` Keygate |
| `429` | Rate limit | Backoff theo `Retry-After`; mỗi bản cài chỉ check-in 6h/lần nên hiếm |
| Token “hết hạn” ngay sau activate | Lệch đồng hồ máy khách (NTP) | `timedatectl`/`date -u`; bật NTP; kiểm tra timezone chỉ ảnh hưởng hiển thị, `exp` là UTC |
| Không thấy màn hình nhập key | UI chỉ hiện first-run khi `status=unlicensed`; `invalid/suspended/revoked/expired` không hiện form | Dùng API `POST /license/activate` (admin) hoặc xử lý nguyên nhân trạng thái trước; xem `/status.last_error` |
| `last_error: machine changed` | Mã máy khác `instance_id` DB | Xoá activation cũ + activate lại (§10) |
| `last_error: ... can not decrypt` / mất key | `SECRET_KEY` bị đổi sau khi lưu key | Set lại `SECRET_KEY` cũ nếu biết, hoặc khách nhập lại license key (key không mất trên Keygate) |
| `GET /api/v1/license` trả 307 | Thiếu dấu `/` cuối | Dùng `/api/v1/license/` hoặc `/status` |
| 401/403 trên API DSight | Token hết hạn / không phải admin | Login lại; kiểm tra role; enforcement/refresh/activate cần admin |
| Addon không có hiệu lực | Chưa attach, sai product, license cache chưa refresh | `GET /licenses/{id}/addons`; attach đúng; `POST /license/refresh` |
| `delete plan/addon` bị chặn | Còn license/addon tham chiếu | Không xoá; detach/suspend/revoke theo quy trình |

**Đọc log DSight:** `server/logs/app.log` (hoặc `LOG_FILE_PATH`) lọc `license`; log không chứa key (chỉ hint/last_error).

---

## 16. Bảo mật

### 16.1 Admin API key (Keygate)

- Chỉ 1–2 người ops giữ key scope `admin`; lưu trong secret manager (1Password/Bitwarden/Vault), **không** trong repo, `.env`, chat, ticket, shell history.
- Khi nhập: `read -rsp` (như §2.1), tránh `export KG_ADMIN_KEY=...` trực tiếp trong history.
- Dùng key riêng cho automation nếu có: scope `licenses:write` + bind product, không dùng key `admin` cho script định kỳ.
- Rotate định kỳ qua Keygate: `POST /api/v1/admin/api-keys/{id}/rotate` (hoặc tạo key mới rồi xoá key cũ); thu hồi ngay khi người giữ key rời đi.
- Keygate admin key **không phải** license key và không được gửi cho khách.

### 16.2 License key

- Key chỉ xuất hiện ở response `POST /admin/licenses` và `POST /admin/licenses/{id}/rotate-key` (và endpoint reveal có audit). Gửi khách qua kênh an toàn (email tới địa chỉ trên license; nếu không chắc thì bàn giao trực tiếp).
- **Không** commit key, không dán vào issue/chat, không ghi file `.txt`/`.env`. Không đặt `LICENSE_KEY` trong `server/.env` — file bị bake vào image và dễ lộ; DSight lưu key trong DB đã mã hoá Fernet, chỉ trả `license_key_hint` (4 ký tự cuối).
- Không log key: DSight không log key (chỉ hint/last_error); probe cũng redact. Keygate tự redact log phía server.
- Khi nghi lộ: `rotate-key` ngay (§12); key cũ chết tức thì.

### 16.3 `SECRET_KEY` và dữ liệu at-rest

- `SECRET_KEY` (server/.env) là đầu vào dẫn xuất Fernet key mã hoá license key trong bảng `license_state`. **Không dùng giá trị mặc định `secret`** (public trong source) và không dùng lại key của hệ thống khác.
- Đổi `SECRET_KEY` = ciphertext cũ không giải mã được → app coi như chưa có key, khách phải nhập lại license key. Không mất dữ liệu nghiệp vụ khác.
- Backup `server/.env` cùng secret manager; không đưa `SECRET_KEY` vào image public.

### 16.4 Hạ tầng

- HTTPS bắt buộc tới `license.dtgsoft.vn` (TLS verify mặc định của `requests`); không tắt verify.
- NTP trên máy khách và server Keygate; token `exp` là mốc tuyệt đối.
- Backup định kỳ: PostgreSQL của Keygate (license/activation/audit) + DB DSight (`license_state`). Kiểm tra restore định kỳ.
- Đối soát hằng tháng: `GET /api/v1/admin/licenses/export` (CSV/JSON) lưu hồ sơ, so với danh sách cảng đang chạy; rà license hết hạn ≤60 ngày để sales gia hạn.
  - ⚠️ Export chứa **license key dạng plaintext** (mục đích migrate off Keygate) và được Keygate audit mỗi lần tải. Chỉ người được phép tải; lưu file đã mã hoá/secret manager, không để trong thư mục share, không gửi qua chat; xoá bản tạm sau đối soát.
- Không white-label/xoá attribution Keygate (AGPL) trong admin UI nội bộ.

---

## 17. Phụ lục: bản đồ API & mẫu bảng khách hàng

### 17.1 Keygate SDK (DSight gọi)

| Mục đích | Endpoint |
|---|---|
| Activate | `POST /api/v1/license/activate` `{license_key, identifier, label}` |
| Verify | `POST /api/v1/license/verify` `{license_key, identifier}` |
| Entitlements | `POST /api/v1/license/entitlements` `{license_key}` |
| Public key Ed25519 | `GET /api/v1/license/pubkey` |

Response verify có `status, plan_id, plan_name, valid_until, features, token, grace_days`; int/quota trong `features` là **string** (`"max_cameras": "12"`), bool là boolean.

### 17.2 Keygate admin (ops gọi)

| Mục đích | Endpoint |
|---|---|
| Tạo license | `POST /api/v1/admin/licenses` |
| Danh sách/tìm license | `GET /api/v1/admin/licenses?external_customer_id=...&limit=200` |
| Chi tiết license + activations | `GET /api/v1/admin/licenses/{id}` |
| Reveal key (audit) | `GET /api/v1/admin/licenses/{id}/key` |
| Gia hạn | `POST /api/v1/admin/licenses/{id}/valid-until` |
| Đổi plan (trial→paid/lifetime) | `POST /api/v1/admin/licenses/{id}/change-plan` |
| Suspend / reinstate / revoke | `POST /api/v1/admin/licenses/{id}/suspend` · `/reinstate` · `/revoke` |
| Rotate key | `POST /api/v1/admin/licenses/{id}/rotate-key` |
| Xoá activation (giải phóng máy) | `DELETE /api/v1/admin/activations/{id}` |
| Tạo/sửa/xoá addon | `POST /api/v1/admin/addons` · `PUT/DELETE /api/v1/admin/addons/{id}` |
| Gắn/tháo addon | `POST /api/v1/admin/licenses/{id}/addons` · `DELETE .../addons/{addon_id}` |
| Entitlement plan | `POST/PUT/DELETE /api/v1/admin/entitlements` |
| Plans/products | `GET /api/v1/admin/plans` · `GET /api/v1/admin/products` |
| Export đối soát (⚠️ chứa key plaintext) | `GET /api/v1/admin/licenses/export?format=json` |

Wrapper: thành công `{"success":true,"data":...}`; danh sách nằm ở `.data.<tên>` (`licenses`, `plans`, `addons`) kèm `total/limit/offset`.

### 17.3 DSight license API

| Mục đích | Endpoint | Quyền |
|---|---|---|
| Trạng thái cho FE | `GET /api/v1/license/status` | đăng nhập |
| Chi tiết state | `GET /api/v1/license/` | admin |
| Nhập/kích hoạt key | `POST /api/v1/license/activate` | admin |
| Verify lại ngay | `POST /api/v1/license/refresh` | admin |
| Đổi enforcement mode | `PUT /api/v1/license/enforcement` | admin |

### 17.4 Mẫu bảng khách hàng (điền khi cấp license)

| Mã KH | Tên khách | License ID | Plan | Camera (N) | Addon ID | `valid_until` | Ngày cấp | HĐ/ghi chú |
|---|---|---|---|---|---|---|---|---|
| DTG-BASON-001 | Bason | | standard | 12 | | 2027-12-31 | 2026-11-09 | HĐ 001/2026 |

> Không ghi license key vào bảng này. Key lưu trong secret manager/kênh bàn giao an toàn.

### 17.5 Checklist nhanh khi cấp license mới

- [ ] Xác định plan (trial/standard/lifetime) + số camera + ngày hết hạn.
- [ ] Chọn đúng môi trường (`stg-` hay production), `$KG`/key đúng.
- [ ] `POST /admin/licenses` (lifetime: **không** gửi `valid_until`).
- [ ] Lưu `LICENSE_ID`; gửi key khách qua kênh an toàn; ghi bảng khách hàng.
- [ ] Tạo + attach addon camera nếu N ≠ baseline (§7).
- [ ] Khách cài đặt, đăng nhập admin, nhập key ở first-run; kiểm tra `GET /license/status` → `status=valid`, đúng `machine_code`, `features.max_cameras`.
- [ ] Đối chiếu Keygate `GET /admin/licenses/{id}` có activation đúng identifier.
- [ ] Với trial: nhắc khách/ops ngày hết hạn trước 7 ngày; chuyển standard trước khi hết hạn nếu tiếp tục.

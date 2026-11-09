#!/usr/bin/env bash
# install_license_identity.sh — chạy trên HOST của khách hàng (KHÔNG chạy trong container).
#
# Mục đích:
#   1. Đọc các định danh phần cứng đúng như server/app/core/license/machine.py:
#        /etc/machine-id
#        /sys/class/dmi/id/product_uuid   (thường chỉ root đọc được)
#        /sys/class/dmi/id/board_serial   (không phải máy nào cũng có)
#   2. Tính "mã máy" (hardware fingerprint) DSIGHT-XXXX-XXXX-XXXX-XXXX:
#        - chỉ lấy cặp key=value khác rỗng
#        - sắp xếp chuỗi key=value, nối bằng '|'
#        - SHA-256, lấy 10 byte đầu, base32 (bỏ padding, IN HOA), nhóm 4 ký tự
#   3. Kiểm tra docker-compose của app có bind mount read-only cho fingerprint.
#   4. Cảnh báo nếu product_uuid/board_serial không đọc được (nên chạy bằng sudo).
#
# Script chỉ đọc file và in ra màn hình — KHÔNG ghi secret, KHÔNG sửa file nào.
# Cài lại trên cùng máy cho cùng mã; đổi phần cứng/ổ đĩa có thể ra mã khác
# (khi đó ops phải xoá activation cũ trên Keygate — xem runbook).
#
# Dùng:
#   sudo scripts/install_license_identity.sh
#   COMPOSE_FILE=/duong/dan/docker-compose.yml sudo -E scripts/install_license_identity.sh
#
# Có thể override đường dẫn để test: MACHINE_ID_FILE, PRODUCT_UUID_FILE, BOARD_SERIAL_FILE.
set -u

export LC_ALL=C

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 1
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P) || exit 1
COMPOSE_FILE=${COMPOSE_FILE:-"$REPO_ROOT/server/docker-compose.yml"}

MACHINE_ID_FILE=${MACHINE_ID_FILE:-/etc/machine-id}
PRODUCT_UUID_FILE=${PRODUCT_UUID_FILE:-/sys/class/dmi/id/product_uuid}
BOARD_SERIAL_FILE=${BOARD_SERIAL_FILE:-/sys/class/dmi/id/board_serial}

warn() {
  printf 'CẢNH BÁO: %s\n' "$*" >&2
}

fail() {
  printf 'LỖI: %s\n' "$*" >&2
  exit 1
}

trim() {
  # Bỏ khoảng trắng đầu/cuối giống str.strip() của Python (file định danh là 1 dòng).
  printf '%s' "$1" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

read_identity() {
  # read_identity <file>: in giá trị đã trim; file thiếu/rỗng/không đọc được → rc 1.
  file=$1
  [ -r "$file" ] || return 1
  value=$(cat "$file" 2>/dev/null) || return 1
  value=$(trim "$value")
  [ -n "$value" ] || return 1
  printf '%s' "$value"
}

hash_to_base32() {
  # stdin → 10 byte đầu SHA-256 → base32 không padding, IN HOA (16 ký tự).
  if command -v openssl >/dev/null 2>&1 && command -v base32 >/dev/null 2>&1; then
    openssl dgst -sha256 -binary | head -c 10 | base32 | tr -d '=\n' | tr '[:lower:]' '[:upper:]'
    return $?
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import base64, hashlib, sys
data = sys.stdin.buffer.read()
print(base64.b32encode(hashlib.sha256(data).digest()[:10]).decode("ascii").rstrip("=").upper())'
    return $?
  fi

  return 1
}

check_compose_mounts() {
  if [ ! -f "$COMPOSE_FILE" ]; then
    warn "không thấy compose file: $COMPOSE_FILE — bỏ qua kiểm tra mount (đặt COMPOSE_FILE nếu file ở chỗ khác)"
    return 1
  fi

  missing=''
  grep -Fq '/etc/machine-id:/host/etc/machine-id:ro' "$COMPOSE_FILE" ||
    missing="$missing /etc/machine-id"
  grep -Fq '/sys/class/dmi/id:/host/sys/class/dmi/id:ro' "$COMPOSE_FILE" ||
    missing="$missing /sys/class/dmi/id"

  if [ -n "$missing" ]; then
    warn "docker-compose thiếu bind mount read-only:$missing"
    warn "app sẽ không đọc được fingerprint và fallback sang UUID lưu DB (chỉ nên xảy ra ở dev)"
    return 1
  fi

  printf 'OK: %s có đủ 2 bind mount read-only cho fingerprint\n' "$COMPOSE_FILE"
  return 0
}

machine_id=$(read_identity "$MACHINE_ID_FILE") || machine_id=''
product_uuid=$(read_identity "$PRODUCT_UUID_FILE") || product_uuid=''
board_serial=$(read_identity "$BOARD_SERIAL_FILE") || board_serial=''

if [ -z "$machine_id" ]; then
  warn "không đọc được $MACHINE_ID_FILE (file thiếu/rỗng/không có quyền đọc)"
fi
if [ -z "$product_uuid" ]; then
  warn "không đọc được $PRODUCT_UUID_FILE — DMI product_uuid thường cần root; hãy chạy lại bằng sudo"
  warn "nếu chạy không có quyền, mã máy có thể KHÁC mã container tính (container chạy root)"
fi
if [ -z "$board_serial" ]; then
  warn "không đọc được $BOARD_SERIAL_FILE — nhiều máy/VM không có board serial; dùng machine-id (+ product_uuid nếu có)"
fi

if [ -z "$machine_id" ] && [ -z "$product_uuid" ] && [ -z "$board_serial" ]; then
  fail 'không đọc được bất kỳ định danh phần cứng nào; chạy lại bằng sudo và kiểm tra 2 đường dẫn DMI'
fi

sources=''
[ -n "$machine_id" ] && sources="${sources}machine_id "
[ -n "$product_uuid" ] && sources="${sources}product_uuid "
[ -n "$board_serial" ] && sources="${sources}board_serial "

canonical=$(
  {
    [ -n "$machine_id" ] && printf 'machine_id=%s\n' "$machine_id"
    [ -n "$product_uuid" ] && printf 'product_uuid=%s\n' "$product_uuid"
    [ -n "$board_serial" ] && printf 'board_serial=%s\n' "$board_serial"
  } | sort | paste -sd '|' -
)

[ -n "$canonical" ] || fail 'không dựng được chuỗi định danh (dữ liệu rỗng)'

encoded=$(printf '%s' "$canonical" | hash_to_base32) ||
  fail 'không tính được base32 (cần openssl + base32, hoặc python3)'

if [ "${#encoded}" -ne 16 ]; then
  fail "base32 trả ${#encoded} ký tự thay vì 16 — kiểm tra openssl/base32"
fi

machine_code="DSIGHT-${encoded:0:4}-${encoded:4:4}-${encoded:8:4}-${encoded:12:4}"

printf '\n=== DSight machine code (mã máy) ===\n'
printf 'Nguồn đã dùng: %s\n' "${sources% }"
check_compose_mounts || true
printf '\nMÃ MÁY: %s\n' "$machine_code"
printf 'Gửi mã này cho DTG khi cần xoá activation cũ; mã dùng làm identifier khi activate license.\n'

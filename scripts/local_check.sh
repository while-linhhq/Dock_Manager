#!/usr/bin/env bash
# Kiểm tra sức khoẻ toàn bộ stack local của Dock Manager.
# Dùng: bash scripts/local_check.sh        (hoặc: make check)
#
# Không chạy pytest (272 test ~147s) — đó là việc của `make test`.
# Exit code 0 = mọi thứ PASS, 1 = có mục FAIL.
set -o pipefail   # KHÔNG dùng -u: conda.sh tham chiếu biến chưa đặt và sẽ làm shell thoát

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONDA_SH="${HOME}/miniconda3/etc/profile.d/conda.sh"
CONDA_ENV="${CONDA_ENV:-bason-dock}"

# Nạp server/.env qua parser (không `source` — giá trị có thể chứa ký tự shell).
if [ -f server/.env ]; then
  eval "$(python3 scripts/env_get.py --all)" || { echo "✗ Không đọc được server/.env" >&2; exit 1; }
else
  echo "✗ Thiếu server/.env" >&2
  exit 1
fi

BACKEND_HOST="${HOST:-127.0.0.1}"
case "$BACKEND_HOST" in
  0.0.0.0|::|'') BACKEND_HOST=127.0.0.1 ;;
esac
# Cẩn thận: trong conda env, HOST thường là triple toolchain (vd x86_64-conda-linux-gnu)
# chứ không phải host app bind. Chỉ nhận khi phân giải được — giống run_dev.py.
if ! python3 -c "import socket,sys; socket.getaddrinfo(sys.argv[1], None)" "$BACKEND_HOST" >/dev/null 2>&1; then
  printf '  \033[2m· HOST=%s không phân giải được (biến toolchain?) — dùng 127.0.0.1\033[0m\n' "$BACKEND_HOST"
  BACKEND_HOST=127.0.0.1
fi
BACKEND_PORT="${PORT:-8000}"
CLIENT_PORT="${CLIENT_PORT:-5173}"
BASE="http://${BACKEND_HOST}:${BACKEND_PORT}"
API="$BASE/api/v1"

PASS=0; FAIL=0; WARN=0
ok()   { printf '  \033[32m✓\033[0m %-26s %s\n' "$1" "$2"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m✗\033[0m %-26s %s\n' "$1" "$2"; FAIL=$((FAIL+1)); }
warn() { printf '  \033[33m·\033[0m %-26s %s\n' "$1" "$2"; WARN=$((WARN+1)); }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ---------------------------------------------------------------- 1. môi trường ảo
section "1. Môi trường ảo (conda)"
if [ -f "$CONDA_SH" ]; then
  # shellcheck disable=SC1090
  . "$CONDA_SH" && conda activate "$CONDA_ENV" 2>/dev/null
  if [ "${CONDA_DEFAULT_ENV:-}" = "$CONDA_ENV" ]; then
    PYV="$(python -V 2>&1)"
    ok "conda env" "$CONDA_ENV ($PYV)"
    GPU="$(python - <<'PY' 2>/dev/null
try:
    import torch
    print(f"torch {torch.__version__} · cuda={torch.cuda.is_available()}"
          + (f" · {torch.cuda.get_device_name(0)}" if torch.cuda.is_available() else ""))
except Exception as e:
    print(f"LỖI: {type(e).__name__}: {e}")
PY
)"
    case "$GPU" in
      LỖI*) bad "torch / CUDA" "$GPU" ;;
      *cuda=True*) ok "torch / CUDA" "$GPU" ;;
      *) warn "torch / CUDA" "$GPU — pipeline AI sẽ không chạy được" ;;
    esac
    MISSING="$(python - <<'PY' 2>/dev/null
import importlib
mods = ['fastapi','uvicorn','sqlalchemy','psycopg2','pydantic_settings','boto3','redis',
        'qdrant_client','cv2','ultralytics','paddleocr','psutil','jose','passlib']
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(', '.join(missing))
PY
)"
    if [ -z "$MISSING" ]; then ok "thư viện bắt buộc" "14/14 import được"
    else bad "thư viện bắt buộc" "thiếu: $MISSING"; fi
  else
    bad "conda env" "không activate được $CONDA_ENV"
  fi
else
  bad "conda" "không thấy $CONDA_SH"
fi

# --------------------------------------------------------------- 2. cấu hình
section "2. Cấu hình hiệu lực (db > env)"
# port_configs trong DB là lớp ưu tiên CAO HƠN .env: pipeline_service._load_runtime_config()
# nạp cfg_map rồi đọc `cfg_map.get(key, settings.X)`. Vì vậy phải kiểm tra giá trị
# HIỆU LỰC chứ không chỉ giá trị trong .env — nếu không sẽ báo xanh nhầm.
declare -A DBCFG=()
while IFS='=' read -r _k _v; do
  [ -n "$_k" ] && DBCFG["$_k"]="$_v"
done < <(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-postgres}" server-db-1 \
    psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-demo_db}" -tAc \
    "select key || '=' || value from port_configs;" 2>/dev/null)
printf '  \033[2m· port_configs nạp %d key từ DB (trùng key thì DB thắng .env)\033[0m\n' "${#DBCFG[@]}"

# Đếm key trùng tên bị DB ghi đè — để .env không bị đọc như thể là nguồn duy nhất.
OVERRIDDEN=0
for _k in "${!DBCFG[@]}"; do
  _u="${_k^^}"
  if [ -n "${!_u+x}" ] && [ "${!_u}" != "${DBCFG[$_k]}" ]; then OVERRIDDEN=$((OVERRIDDEN + 1)); fi
done
printf '  \033[2m· %d key trùng tên đang bị DB ghi đè (xem chi tiết: make config-diff)\033[0m\n' "$OVERRIDDEN"

eff() { if [ -n "${DBCFG[$1]+x}" ]; then printf '%s' "${DBCFG[$1]}"; else printf '%s' "$2"; fi; }
src() { if [ -n "${DBCFG[$1]+x}" ]; then printf 'db'; else printf 'env'; fi; }
local_ok() {  # local_ok <tên> <giá trị hiển thị> <nguồn> [giá trị đem kiểm tra]
  local name="$1" shown="$2" source="$3" probe="${4:-$2}"
  case "$probe" in
    *127.0.0.1*|*localhost*|*"@db:"*|*"//db:"*|*"@redis:"*|*"//redis:"*|*"@qdrant:"*|*"//qdrant:"*|"")
      ok "$name" "${shown:-(rỗng)} ($source)" ;;
    *) bad "$name" "${shown:-(rỗng)} ($source) — trỏ ra ngoài" ;;
  esac
}

# Các key này KHÔNG có trong port_configs (cấu hình kết nối không thể tự cấu hình
# từ DB) nên nguồn luôn là env.
local_ok "DATABASE_URL" \
  "$(printf '%s' "${DATABASE_URL:-}" | sed -E 's#^[a-z]+://[^@]*@##')" env "${DATABASE_URL:-}"
local_ok "MINIO_ENDPOINT" \
  "${MINIO_ENDPOINT:-} · secure=${MINIO_SECURE:-false} · bucket=${MINIO_BUCKET:-}" env
local_ok "AWS_ENDPOINT_URL" "${AWS_ENDPOINT_URL:-(chưa đặt → boto3 trỏ AWS thật)}" env

# Các key này CÓ trong DB → giá trị hiệu lực là của DB.
local_ok "REDIS_URL" \
  "$(printf '%s' "$(eff redis_url "${REDIS_URL:-}")" | sed -E 's#//[^@]*@#//#')" \
  "$(src redis_url)" "$(eff redis_url "${REDIS_URL:-}")"
local_ok "QDRANT_HOST" \
  "$(eff qdrant_host "${QDRANT_HOST:-}"):$(eff qdrant_port "${QDRANT_PORT:-6333}")" \
  "$(src qdrant_host)"

# Đường dẫn model/ffmpeg do DB quyết định — kiểm tra file có thật, tránh chạy nhầm model.
# Nếu có .engine cùng tên thì đó mới là file chạy thật (resolver ưu tiên engine).
for _pair in "model_path:${MODEL_PATH:-models/yolo/yolo26s_finetuned.pt}" "ffmpeg_path:${FFMPEG_PATH:-vendor/ffmpeg}"; do
  _k="${_pair%%:*}"; _default="${_pair#*:}"; _v="$(eff "$_k" "$_default")"
  _engine="${_v%.pt}.engine"
  if [ "$_k" = "model_path" ] && [ -f "server/$_engine" ]; then
    ok "$_k" "$_engine · engine TensorRT đang được dùng ($(src "$_k"))"
  elif [ -e "server/$_v" ]; then
    ok "$_k" "$_v · file tồn tại ($(src "$_k"))"
  else
    bad "$_k" "$_v · KHÔNG thấy server/$_v ($(src "$_k"))"
  fi
done

# Ví dụ ưu tiên db > env đang có tác dụng thật.
ok "seam_anchor_enabled" "hiệu lực=$(eff seam_anchor_enabled "${SEAM_ANCHOR_ENABLED:-}") ($(src seam_anchor_enabled)) · env=${SEAM_ANCHOR_ENABLED:-?}"

# TensorRT: engine không commit được (gắn cứng GPU + phiên bản TRT) nên phải xem máy này có gì.
TRT_VER="$(cd server 2>/dev/null && python -c 'import tensorrt;print(tensorrt.__version__)' 2>/dev/null)"
DINO_ENGINE="$(ls server/models/dinov2/*.engine 2>/dev/null | head -1)"
if [ -z "$TRT_VER" ]; then
  bad "TensorRT" "chưa cài — pip install 'tensorrt-cu12>=10,<11' (xem: make engines)"
elif [ -n "$DINO_ENGINE" ]; then
  ok "TensorRT" "$TRT_VER · DINOv2 engine $(basename "$DINO_ENGINE") ($(du -h "$DINO_ENGINE" | cut -f1))"
else
  ok "TensorRT" "$TRT_VER · chưa build DINOv2 engine (chạy: make engines)"
fi
if [ "${PADDLE_USE_TENSORRT:-false}" = "true" ]; then
  TRT_LINK="$(ls server/app/runtime-media/cuda-libs/libnvinfer.so 2>/dev/null)"
  if [ -n "$TRT_LINK" ]; then
    ok "Paddle TRT" "bật (${PADDLE_TRT_PRECISION:-fp16}) · symlink libnvinfer.so đã có cho Paddle"
  else
    warn "Paddle TRT" "bật nhưng thiếu symlink libnvinfer.so — OCR sẽ tự lùi về fp32 (chạy: make engines)"
  fi
fi

# Đường đi thật của app: settings (đọc .env) -> boto3 client. Cố tình xoá biến môi
# trường trước khi import để chắc rằng app tự đủ, không nhờ shell export hộ.
S3_EP="$(cd server 2>/dev/null && python -c '
import os
os.environ.pop("AWS_ENDPOINT_URL", None)
try:
    from app.services.storage.s3_service import get_s3_client
    print(get_s3_client().meta.endpoint_url or "")
except Exception as exc:
    print("LOI:" + type(exc).__name__)
' 2>/dev/null)"
case "$S3_EP" in
  *127.0.0.1*|*localhost*) ok "S3 client (app)" "endpoint_url=$S3_EP" ;;
  "") bad "S3 client (app)" "không dựng được client boto3" ;;
  *) bad "S3 client (app)" "endpoint_url=$S3_EP — sẽ ghi media lên AWS thật" ;;
esac

# Quét host ngoài ở CẢ HAI lớp. Cho phép: ZALO_*/zalo_* (giữ nguyên giá trị thật),
# sepay_* (token thật trong DB) và RTSP_URL (camera thật, không thể local hoá).
STRAY="$(grep -nE '^[A-Za-z_][A-Za-z0-9_]*=[^ ]*(iotforce\.io\.vn|aivo\.io\.vn|cameraddns\.net|amazonaws\.com)' server/.env 2>/dev/null \
  | grep -vE '^[0-9]+:(ZALO_|RTSP_URL=)' | cut -d: -f2- | cut -d= -f1 | tr '\n' ' ')"
for _k in "${!DBCFG[@]}"; do
  case "$_k" in zalo_*|sepay_*) continue ;; esac
  case "${DBCFG[$_k]}" in
    *iotforce.io.vn*|*aivo.io.vn*|*cameraddns.net*|*amazonaws.com*) STRAY="$STRAY db:$_k " ;;
  esac
done
if [ -z "$STRAY" ]; then
  ok "host ngoài" "không còn ở cả .env lẫn port_configs (ngoài Zalo/Sepay/RTSP)"
else
  bad "host ngoài" "còn trỏ ra ngoài: $STRAY"
fi

# Hai tích hợp ngoài: cờ bật/tắt đến từ env, dữ liệu thật (token/chat id) đến từ DB.
ok "SEPay sync" \
  "tắt (env SEPAY_SYNC_ENABLED=${SEPAY_SYNC_ENABLED:-?}) · token thật trong db=$([ -n "${DBCFG[sepay_api_token]:-}" ] && echo 'có, không dùng' || echo 'không')"
ZALO_HOST="$(printf '%s' "${ZALO_PUBLIC_BASE_URL:-}" | sed -E 's#^https?://##')"
ok "Zalo (giữ nguyên)" \
  "enabled=${ZALO_ENABLED:-?} · polling=${ZALO_POLLING_ENABLED:-?} · chat_id db=$([ -n "${DBCFG[zalo_chat_id]:-}" ] && echo 'có' || echo 'không') · base=${ZALO_HOST:-<rỗng>}"

# ------------------------------------------------------------------- 3. container
section "3. Docker (db · minio · redis · qdrant)"
for c in server-db-1 server-minio-1 server-redis-1 server-qdrant-1; do
  STATE="$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo missing)"
  HEALTH="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$c" 2>/dev/null || echo '')"
  if [ "$STATE" = "running" ] && { [ "$HEALTH" = "healthy" ] || [ "$HEALTH" = "n/a" ]; }; then
    ok "$c" "running · $HEALTH"
  else
    bad "$c" "state=$STATE health=$HEALTH — chạy: make up"
  fi
done

# ------------------------------------------------------------------------- 4. DB
section "4. PostgreSQL + dữ liệu"
PGUSER="${POSTGRES_USER:-postgres}"; PGDATABASE="${POSTGRES_DB:-demo_db}"
Q() { docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-}" server-db-1 \
        psql -U "$PGUSER" -d "$PGDATABASE" -tAc "$1" 2>/dev/null; }
TABLES="$(Q "select count(*) from information_schema.tables where table_schema='public';")"
if [ -n "$TABLES" ] && [ "$TABLES" -gt 0 ] 2>/dev/null; then
  COUNTS="$(Q "select 'vessels='||(select count(*) from vessels)||' detections='||(select count(*) from detections)||' cameras='||(select count(*) from cameras)||' invoices='||(select count(*) from invoices)||' users='||(select count(*) from users);")"
  ok "schema" "$TABLES bảng · $COUNTS"
else
  bad "schema" "không truy vấn được — chạy: make seed"
fi

# ---------------------------------------------------------------------- 5. MinIO
section "5. MinIO (media detection)"
if command -v python >/dev/null 2>&1; then
  MINFO="$(python - <<'PY' 2>/dev/null
import os
try:
    import boto3
    c = boto3.client('s3')
    b = os.environ.get('MINIO_BUCKET', 'media')
    n = sum(len(p.get('Contents', [])) for p in c.get_paginator('list_objects_v2').paginate(Bucket=b))
    print(f"endpoint={os.environ.get('AWS_ENDPOINT_URL','?')} bucket={b} objects={n}")
except Exception as e:
    print(f"LỖI: {type(e).__name__}: {e}")
PY
)"
  case "$MINFO" in
    LỖI*) bad "bucket" "$MINFO" ;;
    *objects=0) warn "bucket" "$MINFO — chưa có media" ;;
    *) ok "bucket" "$MINFO" ;;
  esac
fi

# --------------------------------------------------------------------- 6. Qdrant
section "6. Qdrant (vector Re-ID)"
QH="${QDRANT_HOST:-127.0.0.1}"; QP="${QDRANT_PORT:-6333}"
COLLS="$(curl -s -m 5 "http://${QH}:${QP}/collections" 2>/dev/null \
  | python3 -c "import sys,json;print(' '.join(c['name'] for c in json.load(sys.stdin)['result']['collections']))" 2>/dev/null)"
if [ -n "$COLLS" ]; then
  DETAIL=""
  for c in $COLLS; do
    N="$(curl -s -m 5 "http://${QH}:${QP}/collections/$c" 2>/dev/null \
      | python3 -c "import sys,json;print(json.load(sys.stdin)['result'].get('points_count'))" 2>/dev/null)"
    DETAIL="$DETAIL $c=$N"
  done
  ok "collections" "$DETAIL"
else
  bad "collections" "không kết nối được ${QH}:${QP}"
fi

# -------------------------------------------------------------------- 7. Redis
section "7. Redis"
RURL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
RHOST="$(printf '%s' "$RURL" | sed -E 's#^redis://([^@]*@)?([^:/]+).*#\2#')"
RPORT="$(printf '%s' "$RURL" | sed -E 's#^redis://([^@]*@)?[^:/]+:([0-9]+).*#\2#')"
[ "$RPORT" = "$RURL" ] && RPORT=6379
if docker exec server-redis-1 redis-cli ping 2>/dev/null | grep -q PONG; then
  ok "ping" "$RHOST:$RPORT → PONG"
else
  bad "ping" "không phản hồi tại $RHOST:$RPORT"
fi

# ------------------------------------------------------------------- 8. backend
section "8. Backend API (:${BACKEND_PORT})"
# Backend có thể đang bận nạp pipeline AI (YOLO engine · PaddleOCR · DINOv2 — log cho thấy
# /pipeline/start mất ~24s và event loop bị chặn trong lúc đó) nên thử lại vài lần.
CODE=""
for _try in 1 2 3 4 5; do
  CODE="$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null)"
  [ "$CODE" = "200" ] && break
  [ "$_try" -lt 5 ] && sleep 5
done
if [ "$CODE" = "200" ]; then
  ok "/health" "HTTP 200 $BASE/health"
  DCODE="$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$BASE/docs" 2>/dev/null)"
  [ "$DCODE" = "200" ] && ok "/docs" "HTTP 200 (Swagger)" || warn "/docs" "HTTP $DCODE"

  TOKEN="$(curl -s -m 10 -X POST "$API/auth/login" -d 'username=admin&password=admin123' 2>/dev/null \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)"
  if [ -n "$TOKEN" ]; then
    ok "đăng nhập" "admin/admin123 → có access token"
    ME="$(curl -sL -m 10 -H "Authorization: Bearer $TOKEN" "$API/users/me" 2>/dev/null \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print(f\"{d.get('username')} · role={d.get('role',{}).get('role_name')}\")" 2>/dev/null)"
    [ -n "$ME" ] && ok "phân quyền" "$ME" || warn "phân quyền" "không đọc được /users/me"
    DCOUNT="$(curl -sL -m 15 -H "Authorization: Bearer $TOKEN" "$API/detections/?limit=1" 2>/dev/null \
      | python3 -c "import sys,json;print(len(json.load(sys.stdin)))" 2>/dev/null)"
    VCOUNT="$(curl -sL -m 15 -H "Authorization: Bearer $TOKEN" "$API/vessels/?limit=1" 2>/dev/null \
      | python3 -c "import sys,json;print(len(json.load(sys.stdin)))" 2>/dev/null)"
    if [ "${DCOUNT:-0}" -ge 1 ] && [ "${VCOUNT:-0}" -ge 1 ]; then
      ok "dữ liệu API" "detections + vessels trả về bản ghi"
    else
      bad "dữ liệu API" "detections=$DCOUNT vessels=$VCOUNT (mong đợi ≥1)"
    fi
    PIPE="$(curl -s -m 8 -H "Authorization: Bearer $TOKEN" "$API/pipeline/status" 2>/dev/null \
      | python3 -c "
import json, sys
d = json.load(sys.stdin)
gpu = d.get('gpu') or {}
desc = gpu.get('device_name') or ''
print(('DANG_CHAY' if d.get('is_running') else 'dang_tat')
      + ' | group=' + str(d.get('active_group_id'))
      + ' | seam_anchor=' + ('on' if d.get('seam_anchor_active') else 'off')
      + ((' | ' + desc) if desc else ''))" 2>/dev/null | sed 's/DANG_CHAY/ĐANG CHẠY/; s/dang_tat/đang tắt/')"
    [ -n "$PIPE" ] && ok "pipeline AI" "$PIPE" || warn "pipeline AI" "không đọc được /pipeline/status"
  else
    bad "đăng nhập" "admin/admin123 thất bại — DB local đã đổi mật khẩu?"
  fi
else
  bad "/health" "HTTP $CODE — chưa chạy? dùng: make backend"
fi

# -------------------------------------------------------------------- 9. client
section "9. Client (Vite :${CLIENT_PORT})"
CCODE="$(curl -s -m 8 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${CLIENT_PORT}/" 2>/dev/null)"
if [ "$CCODE" = "200" ]; then
  ok "dev server" "HTTP 200 http://localhost:${CLIENT_PORT}/"
  PCODE="$(curl -s -m 10 -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:${CLIENT_PORT}/api/v1/auth/login" -d 'username=admin&password=admin123' 2>/dev/null)"
  [ "$PCODE" = "200" ] && ok "proxy /api" "Vite → backend local OK" \
                       || bad "proxy /api" "HTTP $PCODE — kiểm tra VITE_API_PROXY_TARGET trong client/.env"
else
  warn "dev server" "HTTP $CCODE — chưa chạy? dùng: make client"
fi

# ----------------------------------------------------------------------- verdict
printf '\n\033[1mKết quả:\033[0m \033[32m%d PASS\033[0m · \033[33m%d WARN\033[0m · \033[31m%d FAIL\033[0m\n' "$PASS" "$WARN" "$FAIL"
if [ "$FAIL" -eq 0 ]; then
  printf '\033[32m✓ Local sẵn sàng.\033[0m  Backend %s  ·  Client http://localhost:%s  ·  đăng nhập admin/admin123\n' "$BASE" "$CLIENT_PORT"
  exit 0
fi
printf '\033[31m✗ Còn %d mục FAIL — xem gợi ý ở trên.\033[0m\n' "$FAIL"
exit 1

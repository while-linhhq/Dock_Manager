#!/usr/bin/env bash
# Chạy backend + client ở nền cho môi trường local, rồi chờ tới khi sẵn sàng.
# Idempotent: đã chạy thì bỏ qua (dùng `make restart` nếu muốn khởi động lại).
# Dùng: bash scripts/local_start.sh        (hoặc: make start)
set -o pipefail   # KHÔNG dùng -u: conda.sh tham chiếu biến chưa đặt và sẽ làm shell thoát

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="server/.env"
RUN_DIR=".run"
CONDA_SH="${HOME}/miniconda3/etc/profile.d/conda.sh"
CONDA_ENV="${CONDA_ENV:-bason-dock}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
CLIENT_PORT="${CLIENT_PORT:-5173}"
PIPELINE="${PIPELINE:-1}"

[ -f "$ENV_FILE" ] || { echo "✗ Thiếu $ENV_FILE" >&2; exit 1; }
mkdir -p "$RUN_DIR"

alive() { [ -f "$1" ] && kill -0 "$(cat "$1" 2>/dev/null)" 2>/dev/null; }

# --- Backend ----------------------------------------------------------------
if alive "$RUN_DIR/backend.pid"; then
  printf '  · backend  đã chạy (pid %s) — bỏ qua\n' "$(cat "$RUN_DIR/backend.pid")"
else
  # Không source .env: pydantic-settings đọc server/.env (cwd=server). Chỉ export
  # cờ điều khiển pipeline cho tiến trình con.
  export AUTOSTART_PIPELINE="$PIPELINE"
  # Backend cần đúng conda env — thiếu bước này `python` hệ thống sẽ chết vì
  # ModuleNotFoundError: uvicorn (và mất ~90s chờ vô ích).
  if [ -f "$CONDA_SH" ]; then
    # shellcheck disable=SC1090
    . "$CONDA_SH" && conda activate "$CONDA_ENV"
  fi
  if ! python -c 'import uvicorn' 2>/dev/null; then
    printf '✗ conda env "%s" thiếu uvicorn — kiểm tra CONDA_ENV / cài requirements.\n' "$CONDA_ENV" >&2
    exit 1
  fi
  # Nhóm { } giữ cwd=server cho cả lệnh nền LẪN ghi PID; đường dẫn tuyệt đối để
  # không phụ thuộc cwd của tiến trình con.
  ( cd server && { setsid nohup python run_dev.py > "$ROOT/$RUN_DIR/backend.log" 2>&1 & echo $! > "$ROOT/$RUN_DIR/backend.pid"; } )
  printf '▶ Backend  :%s (pid %s · pipeline AI %s · %s)\n' "$BACKEND_PORT" \
    "$(cat "$RUN_DIR/backend.pid")" "$( [ "$PIPELINE" = "1" ] && echo BẬT || echo TẮT )" "$CONDA_ENV"
fi

# --- Client -----------------------------------------------------------------
if alive "$RUN_DIR/client.pid"; then
  printf '  · client   đã chạy (pid %s) — bỏ qua\n' "$(cat "$RUN_DIR/client.pid")"
else
  ( cd client && { setsid nohup pnpm run dev > "$ROOT/$RUN_DIR/client.log" 2>&1 & echo $! > "$ROOT/$RUN_DIR/client.pid"; } )
  printf '▶ Client   :%s (pid %s)\n' "$CLIENT_PORT" "$(cat "$RUN_DIR/client.pid")"
fi

# --- Chờ sẵn sàng -----------------------------------------------------------
printf '  · chờ backend'
for _ in $(seq 1 90); do
  curl -s -m 2 -o /dev/null "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null && break
  printf '.'; sleep 1
done
echo

printf '  · chờ client'
for _ in $(seq 1 45); do
  curl -s -m 2 -o /dev/null "http://127.0.0.1:$CLIENT_PORT/" 2>/dev/null && break
  printf '.'; sleep 1
done
echo

if [ "$PIPELINE" = "1" ]; then
  printf '  · chờ pipeline AI (nạp YOLO · PaddleOCR · DINOv2, ~40s)'
  RUNNING=0
  for _ in $(seq 1 60); do
    if curl -s -m 12 "http://127.0.0.1:$BACKEND_PORT/api/v1/pipeline/status" 2>/dev/null \
       | grep -Eq '"is_running"[[:space:]]*:[[:space:]]*true'; then
      RUNNING=1; printf ' ✓\n'; break
    fi
    printf '.'; sleep 3
  done
  if [ "$RUNNING" = "0" ]; then
    printf ' (chưa chạy — xem %s/backend.log)\n' "$RUN_DIR"
  fi
fi

printf '✓ Sẵn sàng: client http://localhost:%s  ·  API http://127.0.0.1:%s/docs  ·  admin/admin123\n' \
  "$CLIENT_PORT" "$BACKEND_PORT"
printf '  log: %s/backend.log  ·  %s/client.log\n' "$RUN_DIR" "$RUN_DIR"

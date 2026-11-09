#!/usr/bin/env bash
# Dừng stack local của Dock Manager: backend (graceful), client, và OCR worker mồ côi.
# Dùng: bash scripts/local_stop.sh        (hoặc: make stop)
#
# Backend/client được Makefile chạy qua `setsid` nên mỗi cái là trưởng nhóm tiến
# trình. Dừng bằng `kill -- -PGID` để con cháu (vite, OCR worker) không mồ côi
# giữ cổng/VRAM.
set -o pipefail   # KHÔNG dùng -u: conda.sh tham chiếu biến chưa đặt và sẽ làm shell thoát

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DIR=".run"
CONDA_SH="${HOME}/miniconda3/etc/profile.d/conda.sh"
CONDA_ENV="${CONDA_ENV:-bason-dock}"

# Còn tiến trình nào sống trong nhóm $1?
group_alive() {
  [ -n "$(pgrep -g "$1" 2>/dev/null)" ]
}

stop_pidfile() {
  local name="$1" file="$2" pid pgid use_group=0 waited=0
  if [ ! -f "$file" ]; then
    printf '  · %-8s không có PID file\n' "$name"
    return 0
  fi
  pid="$(cat "$file" 2>/dev/null)"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    printf '  · %-8s đã dừng (pid %s không tồn tại)\n' "$name" "${pid:-?}"
    rm -f "$file"
    return 0
  fi

  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  if [ -n "$pgid" ] && [ "$pgid" = "$pid" ]; then
    use_group=1
    kill -TERM -- "-$pgid" 2>/dev/null
  else
    kill -TERM "$pid" 2>/dev/null
  fi

  while [ "$waited" -lt 25 ]; do
    if [ "$use_group" = "1" ]; then
      group_alive "$pid" || break
    else
      kill -0 "$pid" 2>/dev/null || break
    fi
    sleep 1
    waited=$((waited + 1))
  done

  if [ "$use_group" = "1" ] && group_alive "$pid"; then
    printf '  ! %-8s không thoát sau 25s — SIGKILL cả nhóm %s\n' "$name" "$pid"
    kill -KILL -- "-$pid" 2>/dev/null
  elif [ "$use_group" = "0" ] && kill -0 "$pid" 2>/dev/null; then
    printf '  ! %-8s không thoát sau 25s — SIGKILL pid %s\n' "$name" "$pid"
    kill -KILL "$pid" 2>/dev/null
  else
    printf '  ✓ %-8s đã dừng (pid %s%s)\n' "$name" "$pid" \
      "$( [ "$use_group" = "1" ] && echo ' · cả nhóm tiến trình' )"
  fi
  rm -f "$file"
}

printf '▶ Dừng Dock Manager local\n'
# Backend trước: SIGTERM cho uvicorn để lifespan shutdown dừng pipeline + đóng DB
stop_pidfile backend "$RUN_DIR/backend.pid"
stop_pidfile client  "$RUN_DIR/client.pid"

# OCR worker là tiến trình con do multiprocessing spawn: /proc chỉ hiện tên "python"
# với cmdline "from multiprocessing.spawn import spawn_main", nên khớp theo tên
# 'ocr-gpu-worker' (cách code cũ làm) KHÔNG bao giờ trúng. Nhận diện theo bộ ba:
#   cmdline có "multiprocessing" + cwd = server/ + đúng interpreter của conda env
# => chỉ trúng tiến trình con của chính dự án này.
if [ -f "$CONDA_SH" ]; then
  # shellcheck disable=SC1090
  . "$CONDA_SH" && conda activate "$CONDA_ENV" 2>/dev/null
  KILLED="$(python - "$ROOT/server" <<'PY' 2>/dev/null
import os
import sys

try:
    import psutil
except Exception:
    print("")
    raise SystemExit(0)

server_dir = os.path.realpath(sys.argv[1])
exe = os.path.realpath(sys.executable)
me = psutil.Process()
mine = {me.pid} | {c.pid for c in me.children(recursive=True)}

killed = []
for proc in psutil.process_iter(['pid', 'cmdline']):
    try:
        if proc.pid in mine:
            continue
        cmdline = ' '.join(proc.info.get('cmdline') or [])
        if 'multiprocessing' not in cmdline:
            continue
        if os.path.realpath(proc.cwd()) != server_dir:
            continue
        if os.path.realpath(proc.exe()) != exe:
            continue
        proc.terminate()
        killed.append(proc.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        continue

if killed:
    _, alive = psutil.wait_procs(
        [psutil.Process(p) for p in killed if psutil.pid_exists(p)], timeout=5.0)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
print(','.join(str(p) for p in killed))
PY
)"
  if [ -n "$KILLED" ]; then
    printf '  ✓ %-8s đã dọn tiến trình con mồ côi (pid %s)\n' "ocr" "$KILLED"
  else
    printf '  · %-8s không có tiến trình con mồ côi\n' "ocr"
  fi
fi

printf '✓ Đã dừng. Container vẫn chạy — dùng `make down` để tắt luôn.\n'

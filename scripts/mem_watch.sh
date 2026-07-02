#!/usr/bin/env bash
# Giám sát RAM pipeline: tổng RSS toàn cây process backend (root PID + mọi con,
# gồm OCR subprocess spawn) + swap + mem hệ thống. Ghi CSV mỗi INTERVAL giây.
# Bắt xu hướng leo (leak) vs ổn định.
set -u
INTERVAL="${INTERVAL:-30}"
LOG="${LOG:-/tmp/mem_watch.csv}"
ROOT_PID="${ROOT_PID:?set ROOT_PID to backend root pid}"

# In ra ROOT_PID + toàn bộ con cháu (BFS qua bảng ppid trong /proc).
descendants() {
  local root="$1"
  declare -A kids=()
  local d pid ppid
  for d in /proc/[0-9]*; do
    pid=${d#/proc/}
    ppid=$(awk '/^PPid:/{print $2}' "$d/status" 2>/dev/null) || continue
    [ -n "${ppid:-}" ] && kids[$ppid]="${kids[$ppid]:-} $pid"
  done
  local queue=("$root") out=() cur
  while [ ${#queue[@]} -gt 0 ]; do
    cur="${queue[0]}"
    queue=("${queue[@]:1}")
    out+=("$cur")
    # shellcheck disable=SC2206
    [ -n "${kids[$cur]:-}" ] && queue+=(${kids[$cur]})
  done
  echo "${out[@]}"
}

echo "ts,backend_procs,backend_rss_mb,mem_used_mb,mem_avail_mb,swap_used_mb" > "$LOG"
while true; do
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  if [ ! -d "/proc/$ROOT_PID" ]; then
    echo "$ts,0,0,,,BACKEND_DEAD" | tee -a "$LOG"
    sleep "$INTERVAL"; continue
  fi
  pids=$(descendants "$ROOT_PID")
  nproc=0; rss_kb=0
  for p in $pids; do
    r=$(awk '/^VmRSS:/{print $2}' /proc/$p/status 2>/dev/null) || continue
    [ -n "${r:-}" ] && rss_kb=$((rss_kb + r)) && nproc=$((nproc + 1))
  done
  backend_rss_mb=$((rss_kb / 1024))
  read mem_used mem_avail <<< "$(free -m | awk '/^Mem:/{print $3" "$7}')"
  swap_used=$(free -m | awk '/^Swap:/{print $3}')
  echo "$ts,$nproc,$backend_rss_mb,$mem_used,$mem_avail,$swap_used" | tee -a "$LOG"
  sleep "$INTERVAL"
done

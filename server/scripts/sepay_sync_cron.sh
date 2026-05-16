#!/usr/bin/env bash
# Gọi từ crontab, ví dụ mỗi phút:
# * * * * * SEPAY_CRON_SECRET=xxx API_BASE=http://127.0.0.1:8000 /path/to/sepay_sync_cron.sh

set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
SECRET="${SEPAY_CRON_SECRET:-}"

if [[ -z "${SECRET}" ]]; then
  echo "SEPAY_CRON_SECRET is required" >&2
  exit 1
fi

curl -fsS -X POST \
  -H "X-Sepay-Cron-Secret: ${SECRET}" \
  "${API_BASE%/}/api/v1/sepay/sync/cron"

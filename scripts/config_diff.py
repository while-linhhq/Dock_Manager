#!/usr/bin/env python3
"""So sánh cấu hình hai lớp: port_configs (DB, ưu tiên cao) vs server/.env.

    python3 scripts/config_diff.py        # hoặc: make config-diff

Cơ chế: pipeline_service._load_runtime_config() nạp toàn bộ port_configs vào cfg_map
rồi đọc `cfg_map.get(key, settings.X)` — nên khi trùng key, GIÁ TRỊ TRONG DB THẮNG.
Script này in ra đúng những key bị ghi đè để không phải đoán .env có tác dụng hay không.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "server" / ".env"
_SECRET = re.compile(r"(password|secret|token|api_key|access_key)", re.I)
BOLD, DIM, YELLOW, RESET = "\033[1m", "\033[2m", "\033[33m", "\033[0m"


def read_env(path: Path = ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            values[k.strip()] = v.strip()
    return values


def read_db(env: dict[str, str]) -> dict[str, str]:
    cmd = [
        "docker", "exec", "-e", f"PGPASSWORD={env.get('POSTGRES_PASSWORD', 'postgres')}",
        "server-db-1", "psql", "-U", env.get("POSTGRES_USER", "postgres"),
        "-d", env.get("POSTGRES_DB", "demo_db"), "-tAc",
        "select key || '=' || value from port_configs;",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except Exception as exc:  # pragma: no cover - chỉ dùng tay
        print(f"✗ Không truy vấn được port_configs: {exc}", file=sys.stderr)
        return {}
    values: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values


def show(key: str, value: str) -> str:
    if value and _SECRET.search(key):
        return f"<ẩn {len(value)} ký tự>"
    return value or "(rỗng)"


def main() -> int:
    env = read_env()
    db = read_db(env)
    if not db:
        return 1

    same, diff, only_db = [], [], []
    for key, db_value in sorted(db.items()):
        env_value = env.get(key.upper())
        if env_value is None:
            only_db.append(key)
        elif env_value == db_value:
            same.append(key)
        else:
            diff.append((key, env_value, db_value))

    print(f"{BOLD}DB (port_configs): {len(db)} key  ·  .env: {len(env)} key{RESET}")

    print(f"\n{BOLD}{YELLOW}Trùng key nhưng khác giá trị → DB thắng ({len(diff)}){RESET}")
    if diff:
        width = max(len(k) for k, _, _ in diff)
        for key, env_value, db_value in diff:
            print(f"  {key:<{width}}  .env={show(key, env_value):<24} → hiệu lực={show(key, db_value)}")
    else:
        print("  (không có)")

    print(f"\n{BOLD}Chỉ có trong DB — .env không có key tương ứng ({len(only_db)}){RESET}")
    for i in range(0, len(only_db), 4):
        print("  " + "".join(f"{k:<32}" for k in only_db[i:i + 4]).rstrip())

    print(f"\n{DIM}Trùng key và cùng giá trị: {len(same)} key{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

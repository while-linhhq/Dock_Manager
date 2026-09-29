#!/usr/bin/env python3
"""Đọc server/.env an toàn từ shell (không `source` — tránh vỡ chuỗi có ký tự đặc biệt).

    python3 scripts/env_get.py KEY [DEFAULT]   # in 1 giá trị
    python3 scripts/env_get.py --all           # in các dòng `export K=V` để `eval`
    python3 scripts/env_get.py --json          # in toàn bộ dưới dạng JSON (đã che secret)
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "server" / ".env"

_SECRET = re.compile(r"(PASSWORD|SECRET|TOKEN|API_KEY|ACCESS_KEY|_KEY$)", re.I)


def parse(path: Path = ENV_FILE) -> "dict[str, str]":
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, value = s.split("=", 1)
        key = key.strip()
        # bỏ qua dòng rác, chỉ nhận KEY hợp lệ
        if not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        values[key] = value.strip()
    return values


def main(argv: list[str]) -> int:
    values = parse()

    if len(argv) == 2 and argv[1] == "--all":
        for key, value in values.items():
            print(f"export {key}={shlex.quote(value)}")
        return 0

    if len(argv) == 2 and argv[1] == "--json":
        print(json.dumps(
            {k: (f"<ẩn {len(v)} ký tự>" if v and _SECRET.search(k) else v)
             for k, v in sorted(values.items())},
            ensure_ascii=False, indent=2))
        return 0

    if not 2 <= len(argv) <= 3:
        print(__doc__, file=sys.stderr)
        return 2

    key = argv[1]
    if key in values:
        print(values[key])
        return 0
    if len(argv) == 3:
        print(argv[2])
        return 0
    print(f"env_get: không có key {key!r} trong {ENV_FILE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

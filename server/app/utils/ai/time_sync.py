"""Map monotonic capture instants to wall-clock for on-frame debug labels."""
from __future__ import annotations

import time


def monotonic_to_wall(ts_mono: float) -> float:
    return time.time() - (time.monotonic() - float(ts_mono))


def format_capture_wall_clock(ts_mono: float, *, camera_id: int | None = None) -> str:
    wall = monotonic_to_wall(ts_mono)
    local = time.localtime(wall)
    base = time.strftime('%H:%M:%S', local)
    ms = int((wall % 1.0) * 1000.0)
    prefix = f'CAM{int(camera_id)} ' if camera_id is not None else ''
    return f'{prefix}{base}.{ms:03d}'

"""Bộ đếm frame + fps theo camera cho pipeline (nhẹ, thread-safe, clock tiêm được).

Mỗi frame chỉ tốn một lần append vào deque và một phép tăng số nguyên; fps tính
theo cửa sổ trượt nên phản ánh tình trạng hiện tại chứ không phải trung bình từ
lúc khởi động.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class FrameStats:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        window_sec: float = 60.0,
    ) -> None:
        self._clock = clock
        self._window_sec = max(1.0, float(window_sec))
        self._lock = threading.Lock()
        self._stamps: dict[int, deque[float]] = {}
        self._totals: dict[int, int] = {}

    def record(self, camera_id: int) -> None:
        key = int(camera_id)
        now = self._clock()
        with self._lock:
            stamps = self._stamps.setdefault(key, deque())
            stamps.append(now)
            self._totals[key] = self._totals.get(key, 0) + 1
            cutoff = now - self._window_sec
            while stamps and stamps[0] < cutoff:
                stamps.popleft()

    def fps(self, camera_id: int) -> float | None:
        with self._lock:
            stamps = self._stamps.get(int(camera_id))
            if stamps is None or len(stamps) < 2:
                return None
            span = stamps[-1] - stamps[0]
            if span <= 0:
                return None
            return (len(stamps) - 1) / span

    def totals(self) -> dict[int, int]:
        with self._lock:
            return dict(self._totals)

    def snapshot(self) -> dict[int, float]:
        with self._lock:
            keys = list(self._stamps)
        result: dict[int, float] = {}
        for key in keys:
            value = self.fps(key)
            if value is not None:
                result[key] = value
        return result

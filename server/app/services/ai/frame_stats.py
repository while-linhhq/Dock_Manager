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
        # mỗi mẫu là (thời điểm, số ms xử lý frame — None nếu không đo)
        self._samples: dict[int, deque[tuple[float, float | None]]] = {}
        self._totals: dict[int, int] = {}

    def _prune(self, samples: deque[tuple[float, float | None]], now: float) -> None:
        cutoff = now - self._window_sec
        while samples and samples[0][0] < cutoff:
            samples.popleft()

    def record(self, camera_id: int, duration_ms: float | None = None) -> None:
        key = int(camera_id)
        now = self._clock()
        with self._lock:
            samples = self._samples.setdefault(key, deque())
            samples.append((now, float(duration_ms) if duration_ms is not None else None))
            self._totals[key] = self._totals.get(key, 0) + 1
            self._prune(samples, now)

    def reset(self) -> None:
        """Xoá mẫu + tổng (gọi khi pipeline khởi động lại để số không cộng dồn)."""
        with self._lock:
            self._samples.clear()
            self._totals.clear()

    def fps(self, camera_id: int) -> float | None:
        now = self._clock()
        with self._lock:
            samples = self._samples.get(int(camera_id))
            if samples is not None:
                self._prune(samples, now)
            if samples is None or len(samples) < 2:
                return None
            span = samples[-1][0] - samples[0][0]
            if span <= 0:
                return None
            return (len(samples) - 1) / span

    def avg_ms(self, camera_id: int) -> float | None:
        """Thời gian xử lý trung bình mỗi frame trong cửa sổ (None nếu chưa đo)."""
        now = self._clock()
        with self._lock:
            samples = self._samples.get(int(camera_id))
            if samples is not None:
                self._prune(samples, now)
            if not samples:
                return None
            durations = [value for _, value in samples if value is not None]
        if not durations:
            return None
        return sum(durations) / len(durations)

    def totals(self) -> dict[int, int]:
        with self._lock:
            return dict(self._totals)

    def ms_snapshot(self) -> dict[int, float]:
        """Thời gian xử lý trung bình mỗi frame theo camera (bỏ camera chưa đo)."""
        with self._lock:
            keys = list(self._samples)
        result: dict[int, float] = {}
        for key in keys:
            value = self.avg_ms(key)
            if value is not None:
                result[key] = value
        return result

    def snapshot(self) -> dict[int, float]:
        with self._lock:
            keys = list(self._samples)
        result: dict[int, float] = {}
        for key in keys:
            value = self.fps(key)
            if value is not None:
                result[key] = value
        return result

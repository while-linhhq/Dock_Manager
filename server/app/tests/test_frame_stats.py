"""Bộ đếm frame/fps theo camera (dùng cho /pipeline/status và log 30 s)."""
from __future__ import annotations

import json
import threading

from app.services.ai.frame_stats import FrameStats


class _FakeClock:
    def __init__(self, step: float) -> None:
        self._now = 0.0
        self._step = step

    def __call__(self) -> float:
        value = self._now
        self._now += self._step
        return value


def test_counts_and_fps_with_injected_clock() -> None:
    stats = FrameStats(clock=_FakeClock(0.04))

    for _ in range(25):
        stats.record(1)

    assert stats.totals() == {1: 25}
    assert stats.fps(1) is not None
    assert abs(stats.fps(1) - 25.0) < 1.25  # 25 fps ± 5 %


def test_fps_none_before_two_samples() -> None:
    stats = FrameStats(clock=_FakeClock(0.04))

    assert stats.fps(1) is None
    stats.record(1)
    assert stats.fps(1) is None


def test_fps_separate_per_camera() -> None:
    stats = FrameStats(clock=_FakeClock(0.04))

    for _ in range(25):
        stats.record(1)
    for _ in range(5):
        stats.record(2)

    assert stats.totals() == {1: 25, 2: 5}
    assert abs(stats.fps(1) - 25.0) < 1.25
    assert abs(stats.fps(2) - 25.0) < 1.25


def test_old_samples_leave_window() -> None:
    clock = _FakeClock(1.0)
    stats = FrameStats(clock=clock, window_sec=5.0)

    for _ in range(10):
        stats.record(1)

    assert stats.totals() == {1: 10}
    assert stats.fps(1) == 1.0  # cửa sổ 5 s → 5 mẫu gần nhất, span 4 s


def test_thread_safety_smoke() -> None:
    stats = FrameStats()

    def worker() -> None:
        for _ in range(200):
            stats.record(7)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert stats.totals() == {7: 800}


def test_snapshot_uses_camera_ids() -> None:
    stats = FrameStats(clock=_FakeClock(0.04))
    for _ in range(25):
        stats.record(3)

    assert set(stats.snapshot()) == {3}


def test_service_payload_is_json_safe() -> None:
    from app.services.pipeline_service import PipelineService

    service = PipelineService.__new__(PipelineService)  # không khởi động pipeline
    service._frame_stats = FrameStats(clock=_FakeClock(0.04))
    for _ in range(25):
        service._frame_stats.record(4)

    payload = service.frame_stats_payload()

    assert set(payload) == {'frames_processed', 'fps_per_camera'}
    assert payload['frames_processed'] == {'4': 25}
    assert abs(payload['fps_per_camera']['4'] - 25.0) < 1.25
    json.dumps(payload)  # khoá phải là chuỗi để JSON hoá được

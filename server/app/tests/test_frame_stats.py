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
    clock = _ManualClock()
    stats = FrameStats(clock=clock, window_sec=5.0)

    for _ in range(10):
        stats.record(1)
        clock.advance(1.0)

    # mẫu ở t=0..9, now=10 → cửa sổ 5 s giữ t=5..9 → span 4 s, 5 mẫu
    assert stats.totals() == {1: 10}
    assert stats.fps(1) == 1.0


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


def test_avg_ms_none_before_samples() -> None:
    stats = FrameStats(clock=_FakeClock(0.04))

    stats.record(1)

    assert stats.avg_ms(1) is None


def test_avg_ms_averages_within_window() -> None:
    stats = FrameStats(clock=_FakeClock(0.04))

    for value in (10.0, 20.0, 30.0):
        stats.record(1, value)

    assert stats.avg_ms(1) == 20.0


def test_old_durations_leave_window() -> None:
    clock = _ManualClock()
    stats = FrameStats(clock=clock, window_sec=2.0)

    for value in (100.0, 200.0, 10.0, 20.0, 30.0):
        stats.record(1, value)
        clock.advance(1.0)

    # mẫu ở t=0..4, now=5 → cửa sổ 2 s chỉ giữ t=3,4 → (20+30)/2
    assert stats.avg_ms(1) == 25.0


def test_snapshot_uses_camera_ids() -> None:
    stats = FrameStats(clock=_FakeClock(0.04))
    for _ in range(25):
        stats.record(3)

    assert set(stats.snapshot()) == {3}


class _ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_fps_expires_when_camera_stops() -> None:
    clock = _ManualClock()
    stats = FrameStats(clock=clock, window_sec=60.0)
    for _ in range(10):
        stats.record(1, 12.0)
        clock.advance(0.1)

    assert stats.fps(1) is not None

    clock.advance(3600.0)

    assert stats.fps(1) is None
    assert stats.avg_ms(1) is None
    assert stats.snapshot() == {}
    assert stats.ms_snapshot() == {}
    assert stats.totals() == {1: 10}  # tổng tích luỹ vẫn giữ


def test_reset_clears_samples_and_totals() -> None:
    stats = FrameStats(clock=_FakeClock(0.04))
    for _ in range(5):
        stats.record(1, 10.0)

    stats.reset()

    assert stats.totals() == {}
    assert stats.fps(1) is None
    assert stats.avg_ms(1) is None


def test_service_payload_is_json_safe() -> None:
    from app.services.pipeline_service import PipelineService

    service = PipelineService.__new__(PipelineService)  # không khởi động pipeline
    service._frame_stats = FrameStats(clock=_FakeClock(0.04))
    for _ in range(25):
        service._frame_stats.record(4, 12.5)

    payload = service.frame_stats_payload()

    assert set(payload) == {'frames_processed', 'fps_per_camera', 'process_ms_per_frame'}
    assert payload['frames_processed'] == {'4': 25}
    assert abs(payload['fps_per_camera']['4'] - 25.0) < 1.25
    json.dumps(payload)  # khoá phải là chuỗi để JSON hoá được

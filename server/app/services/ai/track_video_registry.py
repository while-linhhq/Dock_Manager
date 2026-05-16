"""Per-track recorded video lookup (fused + single-camera pools)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


def _overlap_seconds(
    a_start: float,
    a_end: float,
    b_start: float,
    b_end: float,
) -> float:
    start = max(float(a_start), float(b_start))
    end = min(float(a_end), float(b_end))
    return max(0.0, end - start)


@dataclass
class RecordedVideo:
    uri: str
    size: int
    created_at: float
    started_at: float
    ended_at: float
    track_ids: frozenset[str] = field(default_factory=frozenset)


class TrackVideoRegistry:
    """
    Maps finalized tracks to the recording session that included them.
    Single-track sessions are exclusive (uri claimed once); multi-track sessions
    may be shared by every track_id present in that session.
    """

    def __init__(self, *, max_entries: int = 40) -> None:
        self._max_entries = max(5, int(max_entries))
        self._lock = threading.Lock()
        self._fused: list[RecordedVideo] = []
        self._single: list[RecordedVideo] = []
        self._claimed_uris: set[str] = set()

    def clear(self) -> None:
        with self._lock:
            self._fused.clear()
            self._single.clear()
            self._claimed_uris.clear()

    def register_fused(self, record: RecordedVideo) -> None:
        with self._lock:
            self._fused.append(record)
            if len(self._fused) > self._max_entries:
                self._fused = self._fused[-self._max_entries :]

    def register_single(self, record: RecordedVideo) -> None:
        with self._lock:
            self._single.append(record)
            if len(self._single) > self._max_entries:
                self._single = self._single[-self._max_entries :]

    def take_for_track(
        self,
        track_id: str,
        start_ts: float,
        end_ts: float,
        *,
        fused: bool,
    ) -> RecordedVideo | None:
        tid = str(track_id)
        t_start = float(start_ts)
        t_end = float(end_ts)
        if t_end < t_start:
            t_start, t_end = t_end, t_start

        with self._lock:
            pool = self._fused if fused else self._single
            best: RecordedVideo | None = None
            best_score = -1.0

            for video in pool:
                if video.uri in self._claimed_uris:
                    continue
                if not fused:
                    # Single-camera verification: one track per file only.
                    if video.track_ids != frozenset({tid}):
                        continue
                elif tid not in video.track_ids:
                    overlap = _overlap_seconds(
                        video.started_at,
                        video.ended_at,
                        t_start,
                        t_end,
                    )
                    if overlap <= 0.0:
                        continue

                score = 10_000.0 + _overlap_seconds(
                    video.started_at,
                    video.ended_at,
                    t_start,
                    t_end,
                )
                if score > best_score:
                    best_score = score
                    best = video

            if best is None:
                return None

            if fused and len(best.track_ids) > 1:
                # Multi-boat fused clip: promote via copy per detection, do not exclusive-claim.
                return best
            self._claimed_uris.add(best.uri)
            return best

    def take_for_any_track_ids(
        self,
        track_ids: list[str],
        start_ts: float,
        end_ts: float,
        *,
        fused: bool,
    ) -> RecordedVideo | None:
        seen: set[str] = set()
        for tid in track_ids:
            key = str(tid)
            if not key or key in seen:
                continue
            seen.add(key)
            found = self.take_for_track(key, start_ts, end_ts, fused=fused)
            if found is not None:
                return found
        if not fused:
            return None
        # Fused fallback: time overlap when recorder only tagged local trk_* ids.
        t_start = float(start_ts)
        t_end = float(end_ts)
        if t_end < t_start:
            t_start, t_end = t_end, t_start
        with self._lock:
            best: RecordedVideo | None = None
            best_score = -1.0
            for video in self._fused:
                if video.uri in self._claimed_uris and len(video.track_ids) <= 1:
                    continue
                overlap = _overlap_seconds(
                    video.started_at, video.ended_at, t_start, t_end,
                )
                if overlap <= 0.0:
                    continue
                score = overlap
                if score > best_score:
                    best_score = score
                    best = video
            if best is None:
                return None
            if len(best.track_ids) <= 1:
                self._claimed_uris.add(best.uri)
            return best

    def find_for_track(
        self,
        track_id: str,
        start_ts: float,
        end_ts: float,
        *,
        fused: bool,
    ) -> RecordedVideo | None:
        """Non-mutating lookup (late attach after detection persist)."""
        tid = str(track_id)
        t_start = float(start_ts)
        t_end = float(end_ts)
        if t_end < t_start:
            t_start, t_end = t_end, t_start

        with self._lock:
            pool = self._fused if fused else self._single
            best: RecordedVideo | None = None
            best_score = -1.0
            for video in pool:
                if video.uri in self._claimed_uris:
                    continue
                if not fused:
                    if video.track_ids != frozenset({tid}):
                        continue
                elif tid not in video.track_ids:
                    overlap = _overlap_seconds(
                        video.started_at,
                        video.ended_at,
                        t_start,
                        t_end,
                    )
                    if overlap <= 0.0:
                        continue
                score = 10_000.0 + _overlap_seconds(
                    video.started_at,
                    video.ended_at,
                    t_start,
                    t_end,
                )
                if score > best_score:
                    best_score = score
                    best = video
            return best

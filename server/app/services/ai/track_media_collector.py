"""Per-track IN/OUT overlay snapshots for MinIO export (fused + single-camera views).

Capture model: 4 comparison images per detection, taken at the two berth-boundary
crossing moments (IN and OUT), NOT best-shot by confidence.

  - single_overlay_in / single_overlay_out : single-camera overlay frame at the
    IN / OUT crossing instant.
  - fused_overlay_in / fused_overlay_out   : fused overlay frame at the same
    IN / OUT instant.

Fallback: a track that never emits a clean OUT (e.g. still moored at finalize)
uses the latest overlay frame of the detection as its OUT image. There is no
best-shot fallback.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import cv2
import numpy as np


_JPEG_Q = 92


def encode_jpeg_bgr(frame_bgr: np.ndarray | None) -> bytes | None:
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    ok, enc = cv2.imencode('.jpg', frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_Q])
    return enc.tobytes() if ok else None


@dataclass
class TrackMediaSnapshot:
    """IN/OUT overlay JPEGs + latest-frame fallback, gathered until finalize."""

    # Discrete crossing captures (encoded inline when the event fires).
    single_overlay_in_jpeg: bytes | None = None
    single_overlay_in_camera_id: int | None = None
    single_overlay_out_jpeg: bytes | None = None
    single_overlay_out_camera_id: int | None = None
    fused_overlay_in_jpeg: bytes | None = None
    fused_overlay_out_jpeg: bytes | None = None

    # Latest overlay frames (raw, encoded lazily at finalize only if OUT missing).
    single_latest_frame: np.ndarray | None = None
    single_latest_camera_id: int | None = None
    single_latest_ts: float = field(default=-1.0)
    fused_latest_frame: np.ndarray | None = None
    fused_latest_ts: float = field(default=-1.0)


class TrackMediaCollector:
    """Thread-safe: set IN/OUT overlays on crossing; track latest for fallback; pop at finalize."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_track: dict[str, TrackMediaSnapshot] = {}

    def set_boundary_overlay(
        self,
        track_id: str,
        direction: str,
        camera_id: int,
        single_bgr: np.ndarray | None,
        fused_bgr: np.ndarray | None,
    ) -> None:
        """Capture single + fused overlay at an IN/OUT crossing (encoded inline; rare event)."""
        if direction not in ('in', 'out'):
            return
        single_jpeg = encode_jpeg_bgr(single_bgr)
        fused_jpeg = encode_jpeg_bgr(fused_bgr)
        if not single_jpeg and not fused_jpeg:
            return
        tid = str(track_id)
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            if direction == 'in':
                if single_jpeg:
                    snap.single_overlay_in_jpeg = single_jpeg
                    snap.single_overlay_in_camera_id = int(camera_id)
                if fused_jpeg:
                    snap.fused_overlay_in_jpeg = fused_jpeg
            else:
                if single_jpeg:
                    snap.single_overlay_out_jpeg = single_jpeg
                    snap.single_overlay_out_camera_id = int(camera_id)
                if fused_jpeg:
                    snap.fused_overlay_out_jpeg = fused_jpeg

    def update_latest_single(
        self,
        track_id: str,
        camera_id: int,
        frame_bgr: np.ndarray,
        ts: float,
    ) -> None:
        if frame_bgr is None or frame_bgr.size == 0:
            return
        tid = str(track_id)
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            if ts <= snap.single_latest_ts:
                return
            snap.single_latest_frame = frame_bgr
            snap.single_latest_camera_id = int(camera_id)
            snap.single_latest_ts = ts

    def update_latest_fused(
        self,
        track_id: str,
        frame_bgr: np.ndarray,
        ts: float,
    ) -> None:
        if frame_bgr is None or frame_bgr.size == 0:
            return
        tid = str(track_id)
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            if ts <= snap.fused_latest_ts:
                return
            snap.fused_latest_frame = frame_bgr
            snap.fused_latest_ts = ts

    def pop(self, track_id: str) -> TrackMediaSnapshot | None:
        tid = str(track_id)
        with self._lock:
            return self._by_track.pop(tid, None)

    def pop_any(self, track_ids: list[str]) -> TrackMediaSnapshot | None:
        """Pop and merge snapshots for global + per-camera local track keys."""
        merged: TrackMediaSnapshot | None = None
        with self._lock:
            for tid in track_ids:
                snap = self._by_track.pop(str(tid), None)
                if snap is None:
                    continue
                if merged is None:
                    merged = snap
                    continue
                # IN/OUT crossings are unique events — keep first non-None.
                if merged.single_overlay_in_jpeg is None and snap.single_overlay_in_jpeg:
                    merged.single_overlay_in_jpeg = snap.single_overlay_in_jpeg
                    merged.single_overlay_in_camera_id = snap.single_overlay_in_camera_id
                if merged.single_overlay_out_jpeg is None and snap.single_overlay_out_jpeg:
                    merged.single_overlay_out_jpeg = snap.single_overlay_out_jpeg
                    merged.single_overlay_out_camera_id = snap.single_overlay_out_camera_id
                if merged.fused_overlay_in_jpeg is None and snap.fused_overlay_in_jpeg:
                    merged.fused_overlay_in_jpeg = snap.fused_overlay_in_jpeg
                if merged.fused_overlay_out_jpeg is None and snap.fused_overlay_out_jpeg:
                    merged.fused_overlay_out_jpeg = snap.fused_overlay_out_jpeg
                # Latest frame fallback — keep the most recent across keys.
                if snap.single_latest_frame is not None and snap.single_latest_ts > merged.single_latest_ts:
                    merged.single_latest_frame = snap.single_latest_frame
                    merged.single_latest_camera_id = snap.single_latest_camera_id
                    merged.single_latest_ts = snap.single_latest_ts
                if snap.fused_latest_frame is not None and snap.fused_latest_ts > merged.fused_latest_ts:
                    merged.fused_latest_frame = snap.fused_latest_frame
                    merged.fused_latest_ts = snap.fused_latest_ts
        return merged

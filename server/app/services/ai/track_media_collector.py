"""Per-track best-shot buffers for MinIO export (fused + single-camera views)."""
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
    """JPEG payloads + scores gathered until track finalize."""

    fused_best_detection_jpeg: bytes | None = None
    fused_best_detection_conf: float = field(default=-1.0)
    fused_best_ocr_jpeg: bytes | None = None
    fused_best_ocr_conf: float = field(default=-1.0)
    fused_best_ocr_ship_id: str | None = None
    single_best_detection_jpeg: bytes | None = None
    single_best_detection_conf: float = field(default=-1.0)
    single_best_camera_id: int | None = None
    single_best_ocr_jpeg: bytes | None = None
    single_best_ocr_conf: float = field(default=-1.0)
    single_best_ocr_ship_id: str | None = None
    single_best_ocr_camera_id: int | None = None


class TrackMediaCollector:
    """Thread-safe: update with running max confidence; pop at detection finalize."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_track: dict[str, TrackMediaSnapshot] = {}

    def update_fused_detection(
        self,
        track_id: str,
        conf: float,
        fused_bgr: np.ndarray,
    ) -> None:
        tid = str(track_id)
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            if conf <= snap.fused_best_detection_conf:
                return
        data = encode_jpeg_bgr(fused_bgr)
        if not data:
            return
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            if conf > snap.fused_best_detection_conf:
                snap.fused_best_detection_conf = conf
                snap.fused_best_detection_jpeg = data

    def update_single_detection(
        self,
        track_id: str,
        conf: float,
        camera_id: int,
        frame_bgr: np.ndarray,
    ) -> None:
        tid = str(track_id)
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            if conf <= snap.single_best_detection_conf:
                return
        data = encode_jpeg_bgr(frame_bgr)
        if not data:
            return
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            if conf > snap.single_best_detection_conf:
                snap.single_best_detection_conf = conf
                snap.single_best_detection_jpeg = data
                snap.single_best_camera_id = int(camera_id)

    def update_ocr(
        self,
        track_id: str,
        ocr_conf: float,
        ship_id: str,
        single_bgr: np.ndarray,
        fused_bgr: np.ndarray | None,
        camera_id: int | None,
    ) -> None:
        tid = str(track_id)
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            need_single = ocr_conf > snap.single_best_ocr_conf
            need_fused = fused_bgr is not None and ocr_conf > snap.fused_best_ocr_conf

        single_jpeg = encode_jpeg_bgr(single_bgr) if need_single else None
        fused_jpeg = encode_jpeg_bgr(fused_bgr) if need_fused else None
        if not single_jpeg and not fused_jpeg:
            return
        with self._lock:
            snap = self._by_track.setdefault(tid, TrackMediaSnapshot())
            if single_jpeg and ocr_conf > snap.single_best_ocr_conf:
                snap.single_best_ocr_conf = ocr_conf
                snap.single_best_ocr_jpeg = single_jpeg
                snap.single_best_ocr_ship_id = ship_id
                if camera_id is not None:
                    snap.single_best_ocr_camera_id = int(camera_id)
            if fused_jpeg and ocr_conf > snap.fused_best_ocr_conf:
                snap.fused_best_ocr_conf = ocr_conf
                snap.fused_best_ocr_jpeg = fused_jpeg
                snap.fused_best_ocr_ship_id = ship_id

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
                if snap.fused_best_detection_jpeg and (
                    snap.fused_best_detection_conf > merged.fused_best_detection_conf
                ):
                    merged.fused_best_detection_conf = snap.fused_best_detection_conf
                    merged.fused_best_detection_jpeg = snap.fused_best_detection_jpeg
                if snap.fused_best_ocr_jpeg and snap.fused_best_ocr_conf > merged.fused_best_ocr_conf:
                    merged.fused_best_ocr_conf = snap.fused_best_ocr_conf
                    merged.fused_best_ocr_jpeg = snap.fused_best_ocr_jpeg
                    merged.fused_best_ocr_ship_id = snap.fused_best_ocr_ship_id
                if snap.single_best_detection_jpeg and (
                    snap.single_best_detection_conf > merged.single_best_detection_conf
                ):
                    merged.single_best_detection_conf = snap.single_best_detection_conf
                    merged.single_best_detection_jpeg = snap.single_best_detection_jpeg
                    merged.single_best_camera_id = snap.single_best_camera_id
                if snap.single_best_ocr_jpeg and snap.single_best_ocr_conf > merged.single_best_ocr_conf:
                    merged.single_best_ocr_conf = snap.single_best_ocr_conf
                    merged.single_best_ocr_jpeg = snap.single_best_ocr_jpeg
                    merged.single_best_ocr_ship_id = snap.single_best_ocr_ship_id
                    merged.single_best_ocr_camera_id = snap.single_best_ocr_camera_id
        return merged

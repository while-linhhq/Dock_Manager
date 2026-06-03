from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.services.ai.boat_tracker import TrackedBoat, TrackState
from app.services.ship_id_utils import is_unknown_ship_id, normalize_ship_id
from app.utils.ai.pipeline_utils import clamp_box, ocr_cache_key_track

logger = logging.getLogger(__name__)

OTHERS_DIR = 'others'
_SAFE_SHIP_ID_PATTERN = re.compile(r'[^A-Za-z0-9._-]+')


@dataclass(frozen=True)
class TrainingSnapshotConfig:
    enabled: bool = False
    interval_sec: float = 5.0
    base_dir: Path = Path('snapshot')
    jpeg_quality: int = 95


class TrainingSnapshotCollector:
    """Save full-quality vessel crops for model training under base_dir/<ship_id>/ or others/."""

    def __init__(self, config: TrainingSnapshotConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._last_capture_ts: dict[int, float] = {}
        self._saved_count = 0

    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    def maybe_save(
        self,
        *,
        camera_id: int,
        raw_frame: np.ndarray,
        track: TrackedBoat,
        ocr_cache: dict | None,
        ocr_lock: threading.RLock | threading.Lock | None,
        boat_tracker=None,
    ) -> bool:
        if not self._config.enabled:
            return False
        if track.state != TrackState.CONFIRMED:
            return False
        if raw_frame is None or raw_frame.size == 0:
            return False

        now = time.time()
        with self._lock:
            last = self._last_capture_ts.get(int(camera_id), 0.0)
            if now - last < float(self._config.interval_sec):
                return False
            self._last_capture_ts[int(camera_id)] = now

        ship_id = self._resolve_ship_id(
            track=track,
            ocr_cache=ocr_cache,
            ocr_lock=ocr_lock,
            boat_tracker=boat_tracker,
        )
        folder = _ship_id_to_folder(ship_id)

        height, width = raw_frame.shape[:2]
        x1, y1, x2, y2 = clamp_box(track.box, width, height)
        if x2 <= x1 or y2 <= y1:
            return False

        crop = raw_frame[y1:y2, x1:x2].copy()
        if crop.size == 0:
            return False

        dest_dir = self._config.base_dir / folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Use microseconds to avoid filename collisions within the same second.
        millis = int((now - int(now)) * 1000)
        ts = time.strftime('%Y%m%d_%H%M%S', time.localtime(now)) + f'_{millis:03d}'
        short_track = str(track.track_id).replace('/', '_')[-12:]
        filename = f'{ts}_cam{camera_id}_{short_track}.jpg'
        out_path = dest_dir / filename

        ok = cv2.imwrite(
            str(out_path),
            crop,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(self._config.jpeg_quality)],
        )
        if ok:
            self._saved_count += 1
            logger.debug(
                'training snapshot saved path=%s ship=%s camera=%s',
                out_path,
                folder,
                camera_id,
            )
        return bool(ok)

    def _resolve_ship_id(
        self,
        *,
        track: TrackedBoat,
        ocr_cache: dict | None,
        ocr_lock: threading.RLock | threading.Lock | None,
        boat_tracker=None,
    ) -> str | None:
        for candidate in (track.ship_id, track.last_known_ship_id):
            sid = normalize_ship_id(candidate)
            if sid and not is_unknown_ship_id(sid):
                return sid

        if boat_tracker is not None:
            summary = boat_tracker.get_vote_summary(str(track.track_id))
            if summary:
                best_sid = max(
                    summary,
                    key=lambda sid: float(summary[sid].get('total_conf', 0.0)),
                )
                voted_sid = normalize_ship_id(best_sid)
                if (
                    voted_sid
                    and not is_unknown_ship_id(voted_sid)
                ):
                    return voted_sid

        if ocr_cache is not None and ocr_lock is not None:
            ck = ocr_cache_key_track(str(track.track_id), track.camera_id)
            with ocr_lock:
                ent = ocr_cache.get(ck)
            if isinstance(ent, dict):
                ocr_text = normalize_ship_id(str(ent.get('text') or ''))
                if ocr_text and not is_unknown_ship_id(ocr_text):
                    return ocr_text
                visual_sid = normalize_ship_id(str(ent.get('visual_ship_id') or ''))
                if (
                    visual_sid
                    and not is_unknown_ship_id(visual_sid)
                ):
                    return visual_sid

        return None


def _ship_id_to_folder(ship_id: str | None) -> str:
    if not ship_id or is_unknown_ship_id(ship_id):
        return OTHERS_DIR
    cleaned = _SAFE_SHIP_ID_PATTERN.sub('_', ship_id.strip())
    cleaned = cleaned.strip('._-') or OTHERS_DIR
    return cleaned[:64] if cleaned else OTHERS_DIR

"""Persist "empty port" baselines for seam anchor background models.

Baseline frames are written to local disk so they survive restarts and are
applied to ``BackgroundModel.lock_from_frame`` on next pipeline start.
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from app.utils.ai.frame_quality import is_usable_bgr_frame

_log = logging.getLogger(__name__)

_BASELINE_ROOT = Path('app/runtime-media/seam_baselines')


def _baseline_path(group_id: int | None, camera_id: int) -> Path:
    group_segment = f'group_{int(group_id)}' if group_id is not None else 'no_group'
    return _BASELINE_ROOT / group_segment / f'camera_{int(camera_id)}.jpg'


def save_baseline(group_id: int | None, camera_id: int, frame_bgr: np.ndarray) -> str | None:
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    if not is_usable_bgr_frame(frame_bgr):
        _log.warning(
            'seam_baseline: rejected low-quality frame camera_id=%s group_id=%s',
            camera_id,
            group_id,
        )
        return None
    target = _baseline_path(group_id, camera_id)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode('.jpg', frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok:
            _log.warning('seam_baseline: encode failed for camera_id=%s', camera_id)
            return None
        target.write_bytes(encoded.tobytes())
        return str(target)
    except Exception:
        _log.exception('seam_baseline: failed to save baseline camera_id=%s', camera_id)
        return None


def load_baseline(group_id: int | None, camera_id: int) -> np.ndarray | None:
    target = _baseline_path(group_id, camera_id)
    if not target.exists():
        return None
    try:
        frame = cv2.imread(str(target), cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            return None
        return frame
    except Exception:
        _log.exception('seam_baseline: failed to read baseline camera_id=%s', camera_id)
        return None


def has_baseline(group_id: int | None, camera_id: int) -> bool:
    return _baseline_path(group_id, camera_id).exists()


def delete_baseline(group_id: int | None, camera_id: int) -> bool:
    target = _baseline_path(group_id, camera_id)
    if not target.exists():
        return False
    try:
        target.unlink()
        return True
    except Exception:
        _log.exception('seam_baseline: failed to delete baseline camera_id=%s', camera_id)
        return False

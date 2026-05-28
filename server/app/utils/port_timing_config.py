"""Port config timing keys: seconds-first, legacy frame keys migrated via record_fps."""

from __future__ import annotations

LEGACY_FRAME_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        'ocr_interval_frames',
        'track_min_hits',
        'track_max_tentative_misses',
        'track_max_lost_frames',
    }
)

FRAME_TO_SEC_KEY: dict[str, str] = {
    'ocr_interval_frames': 'ocr_interval_sec',
    'track_min_hits': 'track_min_confirm_sec',
    'track_max_tentative_misses': 'track_max_tentative_sec',
    'track_max_lost_frames': 'track_max_lost_sec',
}

DEFAULT_SEC_BY_KEY: dict[str, float] = {
    'ocr_interval_sec': 0.5,
    'track_min_confirm_sec': 1.5,
    'track_max_tentative_sec': 0.5,
    'track_max_lost_sec': 4.0,
}


def frames_to_seconds(frames: float, fps: float) -> float:
    return max(0.01, float(frames) / max(1.0, float(fps)))


def resolve_positive_seconds(
    cfg_map: dict[str, str],
    *,
    sec_key: str,
    legacy_frame_key: str,
    default_sec: float,
    fps: float,
) -> float:
    raw_sec = cfg_map.get(sec_key)
    if raw_sec is not None and str(raw_sec).strip() != '':
        try:
            value = float(str(raw_sec).strip())
            if value > 0:
                return value
        except ValueError:
            pass

    raw_frames = cfg_map.get(legacy_frame_key)
    if raw_frames is not None and str(raw_frames).strip() != '':
        try:
            frames = float(str(raw_frames).strip())
            if frames > 0:
                return frames_to_seconds(frames, fps)
        except ValueError:
            pass

    return max(0.01, float(default_sec))

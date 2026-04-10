"""Đường dẫn lưu detect: {base}/cap|crops|videos|ocr_audit theo ngày (YYYY-MM-DD)."""
import os
from datetime import datetime

RUNS_DETECT = os.path.join("runs", "detect")


def cap_dir_for_today(base: str = RUNS_DETECT) -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(base, "cap", day)


def crops_dir_for_today(base: str = RUNS_DETECT) -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(base, "crops", day)


def videos_dir_for_today(base: str = RUNS_DETECT) -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(base, "videos", day)


def ocr_audit_frames_dir_for_today(base: str = RUNS_DETECT) -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(base, "ocr_audit", "frames", day)


def ocr_audit_logs_dir_for_today(base: str = RUNS_DETECT) -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(base, "ocr_audit", "logs", day)


def timestamp_prefix() -> str:
    """YYYYMMDD_HHMMSS_mmm (milliseconds 3 chữ số)."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path

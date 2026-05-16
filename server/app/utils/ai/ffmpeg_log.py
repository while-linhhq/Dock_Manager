"""Reduce libav/FFmpeg stderr spam when decoding RTSP HEVC streams."""
from __future__ import annotations

import os


def suppress_ffmpeg_decoder_logs() -> None:
    os.environ.setdefault('AV_LOG_LEVEL', 'quiet')
    os.environ.setdefault('OPENCV_FFMPEG_LOGLEVEL', '8')

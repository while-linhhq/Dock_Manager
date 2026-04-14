from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg


def transcode_to_h264_faststart(
    src: str | Path,
    dst: str | Path,
    *,
    preset: str = "veryfast",
    crf: int = 23,
) -> None:
    """
    Transcode MP4 to H.264/AAC with moov atom at front.
    Uses imageio-ffmpeg bundled ffmpeg binary.
    """
    src_p = Path(src)
    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        '-y',
        '-i',
        str(src_p),
        # video
        '-c:v',
        'libx264',
        '-preset',
        str(preset),
        '-crf',
        str(int(crf)),
        # audio (if none, ffmpeg will ignore)
        '-c:a',
        'aac',
        '-b:a',
        '128k',
        # web-friendly
        '-movflags',
        '+faststart',
        str(dst_p),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


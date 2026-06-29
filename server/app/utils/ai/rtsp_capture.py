"""RTSP capture: OpenCV (software) or FFmpeg NVDEC (hardware)."""

from __future__ import annotations

import json
import logging
import re
import select
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.utils.ai.ffmpeg_log import suppress_ffmpeg_decoder_logs

suppress_ffmpeg_decoder_logs()

import cv2  # noqa: E402

logger = logging.getLogger(__name__)

_STREAM_SIZE_RE = re.compile(r'\b(\d{2,5})x(\d{2,5})\b')
_HWACCEL_CANDIDATES = ('cuda', 'nvdec')


@dataclass
class RtspDecodeOptions:
    use_nvdec: bool = False
    ffmpeg_path: str = ''
    rtsp_transport: str = 'tcp'
    hwaccel: str = 'cuda'
    output_scale: float = 1.0


_options = RtspDecodeOptions(
    use_nvdec=bool(settings.RTSP_NVDEC_ENABLED),
    ffmpeg_path=str(settings.FFMPEG_PATH or '').strip(),
    rtsp_transport=str(settings.RTSP_TRANSPORT or 'tcp').strip() or 'tcp',
    hwaccel=str(settings.RTSP_NVDEC_HWACCEL or 'cuda').strip() or 'cuda',
    output_scale=1.0,
)

_nvdec_cache: dict[str, bool] = {}
_hwaccel_cache: dict[str, str | None] = {}


def configure_rtsp_decode(
    *,
    use_nvdec: bool | None = None,
    ffmpeg_path: str | None = None,
    rtsp_transport: str | None = None,
    hwaccel: str | None = None,
    output_scale: float | None = None,
) -> None:
    """Runtime override (pipeline start reads port_configs)."""
    global _options
    if use_nvdec is not None:
        _options.use_nvdec = bool(use_nvdec)
    if ffmpeg_path is not None:
        _options.ffmpeg_path = str(ffmpeg_path).strip()
    if rtsp_transport is not None:
        value = str(rtsp_transport).strip() or 'tcp'
        _options.rtsp_transport = value
    if hwaccel is not None:
        _options.hwaccel = str(hwaccel).strip() or 'cuda'
    if output_scale is not None:
        _options.output_scale = max(0.1, min(1.0, float(output_scale)))


def scaled_frame_dims(width: int, height: int, scale: float) -> tuple[int, int]:
    """Even dimensions for ffmpeg scale; scale=1 keeps source size."""
    src_w, src_h = int(width), int(height)
    if src_w <= 0 or src_h <= 0:
        return src_w, src_h
    factor = max(0.1, min(1.0, float(scale)))
    if factor >= 0.99:
        return src_w, src_h
    out_w = max(2, int(src_w * factor) // 2 * 2)
    out_h = max(2, int(src_h * factor) // 2 * 2)
    return out_w, out_h


def resolve_ffmpeg_path(explicit: str = '') -> str:
    for candidate in (
        str(explicit or '').strip(),
        str(_options.ffmpeg_path or '').strip(),
        str(settings.FFMPEG_PATH or '').strip(),
        shutil.which('ffmpeg') or '',
    ):
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_absolute():
            server_root = Path(__file__).resolve().parents[3]
            path = server_root / path
        if path.is_file():
            return str(path)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return 'ffmpeg'


def _ffmpeg_hwaccels(ffmpeg_path: str) -> set[str]:
    try:
        proc = subprocess.run(
            [ffmpeg_path, '-hide_banner', '-hwaccels'],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        logger.warning('ffmpeg hwaccels probe failed (%s): %s', ffmpeg_path, err)
        return set()
    text = f'{proc.stdout or ""}\n{proc.stderr or ""}'.lower()
    found: set[str] = set()
    for line in text.splitlines():
        token = line.strip().lower()
        if token in _HWACCEL_CANDIDATES or token == 'cuda':
            found.add(token)
    if 'cuda' in text:
        found.add('cuda')
    if 'nvdec' in text:
        found.add('nvdec')
    return found


def resolve_nvdec_hwaccel(ffmpeg_path: str) -> str | None:
    cached = _hwaccel_cache.get(ffmpeg_path)
    if cached is not None or ffmpeg_path in _hwaccel_cache:
        return cached

    hwaccels = _ffmpeg_hwaccels(ffmpeg_path)
    preferred = (_options.hwaccel, 'cuda', 'nvdec')
    chosen = next((name for name in preferred if name in hwaccels), None)
    _hwaccel_cache[ffmpeg_path] = chosen
    return chosen


def nvdec_available(ffmpeg_path: str | None = None) -> bool:
    path = resolve_ffmpeg_path(ffmpeg_path or '')
    if path in _nvdec_cache:
        return _nvdec_cache[path]
    ok = resolve_nvdec_hwaccel(path) is not None
    _nvdec_cache[path] = ok
    return ok


def nvdec_status() -> str:
    path = resolve_ffmpeg_path()
    if not _options.use_nvdec:
        return f'disabled (ffmpeg={path})'
    hw = resolve_nvdec_hwaccel(path)
    if hw:
        return (
            f'enabled hwaccel={hw} output_scale={_options.output_scale} ({path})'
        )
    return f'requested but unavailable — fallback OpenCV ({path})'


def _ffprobe_path(ffmpeg_path: str) -> str:
    if ffmpeg_path.endswith('ffmpeg'):
        return f'{ffmpeg_path[:-6]}ffprobe'
    sibling = Path(ffmpeg_path).with_name('ffprobe')
    if sibling.is_file():
        return str(sibling)
    return shutil.which('ffprobe') or 'ffprobe'


def _probe_stream_size_ffprobe(
    ffmpeg_path: str,
    url: str,
    *,
    rtsp_transport: str,
    timeout_sec: float = 20.0,
) -> tuple[int, int] | None:
    ffprobe = _ffprobe_path(ffmpeg_path)
    cmd = [
        ffprobe,
        '-hide_banner',
        '-rtsp_transport',
        rtsp_transport,
        '-v',
        'error',
        '-select_streams',
        'v:0',
        '-show_entries',
        'stream=width,height',
        '-of',
        'json',
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if proc.returncode != 0:
        return None

    try:
        payload = json.loads(proc.stdout or '{}')
        streams = payload.get('streams') or []
        if not streams:
            return None
        stream = streams[0]
        width = int(stream.get('width') or 0)
        height = int(stream.get('height') or 0)
        if width > 0 and height > 0:
            return width, height
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    match = _STREAM_SIZE_RE.search(proc.stdout or '')
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def _probe_stream_size(
    ffmpeg_path: str,
    url: str,
    *,
    rtsp_transport: str,
    hwaccel: str | None,
    timeout_sec: float = 20.0,
) -> tuple[int, int]:
    """Probe resolution via ffprobe, then optional ffmpeg one-frame fallback."""
    probed = _probe_stream_size_ffprobe(
        ffmpeg_path,
        url,
        rtsp_transport=rtsp_transport,
        timeout_sec=timeout_sec,
    )
    if probed is not None:
        return probed

    attempts: list[str | None] = [None]
    if hwaccel:
        attempts.append(hwaccel)

    last_error = ''
    for accel in attempts:
        cmd = [
            ffmpeg_path,
            '-hide_banner',
            '-loglevel',
            'error',
            '-rtsp_transport',
            rtsp_transport,
        ]
        if accel:
            cmd.extend(['-hwaccel', accel])
        cmd.extend(['-i', url, '-frames:v', '1', '-f', 'null', '-'])
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as err:
            raise RuntimeError(f'RTSP probe timeout for {url!r}') from err

        combined = f'{proc.stderr or ""}\n{proc.stdout or ""}'
        matches = _STREAM_SIZE_RE.findall(combined)
        if matches:
            width, height = (int(matches[-1][0]), int(matches[-1][1]))
            if width > 0 and height > 0:
                return width, height
        last_error = combined.strip()[-400:] or str(proc.returncode)

    raise RuntimeError(f'Could not probe RTSP resolution: {last_error}')


def _build_nvdec_cmd(
    *,
    ffmpeg_path: str,
    url: str,
    rtsp_transport: str,
    hwaccel: str,
    width: int,
    height: int,
    use_hwdownload: bool = True,
) -> list[str]:
    """CUDA decode → packed BGR24 (matches OpenCV layout)."""
    head = [
        ffmpeg_path,
        '-hide_banner',
        '-loglevel',
        'error',
        '-rtsp_transport',
        rtsp_transport,
        '-fflags',
        '+genpts+discardcorrupt',
        '-flags',
        'low_delay',
        '-hwaccel',
        hwaccel,
    ]
    tail = [
        '-an',
        '-sn',
        '-dn',
        '-pix_fmt',
        'bgr24',
        '-s',
        f'{width}x{height}',
        '-vsync',
        'passthrough',
        '-f',
        'rawvideo',
        'pipe:1',
    ]
    if use_hwdownload:
        return [
            *head,
            '-hwaccel_output_format',
            'cuda',
            '-extra_hw_frames',
            '4',
            '-i',
            url,
            '-vf',
            f'hwdownload,format=bgr24,scale={width}:{height}:flags=fast_bilinear',
            *tail,
        ]
    return [
        *head,
        '-i',
        url,
        '-vf',
        f'scale={width}:{height}:flags=fast_bilinear',
        *tail,
    ]


class FfmpegNvdecCapture:
    """FFmpeg subprocess decoder with VideoCapture-like API."""

    def __init__(
        self,
        url: str,
        *,
        ffmpeg_path: str,
        rtsp_transport: str,
        hwaccel: str,
        output_scale: float = 1.0,
        probe_timeout_sec: float = 20.0,
        read_timeout_sec: float = 20.0,
        warmup_frames: int = 1,
    ) -> None:
        self._url = url
        self._ffmpeg_path = ffmpeg_path
        self._rtsp_transport = rtsp_transport
        self._hwaccel = hwaccel
        self._output_scale = max(0.1, min(1.0, float(output_scale)))
        self._probe_timeout_sec = probe_timeout_sec
        self._read_timeout_sec = read_timeout_sec
        self._warmup_frames = max(0, int(warmup_frames))
        self._proc: subprocess.Popen[bytes] | None = None
        self._width = 0
        self._height = 0
        self._frame_bytes = 0
        self._read_buffer = bytearray()
        self._opened = False
        self._pending_frame: np.ndarray | None = None
        self._open()

    def isOpened(self) -> bool:  # noqa: N802 — OpenCV API
        return self._opened and self._proc is not None and self._proc.poll() is None

    def set(self, prop_id: int, value: float) -> bool:  # noqa: N802
        if prop_id == cv2.CAP_PROP_BUFFERSIZE:
            return True
        return False

    def release(self) -> None:
        self._opened = False
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.kill()
        except OSError as err:
            logger.debug('ffmpeg kill failed: %s', err)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

    def grab(self) -> bool:  # noqa: N802
        frame = self._read_raw_frame()
        if frame is None:
            return False
        self._pending_frame = frame
        return True

    def retrieve(self) -> tuple[bool, np.ndarray | None]:  # noqa: N802
        if self._pending_frame is None:
            return False, None
        frame = self._pending_frame
        self._pending_frame = None
        return True, frame

    def read(self) -> tuple[bool, np.ndarray | None]:  # noqa: N802
        frame = self._read_raw_frame()
        if frame is None:
            return False, None
        return True, frame

    def _open(self) -> None:
        self.release()
        try:
            probed = _probe_stream_size(
                self._ffmpeg_path,
                self._url,
                rtsp_transport=self._rtsp_transport,
                hwaccel=self._hwaccel,
                timeout_sec=self._probe_timeout_sec,
            )
        except Exception as err:
            logger.warning('NVDEC RTSP probe failed for %s: %s', self._url, err)
            return

        src_w, src_h = probed
        width, height = scaled_frame_dims(src_w, src_h, self._output_scale)
        for use_hwdownload in (False, True):
            if self._try_open_process(
                src_w=src_w,
                src_h=src_h,
                width=width,
                height=height,
                use_hwdownload=use_hwdownload,
            ):
                return
        self._opened = False

    def _try_open_process(
        self,
        *,
        src_w: int,
        src_h: int,
        width: int,
        height: int,
        use_hwdownload: bool,
    ) -> bool:
        cmd = _build_nvdec_cmd(
            ffmpeg_path=self._ffmpeg_path,
            url=self._url,
            rtsp_transport=self._rtsp_transport,
            hwaccel=self._hwaccel,
            width=width,
            height=height,
            use_hwdownload=use_hwdownload,
        )
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as err:
            logger.warning('NVDEC ffmpeg spawn failed: %s', err)
            return False

        self._proc = proc
        self._width = width
        self._height = height
        self._frame_bytes = width * height * 3
        self._read_buffer = bytearray(self._frame_bytes)
        self._opened = True

        if proc.poll() is not None:
            stderr_tail = self._read_stderr_tail(proc)
            logger.warning(
                'NVDEC ffmpeg exited immediately (hwdownload=%s code=%s): %s',
                use_hwdownload,
                proc.returncode,
                stderr_tail,
            )
            self.release()
            return False

        for _ in range(self._warmup_frames):
            if self._read_raw_frame() is None:
                stderr_tail = self._read_stderr_tail(proc)
                logger.warning(
                    'NVDEC warmup read failed for %s (hwdownload=%s code=%s): %s',
                    self._url,
                    use_hwdownload,
                    proc.returncode,
                    stderr_tail,
                )
                self.release()
                return False

        logger.info(
            'NVDEC RTSP opened %dx%d (src %dx%d scale=%.2f hwdownload=%s) '
            'hwaccel=%s transport=%s',
            width,
            height,
            src_w,
            src_h,
            self._output_scale,
            use_hwdownload,
            self._hwaccel,
            self._rtsp_transport,
        )
        return True

    @staticmethod
    def _read_stderr_tail(proc: subprocess.Popen[bytes]) -> str:
        if proc.stderr is None:
            return ''
        try:
            raw = proc.stderr.read(4096)
        except OSError:
            return ''
        return raw.decode('utf-8', errors='ignore').strip()[-400:]

    def _read_exact(self, size: int) -> bool:
        """Read exactly `size` bytes. Never abort mid-frame (prevents pipe misalignment)."""
        if not self.isOpened() or self._proc is None or self._proc.stdout is None:
            return False
        if size != len(self._read_buffer):
            self._read_buffer = bytearray(size)
        stream = self._proc.stdout
        view = memoryview(self._read_buffer)
        remaining = size
        offset = 0
        while remaining > 0:
            try:
                ready, _, _ = select.select([stream], [], [], self._read_timeout_sec)
            except (ValueError, OSError):
                return False
            if not ready:
                logger.warning('NVDEC RTSP read timeout — stream may be lost')
                return False
            try:
                chunk = stream.readinto(view[offset : offset + remaining])
            except OSError as err:
                logger.warning('NVDEC RTSP read failed: %s', err)
                return False
            if not chunk:
                if self._proc.poll() is not None:
                    logger.warning('NVDEC ffmpeg exited (code=%s)', self._proc.returncode)
                return False
            offset += int(chunk)
            remaining -= int(chunk)
        return True

    def _frame_from_buffer(self) -> np.ndarray:
        return np.frombuffer(self._read_buffer, dtype=np.uint8).reshape(
            (self._height, self._width, 3)
        ).copy()

    def _read_raw_frame(self) -> np.ndarray | None:
        if not self._read_exact(self._frame_bytes):
            return None
        return self._frame_from_buffer()


def read_latest_frame(cap: Any) -> tuple[bool, Any | None]:
    """Sequential realtime read — same semantics as OpenCV VideoCapture.read()."""
    return cap.read()


def open_rtsp(rtsp_url: str) -> Any:
    """Open RTSP with NVDEC when enabled and available, else OpenCV FFmpeg."""
    if not _options.use_nvdec:
        return cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    ffmpeg_path = resolve_ffmpeg_path()
    hwaccel = resolve_nvdec_hwaccel(ffmpeg_path)
    if hwaccel is None:
        logger.warning(
            'RTSP_NVDEC enabled but ffmpeg has no cuda/nvdec hwaccel (%s) — using OpenCV',
            ffmpeg_path,
        )
        return cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    capture = FfmpegNvdecCapture(
        rtsp_url,
        ffmpeg_path=ffmpeg_path,
        rtsp_transport=_options.rtsp_transport,
        hwaccel=hwaccel,
        output_scale=_options.output_scale,
    )
    if capture.isOpened():
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture

    logger.warning('NVDEC open failed for %s — fallback OpenCV', rtsp_url)
    capture.release()
    return cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

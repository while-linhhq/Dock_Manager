#!/usr/bin/env python3
"""Test GStreamerNvdecCapture vs FfmpegNvdecCapture on RTSP URL.

Usage:
    conda run -n bason-dock python scripts/test_gst_rtsp.py rtsp://...

Captures 30 frames each backend, prints timing + CPU info.
Safe to kill anytime.
"""

import sys
import time
import os
import subprocess
from pathlib import Path

# --- Path bootstrapping (same as app setup) ---
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DATABASE_URL', 'postgresql://x:x@localhost/x')
os.environ.setdefault('RTSP_NVDEC_ENABLED', 'true')

# Force conda lib into LD path before any cv2 import (needed for cuda symbols)
_conda_prefix = os.environ.get('CONDA_PREFIX') or str(
    Path(sys.executable).resolve().parents[1]
)
_conda_lib = os.path.join(_conda_prefix, 'lib')
if os.path.isdir(_conda_lib):
    os.environ.setdefault('LD_LIBRARY_PATH', '')
    os.environ['LD_LIBRARY_PATH'] = f'{_conda_lib}:{os.environ["LD_LIBRARY_PATH"]}'

import cv2
import numpy as np
from app.utils.ai.rtsp_capture import (
    GStreamerNvdecCapture,
    FfmpegNvdecCapture,
    open_rtsp,
    nvdec_status,
    configure_rtsp_decode,
    _options,
)


def test_backend(name: str, cap, frames: int = 30) -> float:
    """Capture `frames` frames, return elapsed wall time + print diagnostics."""
    ok_count = 0
    timestamps = []
    start = time.monotonic()
    for i in range(frames):
        ok, frame = cap.read()
        if ok and frame is not None:
            ok_count += 1
            timestamps.append(time.monotonic())
        else:
            print(f'    [{name}] frame {i}: MISS')
    elapsed = time.monotonic() - start

    if ok_count >= 2:
        intervals = np.diff(timestamps[-ok_count:])
        avg_fps = (ok_count - 1) / intervals.sum() if intervals.sum() > 0 else 0
    else:
        avg_fps = 0.0

    print(f'  [{name}] {ok_count}/{frames} frames in {elapsed:.2f}s '
          f'= {ok_count / elapsed:.1f} fps (avg_{avg_fps:.1f} fps across actual captures)')
    return elapsed


def test_gstreamer_direct(url: str, frames: int = 30):
    """Test GStreamerNvdecCapture directly."""
    print('\n--- GStreamer NVDEC (GPU BGR convert) ---')
    if not GStreamerNvdecCapture.available():
        print('  ** GStreamerNvdecCapture.available() = False **')
        return

    gst_inspect = cv2.TEST_DIR + '/gst-inspect-1.0' if hasattr(cv2, 'TEST_DIR') else 'gst-inspect-1.0'
    cap = GStreamerNvdecCapture(url, rtsp_transport=_options.rtsp_transport)
    if not cap.isOpened():
        print('  ** GStreamerNvdecCapture NOT OPENED **')
        # read stderr from subprocess if available
        return

    shape = None
    cap2 = GStreamerNvdecCapture(url, rtsp_transport=_options.rtsp_transport)
    if cap2.isOpened():
        ok, fr = cap2.read()
        if ok and fr is not None:
            shape = fr.shape
        cap2.release()

    print(f'  opened, frame shape={shape}')
    test_backend('GStreamer', cap, frames)
    cap.release()


def test_ffmpeg_nvdec(url: str, frames: int = 30):
    """Test FfmpegNvdecCapture directly (current default)."""
    from app.utils.ai.rtsp_capture import resolve_ffmpeg_path, resolve_nvdec_hwaccel
    print('\n--- FFmpeg NVDEC (CPU BGR convert) ---')
    ffmpeg_path = resolve_ffmpeg_path()
    hwaccel = resolve_nvdec_hwaccel(ffmpeg_path)
    print(f'  ffmpeg={ffmpeg_path} hwaccel={hwaccel}')

    cap = FfmpegNvdecCapture(
        url,
        ffmpeg_path=ffmpeg_path,
        rtsp_transport=_options.rtsp_transport,
        hwaccel=hwaccel or 'cuda',
        output_scale=_options.output_scale,
    )
    if not cap.isOpened():
        print('  ** FfmpegNvdecCapture NOT OPENED **')
        return
    print('  opened')
    test_backend('FFmpeg', cap, frames)
    cap.release()


def test_open_rtsp(url: str, frames: int = 30):
    """Test open_rtsp with current config (auto GStreamer → FFmpeg → OpenCV)."""
    print(f'\n--- open_rtsp() (auto: GST_NVDEC={_options.use_nvdec}) ---')
    cap = open_rtsp(url)
    if cap is None or not cap.isOpened():
        print('  ** NOT OPENED **')
        return
    print(f'  type={type(cap).__name__}')
    test_backend('open_rtsp', cap, frames)
    cap.release()


def cpu_monitor(pid: int, duration: float, interval: float = 0.5):
    """Read /proc/pid/stat CPU ticks — lightweight."""
    import threading
    result = {}

    def _worker():
        try:
            import re
            start = time.monotonic()
            samples = []
            while time.monotonic() - start < duration:
                try:
                    with open(f'/proc/{pid}/stat') as f:
                        parts = f.read().split()
                        utime = int(parts[13])
                        stime = int(parts[14])
                        samples.append((utime, stime, time.monotonic()))
                except (IndexError, ValueError, OSError):
                    pass
                time.sleep(interval)
            if len(samples) >= 2:
                t0_u, t0_s, t0_w = samples[0]
                t1_u, t1_s, t1_w = samples[-1]
                dt = t1_w - t0_w
                clk = os.sysconf_names.get('SC_CLK_TCK', 100)
                result['user_cpu'] = (t1_u - t0_u) / clk
                result['sys_cpu'] = (t1_s - t0_s) / clk
                result['wall'] = dt
                result['cpu_pct'] = 100 * (result['user_cpu'] + result['sys_cpu']) / dt if dt > 0 else 0
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=duration + 2)
    return result


def benchmark_with_monitor(url: str, frames: int = 60):
    """Capture frames in a subprocess and measure CPU via /proc."""
    import multiprocessing as mp
    import traceback

    def _worker(url, frames, backend: str, result_queue):
        try:
            if backend == 'gst':
                cap = GStreamerNvdecCapture(url, rtsp_transport=_options.rtsp_transport)
            elif backend == 'ffmpeg':
                from app.utils.ai.rtsp_capture import resolve_ffmpeg_path, resolve_nvdec_hwaccel
                ffp = resolve_ffmpeg_path()
                hw = resolve_nvdec_hwaccel(ffp)
                cap = FfmpegNvdecCapture(
                    url, ffmpeg_path=ffp, rtsp_transport=_options.rtsp_transport,
                    hwaccel=hw or 'cuda', output_scale=_options.output_scale,
                )
            elif backend == 'opencv':
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            else:
                cap = open_rtsp(url)

            if not cap.isOpened():
                result_queue.put(None)
                return

            pid = os.getpid()
            # measure CPU of parent separately
            count = 0
            t0 = time.monotonic()
            for i in range(frames):
                ok, _ = cap.read()
                if ok:
                    count += 1
            elapsed = time.monotonic() - t0
            cap.release()
            result_queue.put({'count': count, 'elapsed': elapsed, 'fps': count / elapsed if elapsed else 0, 'pid': pid})
        except Exception as e:
            result_queue.put({'error': str(e), 'traceback': traceback.format_exc()})

    for backend in ['gst', 'ffmpeg']:
        print(f'\n=== Benchmark: {backend} (subprocess, {frames} frames) ===')
        q = mp.Queue()
        p = mp.Process(target=_worker, args=(url, frames, backend, q), daemon=True)
        p.start()
        # wait for pid then monitor
        p.join(timeout=max(5, 0.3 * frames))
        if p.is_alive():
            p.kill()
            p.join()
        result = q.get(timeout=3) if not q.empty() else {}
        if result is None:
            print('  OPEN FAILED')
            continue
        if 'error' in result:
            print(f'  ERROR: {result["error"]}')
            if 'traceback' in result:
                print(result['traceback'][:500])
            continue
        print(f'  {result["count"]}/{frames} frames, {result["elapsed"]:.2f}s = {result["fps"]:.1f} fps')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1]
    frames = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    print(f'RTSP URL: {url}')
    print(f'NVDEC status: {nvdec_status()}')
    print(f'GStreamerAvailable: {GStreamerNvdecCapture.available()}')
    print(f'Frames: {frames}\n')

    # Quick per-backend test
    test_gstreamer_direct(url, frames)
    # test_ffmpeg_nvdec(url, frames)

    # Deeper subprocess benchmark (avoids main process GPU contention)
    print('\n\n========== SUBPROCESS BENCHMARK ==========')
    benchmark_with_monitor(url, min(frames, 60))

    print('\nDone.')

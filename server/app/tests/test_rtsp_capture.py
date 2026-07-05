from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.utils.ai import rtsp_capture


def test_resolve_ffmpeg_path_prefers_explicit(tmp_path):
    ffmpeg = tmp_path / 'ffmpeg'
    ffmpeg.write_bytes(b'')
    with patch('shutil.which', return_value='/usr/bin/ffmpeg'):
        assert rtsp_capture.resolve_ffmpeg_path(str(ffmpeg)) == str(ffmpeg)


def test_nvdec_available_false_without_hwaccel():
    rtsp_capture._nvdec_cache.clear()
    rtsp_capture._hwaccel_cache.clear()
    with patch.object(rtsp_capture, '_ffmpeg_hwaccels', return_value=set()):
        assert rtsp_capture.nvdec_available('/fake/ffmpeg') is False


def test_nvdec_available_true_with_cuda():
    rtsp_capture._nvdec_cache.clear()
    rtsp_capture._hwaccel_cache.clear()
    with patch.object(rtsp_capture, '_ffmpeg_hwaccels', return_value={'cuda'}):
        assert rtsp_capture.nvdec_available('/fake/ffmpeg') is True
        assert rtsp_capture.resolve_nvdec_hwaccel('/fake/ffmpeg') == 'cuda'


def test_open_rtsp_software_when_nvdec_disabled():
    rtsp_capture.configure_rtsp_decode(use_nvdec=False)
    fake_cap = MagicMock()
    with patch('app.utils.ai.rtsp_capture.cv2.VideoCapture', return_value=fake_cap) as mock_cv:
        cap = rtsp_capture.open_rtsp('rtsp://cam/stream')
    assert cap is fake_cap
    mock_cv.assert_called_once()


def test_open_rtsp_fallback_when_nvdec_unavailable():
    rtsp_capture.configure_rtsp_decode(use_nvdec=True)
    rtsp_capture._nvdec_cache.clear()
    rtsp_capture._hwaccel_cache.clear()
    fake_cap = MagicMock()
    # Skip the GStreamer NVDEC branch (it returns _ClosedCapture on failure to
    # avoid a CPU spike) so we exercise the FFmpeg-NVDEC → OpenCV fallback path.
    with patch.object(rtsp_capture.GStreamerNvdecCapture, 'available', return_value=False):
        with patch.object(rtsp_capture, 'nvdec_available', return_value=False):
            with patch('app.utils.ai.rtsp_capture.cv2.VideoCapture', return_value=fake_cap) as mock_cv:
                cap = rtsp_capture.open_rtsp('rtsp://cam/stream')
    assert cap is fake_cap
    mock_cv.assert_called_once()


def test_scaled_frame_dims_halves_even_dimensions():
    assert rtsp_capture.scaled_frame_dims(2560, 1440, 0.5) == (1280, 720)


def test_ffmpeg_nvdec_command_uses_low_latency_realtime_flags():
    cmd = rtsp_capture._build_nvdec_cmd(
        ffmpeg_path='/fake/ffmpeg',
        url='rtsp://cam/stream',
        rtsp_transport='tcp',
        hwaccel='cuda',
        width=640,
        height=360,
    )
    joined = ' '.join(cmd)
    assert '-fflags nobuffer+genpts+discardcorrupt' in joined
    assert '-avioflags direct' in joined
    assert '-rtbufsize 1M' in joined
    assert '-flags low_delay' in joined


def test_gstreamer_launch_command_drops_late_frames():
    launched: dict[str, list[str]] = {}

    class _FakeProc:
        stdout = MagicMock()
        stderr = MagicMock()
        returncode = 0

        def poll(self):
            return None

    def _fake_popen(cmd, **_kwargs):
        launched['cmd'] = cmd
        return _FakeProc()

    cap = object.__new__(rtsp_capture.GStreamerNvdecCapture)
    cap._url = 'rtsp://cam/stream'
    cap._rtsp_transport = 'tcp'
    cap._proc = None
    cap._frame_bytes = 640 * 360 * 3
    cap._read_buffer = bytearray(cap._frame_bytes)
    cap._opened = False
    with patch.object(rtsp_capture.GStreamerNvdecCapture, '_gst_path', return_value='/usr/bin/gst-launch-1.0'):
        with patch.object(rtsp_capture.GStreamerNvdecCapture, '_split_rtsp_url', return_value=('rtsp://cam/stream', None, None)):
            with patch.object(rtsp_capture.GStreamerNvdecCapture, '_env_with_conda_lib', return_value={}):
                with patch.object(rtsp_capture.GStreamerNvdecCapture, '_read_raw_frame', return_value=np.zeros((360, 640, 3), dtype=np.uint8)):
                    with patch('subprocess.Popen', side_effect=_fake_popen):
                        assert cap._try_launch('/usr/bin/gst-launch-1.0', 'rtsp://cam/stream', None, None, 640, 360, 'rtph264depay', 'nvh264dec', 'h264') is True

    cmd = launched['cmd']
    joined = ' '.join(cmd)
    assert 'latency=50' in cmd
    assert 'drop-on-latency=true' in cmd
    assert 'leaky=downstream' in cmd
    assert 'sync=false' in cmd
    assert joined.count('max-size-buffers=1') == 2


def test_ffmpeg_nvdec_capture_read_frame():
    rtsp_capture._nvdec_cache.clear()
    width, height = 4, 2
    frame_bytes = width * height * 3
    payload = (np.arange(frame_bytes, dtype=np.uint8)).tobytes()

    proc = MagicMock()
    proc.poll.return_value = None
    proc.stdout = MagicMock()
    proc.returncode = 0

    state = {'left': payload}

    def _readinto_mock(view) -> int:
        if not state['left']:
            return 0
        n = len(view)
        chunk = state['left'][:n]
        state['left'] = state['left'][len(chunk):]
        view[: len(chunk)] = chunk
        return len(chunk)

    proc.stdout.readinto.side_effect = _readinto_mock

    with patch.object(rtsp_capture, '_probe_stream_size', return_value=(width, height)):
        with patch('subprocess.Popen', return_value=proc):
            cap = rtsp_capture.FfmpegNvdecCapture(
                'rtsp://cam',
                ffmpeg_path='/fake/ffmpeg',
                rtsp_transport='tcp',
                hwaccel='cuda',
                read_timeout_sec=1.0,
                warmup_frames=0,
            )

    with patch('select.select', return_value=([proc.stdout], [], [])):
        ok, frame = cap.read()

    assert ok is True
    assert frame is not None
    assert frame.shape == (height, width, 3)
    cap.release()
